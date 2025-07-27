import asyncio
import json
import os
import shutil
from itertools import islice
from pathlib import Path
from typing import Annotated
from uuid import UUID

import aiofiles
from gcloud.aio.storage import Storage
from google.cloud import translate_v3
from google.cloud import vision_v1
from google.cloud.translate_v3.types.translation_service import TranslateTextResponse
# from google.cloud.vision_v1.types import ImageSource, Image, Feature, AnnotateImageRequest, OutputConfig, GcsDestination, AsyncBatchAnnotateImagesRequest
from google.oauth2 import service_account
from sqlalchemy.ext.asyncio import AsyncSession
from taskiq import TaskiqDepends

from apps.vocabulary_app.models import VocabularyModel
from settings.my_config import get_settings
from settings.my_database import get_session
from settings.my_taskiq import broker
from utility.my_logger import my_logger

settings = get_settings()

try:
    credentials = service_account.Credentials.from_service_account_file(filename=settings.GCP_CREDENTIALS_PATH)
except Exception as e:
    my_logger.exception(f"Exception while initializing google cloud platform credentials, e: {e}")


def chunked(iterable, size):
    it = iter(iterable)
    while chunk := list(islice(it, size)):
        yield chunk


async def upload(path: Path, blob_name: str):
    async with aiofiles.open(path, "rb") as f:
        file_bytes = await f.read()
    await upload_to_gcs(file_bytes=file_bytes, blob_name=blob_name)
    return blob_name


@broker.task
async def start_ocr_upload_pipeline(user_id: str, target_language_code: str, image_paths: list[str]):
    try:
        blob_names = []

        # Prepare (path, blob_name) pairs
        files = [(path, f"{user_id}/{os.path.basename(path)}") for path in image_paths]

        # Upload in chunks of 5
        for chunk in chunked(files, 5):
            tasks = []
            for path, blob_name in chunk:
                tasks.append(upload(path=path, blob_name=blob_name))

            # Run 5 uploads in parallel
            results = await asyncio.gather(*tasks)
            blob_names.extend(results)

        output_prefix = f"ocr_output/{user_id}/"

        my_logger.warning(f"blob_names: {blob_names}")

        await create_vocabulary_task.kiq(owner_id=user_id, blob_names=blob_names, output_prefix=output_prefix, target_language_code=target_language_code)
    except Exception as ex:
        my_logger.exception(f"start_ocr_upload_pipeline failed: {ex}")
        raise ex


async def upload_to_gcs(file_bytes: bytes, blob_name: str):
    try:
        async with Storage(service_file=settings.GCP_CREDENTIALS_PATH) as client:
            await client.upload(bucket=settings.GCS_BUCKET_NAME, object_name=blob_name, file_data=file_bytes)

        my_logger.warning(f"✅ Uploaded to: gs://{settings.GCS_BUCKET_NAME}/{blob_name}")
        return f"gs://{settings.GCS_BUCKET_NAME}/{blob_name}"
    except Exception as ex:
        my_logger.exception(f"upload image failed: {ex}")
        raise ex


async def download_ocr_result(output_prefix: str) -> str:
    try:
        async with Storage(service_file=settings.GCP_CREDENTIALS_PATH) as client:
            objects = await client.list_objects(bucket=settings.GCS_BUCKET_NAME)
            for obj in objects.get('items', []):
                if obj['name'].startswith(output_prefix) and obj['name'].endswith('.json'):
                    content = await client.download(settings.GCS_BUCKET_NAME, obj['name'])
                    response = json.loads(content.decode())
                    my_logger.warning(f"response: {response}")
                    text = response['responses'][0]['fullTextAnnotation']['text']
                    return text
            raise Exception("OCR result not found")
    except Exception as ex:
        my_logger.exception(f"download ocr failed: {ex}")
        raise ex


async def delete_gcs_folder(bucket_name: str, folder_prefix: str):
    try:
        async with Storage(service_file=settings.GCP_CREDENTIALS_PATH) as client:
            objects = await client.list_objects(bucket=bucket_name)
            for obj in objects.get("items", []):
                object_name = obj["name"]
                if object_name.startswith(folder_prefix):
                    await client.delete(bucket=bucket_name, object_name=object_name)
                    my_logger.warning(f"🗑️ Deleted: gs://{bucket_name}/{object_name}")
    except Exception as ex:
        my_logger.exception(f"delete_gcs_folder failed: {ex}")
        raise ex


async def extract_text_from_images(blob_names: list[str], output_uri: str):
    try:
        client = vision_v1.ImageAnnotatorAsyncClient(credentials=credentials)

        features = [{"type_": vision_v1.Feature.Type.TEXT_DETECTION}]
        requests = [
            {"image": {"source": {"image_uri": f"gs://{settings.GCS_BUCKET_NAME}/{blob_name}"}}, "features": features}
            for blob_name in blob_names
        ]
        gcs_destination = {"uri": output_uri}

        batch_size = 10
        output_config = {"gcs_destination": gcs_destination, "batch_size": batch_size}

        operation = client.async_batch_annotate_images(requests=requests, output_config=output_config)

        output_config = {"gcs_destination": {"uri": output_uri}, "batch_size": 100}

        operation = await client.async_batch_annotate_images({"requests": requests, "output_config": output_config})

        my_logger.warning("⏳ Waiting for OCR operation to complete...")
        response = await operation.result(timeout=300)
        gcs_output_uri = response.output_config.gcs_destination.uri
        my_logger.warning(f"Output written to GCS with prefix: {gcs_output_uri}")
        await delete_gcs_folder(settings.GCS_BUCKET_NAME, output_uri)
        my_logger.warning(f"✅ OCR complete, results saved to: {output_uri}")
    except Exception as ex:
        my_logger.exception(f"extract_text_from_images failed: {ex}")
        raise ex


async def translate_text_async(contents: list[str], target_language_code: str, project_id: str) -> str:
    try:
        client = translate_v3.TranslationServiceAsyncClient(credentials=credentials)
        parent = f"projects/{project_id}/locations/global"
        response: TranslateTextResponse = await client.translate_text(parent=parent, contents=contents, mime_type="text/plain", target_language_code=target_language_code)
        return response.translations[0].translated_text
    except Exception as ex:
        my_logger.exception(f"translate_text_async failed: {ex}")
        raise ex


@broker.task(task_name="create_vocabulary_task")
async def create_vocabulary_task(owner_id: str, blob_names: list[str], output_prefix: str, target_language_code: str,
                                 session: Annotated[AsyncSession, TaskiqDepends(get_session)]):
    try:
        gcs_output_uri = f"gs://{settings.GCS_BUCKET_NAME}/{output_prefix}"

        # 1. Run async batch OCR
        chunks = [blob_names[i:i + 1000] for i in range(0, len(blob_names), 1000)]
        for chunk in chunks:
            await extract_text_from_images(blob_names=chunk, output_uri=gcs_output_uri)

        # 2. Download extracted text
        extracted_text = await download_ocr_result(output_prefix=output_prefix)

        # 3. Translate
        translated_text = await translate_text_async(contents=[extracted_text], target_language_code=target_language_code, project_id=settings.GCP_PROJECT_ID)
        my_logger.warning(f"translated_text: {translated_text}")

        # 4. Save to DB
        new_vocabulary = VocabularyModel(word='', translation='', definiton='', part_of_speech='', owner_id=UUID(hex=owner_id))
        session.add(instance=new_vocabulary)
        await session.commit()

        # 5. Cleanup
        await delete_gcs_folder(settings.GCS_BUCKET_NAME, output_prefix)
        for blob in blob_names:
            await delete_gcs_folder(settings.GCS_BUCKET_NAME, blob.rsplit("/", 1)[0])

        shutil.rmtree(settings.TEMP_IMAGES_FOLDER_PATH / owner_id, ignore_errors=True)

        return {"ok": True}
    except Exception as ex:
        my_logger.exception(f"create_vocabulary_task failed: {ex}")
        await session.rollback()
        raise ex

# requests = [
#     AnnotateImageRequest(
#         image=Image(source=ImageSource(image_uri=f"gs://{settings.GCS_BUCKET_NAME}/{blob_name}")),
#         features=[Feature(type_=Feature.Type.DOCUMENT_TEXT_DETECTION)]
#     )
#     for blob_name in blob_names
# ]

# output_config = OutputConfig(
#     gcs_destination=GcsDestination(uri=output_uri),
#     batch_size=1
# )

# operation = await client.async_batch_annotate_images(
#     AsyncBatchAnnotateImagesRequest(
#         requests=[r.pb() for r in requests],
#         output_config=output_config.pb()
#     )
# )
