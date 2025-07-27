import os

import aiofiles
from fastapi import APIRouter, UploadFile, status

from apps.users_app.schemas import ResultSchema
from apps.vocabulary_app.tasks import start_ocr_upload_pipeline
from settings.my_config import get_settings
from settings.my_dependency import strictJwtDependency

vocabulary_router = APIRouter()

settings = get_settings()


@vocabulary_router.post(path="/create", response_model=ResultSchema, status_code=200)
async def upload_images(jwt: strictJwtDependency, images: list[UploadFile], target_language_code: str = "uz"):
    try:
        images_folder_path = settings.TEMP_IMAGES_FOLDER_PATH / jwt.user_id.hex
        images_folder_path.mkdir(parents=True, exist_ok=True)

        for image in images:
            file_path = os.path.join(images_folder_path, image.filename)
            async with aiofiles.open(file_path, mode="wb") as f:
                while chunk := await image.read(size=1024 * 1024):
                    await f.write(chunk)

        image_paths = [str(images_folder_path / fname) for fname in os.listdir(images_folder_path)]

        await start_ocr_upload_pipeline.kiq(user_id=jwt.user_id.hex, target_language_code=target_language_code, image_paths=image_paths)

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
