import asyncio
import os
from itertools import islice

from fastapi import APIRouter, UploadFile, status

from apps.users_app.schemas import ResultSchema
from apps.vocabulary_app.tasks import create_vocabulary_task, upload_to_gcs
from settings.my_config import get_settings
from settings.my_dependency import strictJwtDependency

vocabulary_router = APIRouter()

settings = get_settings()


def chunked(iterable, size):
    it = iter(iterable)
    while chunk := list(islice(it, size)):
        yield chunk


@vocabulary_router.post(path="/create", response_model=ResultSchema, status_code=200)
async def upload_images(jwt: strictJwtDependency, images: list[UploadFile], target_language_code: str = "uz"):
    try:
        print(f"📝 content_type when post: {images}")

        blob_names = []

        for chunk in chunked(images, 10):
            tasks = []
            for image in chunk:
                blob_name = f"{jwt.user_id.hex}/{image.filename}"
                file_bytes = await image.read()
                blob_names.append(blob_name)
                tasks.append(upload_to_gcs(file_bytes, blob_name))
            await asyncio.gather(*tasks)

        output_prefix = f"ocr_output/{jwt.user_id.hex}/"

        await create_vocabulary_task.kiq(owner_id=jwt.user_id, blob_names=blob_names, output_prefix=output_prefix, target_language_code=target_language_code)

        return {"ok": True}
    except Exception as e:
        print(f"🌋 Exception while uploading images: {e}")
        return {"ok": False}


@vocabulary_router.get(path="/vocabulary/images/get", status_code=status.HTTP_200_OK)
async def get_images():
    cwd: str = os.getcwd()
    temp_file_path = os.path.join(cwd, "flutter_images")

    try:
        extracted_words = []

        file_paths = os.listdir(temp_file_path)
        print(f"📝 file_paths: {file_paths}")

        for file_path in file_paths:
            print(f"📝 absolute path: {temp_file_path}/{file_path}")
            extracted_text: str = ""  # await image_to_string(f"{temp_file_path}/{file_path}", lang="eng+uzb")
            print(f"extracted_text: {extracted_text}")
            for text in extracted_text:
                lines = text.split("\n")
                word = lines[0].strip()
                # print(f"📝 text: {text}, lines: {lines}, word: {word}")
                if word:
                    extracted_words.append(word)

        print(f"📝 extracted_words: {extracted_words}")
        # shutil.rmtree(temp_file_path)

        return extracted_words

    except Exception as e:
        print(f"🌋 Exception while reading file: {e}")
        return "fuck off!"

# images_folder_path = settings.TEMP_IMAGES_FOLDER_PATH / jwt.user_id.hex
# try:
#     for image in images:
#         file_path = os.path.join(images_folder_path, image.filename)
#         async with aiofiles.open(file_path, mode="wb") as f:
#             while chunk := await image.read(size=1024 * 1024):
#                 await f.write(chunk)
# except Exception as e:
#     print(f"🌋 Exception while writing file: {e}")
#     return {"ok": False}
