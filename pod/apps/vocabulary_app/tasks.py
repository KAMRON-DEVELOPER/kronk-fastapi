import json
from typing import Annotated
from uuid import UUID

from gcloud.aio.storage import Storage
from google.cloud import storage
from google.cloud import translate_v3
from google.cloud import vision
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


async def upload_to_gcs(file_bytes: bytes, blob_name: str):
    try:
        async with Storage(service_file=settings.GCP_CREDENTIALS_PATH) as client:
            await client.upload(bucket=settings.GCS_BUCKET_NAME, object_name=blob_name, file_data=file_bytes)

        print(f"✅ Uploaded to: gs://{settings.GCS_BUCKET_NAME}/{blob_name}")
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


def delete_gcs_folder(bucket_name: str, folder_prefix: str):
    client = storage.Client(credentials=credentials)
    bucket = client.bucket(bucket_name)
    blobs = bucket.list_blobs(prefix=folder_prefix)
    for blob in blobs:
        blob.delete()
    print(f"🧹 Deleted gs://{bucket_name}/{folder_prefix}")


async def extract_text_from_images(blob_names: list[str], output_uri: str):
    client = vision.ImageAnnotatorAsyncClient(credentials=credentials)

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

    requests = [
        {
            "image": {
                "source": {
                    "image_uri": f"gs://{settings.GCS_BUCKET_NAME}/{blob_name}"
                }
            },
            "features": [
                {"type_": vision.Feature.Type.DOCUMENT_TEXT_DETECTION}
            ]
        }
        for blob_name in blob_names
    ]

    operation = await client.async_batch_annotate_images(
        {
            "requests": requests,
            "output_config": {
                "gcs_destination": {
                    "uri": output_uri
                },
                "batch_size": 100
            }
        }
    )

    print("⏳ Waiting for OCR operation to complete...")
    await operation.result(timeout=300)
    print(f"✅ OCR complete, results saved to: {output_uri}")


async def translate_text_async(contents: list[str], target_language_code: str, project_id: str) -> str:
    client = translate_v3.TranslationServiceAsyncClient(credentials=credentials)
    parent = f"projects/{project_id}/locations/global"
    response: TranslateTextResponse = await client.translate_text(parent=parent, contents=contents, mime_type="text/plain", target_language_code=target_language_code)
    return response.translations[0].translated_text


@broker.task(task_name="create_vocabulary_task")
async def create_vocabulary_task(owner_id: UUID, blob_names: list[str], output_prefix: str, target_language_code: str,
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

        # 4. Save to DB
        new_vocabulary = VocabularyModel(word='', translation='', definiton='', part_of_speech='', owner_id=owner_id)
        session.add(instance=new_vocabulary)
        await session.commit()

        # 5. Cleanup
        delete_gcs_folder(settings.GCS_BUCKET_NAME, output_prefix)
        for blob in blob_names:
            delete_gcs_folder(settings.GCS_BUCKET_NAME, blob.rsplit("/", 1)[0])

        return {"ok": True}
    except Exception as ex:
        my_logger.exception(f"create_vocabulary_task failed: {ex}")
        await session.rollback()
        raise ex
