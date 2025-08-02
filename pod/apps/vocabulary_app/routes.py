import os
from http.client import HTTPException
from uuid import UUID

import aiofiles
from fastapi import APIRouter, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from apps.users_app.schemas import ResultSchema
from apps.vocabulary_app.models import VocabularyModel, SentenceModel, MeaningModel
from apps.vocabulary_app.schemas import VocabularyOut, SentenceOut
from apps.vocabulary_app.tasks import start_ocr_upload_pipeline
from settings.my_config import get_settings
from settings.my_database import DBSession
from settings.my_dependency import strictJwtDependency
from utility.my_logger import my_logger

vocabulary_router = APIRouter()

settings = get_settings()


@vocabulary_router.post(path="/create", response_model=ResultSchema, status_code=200)
async def create_vocabulary(jwt: strictJwtDependency, images: list[UploadFile], target_language_code: str = "uz"):
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


@vocabulary_router.get(path="", response_model=list[VocabularyOut], status_code=200)
async def get_vocabulary(jwt: strictJwtDependency, session: DBSession, start: int = 0, end: int = 20):
    try:
        stmt = (
            select(VocabularyModel)
            .where(VocabularyModel.owner_id == jwt.user_id)
            .order_by(VocabularyModel.created_at.asc())
            .offset(start)
            .limit(end - start + 1)
            .options(selectinload(VocabularyModel.phonetics), selectinload(VocabularyModel.meanings), selectinload(VocabularyModel.sentences))
        )
        results = await session.scalars(stmt)
        vocabularies: list[VocabularyModel] = results.all()

        my_logger.warning(f"vocabulary.__dict__: {vocabularies[0].__dict__}")
        return [VocabularyOut.model_validate(obj=vocabulary) for vocabulary in vocabularies]
    except Exception as e:
        my_logger.exception(f"Exception while creating feed, e: {e}")
        raise HTTPException(str(e))


@vocabulary_router.delete("/delete", status_code=204)
async def delete_vocabulary(vocabulary_id: UUID, jwt: strictJwtDependency, session: DBSession):
    vocabulary = await session.get(VocabularyModel, vocabulary_id)
    if not vocabulary or vocabulary.owner_id != jwt.user_id:
        raise HTTPException("Vocabulary not found")

    await session.delete(vocabulary)
    await session.commit()


@vocabulary_router.get(path="/sentences", response_model=list[SentenceOut], status_code=200)
async def get_sentences(jwt: strictJwtDependency, session: DBSession, start: int = 0, end: int = 20):
    try:
        stmt = (
            select(SentenceModel)
            .where(SentenceModel.owner_id == jwt.user_id)
            .order_by(SentenceModel.created_at.asc())
            .offset(start)
            .limit(end - start + 1)
            .options(selectinload(SentenceModel.words), selectinload(SentenceModel.words).selectinload(VocabularyModel.phonetics),
                     selectinload(SentenceModel.words).selectinload(VocabularyModel.meanings).selectinload(MeaningModel.definitions))
        )
        results = await session.scalars(stmt)
        sentences: list[SentenceModel] = results.all()

        my_logger.warning(f"sentences.__dict__: {sentences[0].__dict__}")
        return [SentenceOut.model_validate(obj=sentence) for sentence in sentences]
    except Exception as e:
        my_logger.exception(f"Exception while creating feed, e: {e}")
        raise HTTPException(str(e))


@vocabulary_router.delete("/sentences/delete", status_code=204)
async def delete_sentence(sentence_id: UUID, jwt: strictJwtDependency, session: DBSession):
    sentence = await session.get(SentenceModel, sentence_id)
    if not sentence or sentence.owner_id != jwt.user_id:
        raise HTTPException("Sentence not found")

    await session.delete(sentence)
    await session.commit()
