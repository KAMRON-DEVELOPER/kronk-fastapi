import os
from uuid import UUID

import aiofiles
from fastapi import APIRouter, UploadFile
from fastapi.exceptions import HTTPException
from sqlalchemy import select, delete, func
from sqlalchemy.orm import selectinload

from apps.users_app.schemas import ResultSchema
from apps.vocabularies_app.models import VocabularyModel, SentenceModel, MeaningModel, UserVocabularyModel
from apps.vocabularies_app.schemas import VocabularyOut, SentenceOut, VocabularyResponse, SentenceResponse
from apps.vocabularies_app.tasks import start_ocr_upload_pipeline
from settings.my_config import get_settings
from settings.my_database import DBSession
from settings.my_dependency import strictJwtDependency
from utility.my_logger import my_logger

vocabularies_router = APIRouter()

settings = get_settings()


@vocabularies_router.post(path="/create", response_model=ResultSchema, status_code=200)
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


# routes.py
@vocabularies_router.get(path="", response_model=VocabularyResponse, status_code=200)
async def get_vocabulary(jwt: strictJwtDependency, session: DBSession, offset: int = 0, limit: int = 20):
    try:
        base_stmt = (
            select(VocabularyModel)
            .join(UserVocabularyModel, UserVocabularyModel.vocabulary_id == VocabularyModel.id)
            .where(UserVocabularyModel.user_id == jwt.user_id)
        )

        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total = await session.scalar(count_stmt)

        stmt = (
            base_stmt
            .order_by(VocabularyModel.created_at.asc())
            .offset(offset)
            .limit(limit)
            .options(
                selectinload(VocabularyModel.phonetics),
                selectinload(VocabularyModel.meanings),
                selectinload(VocabularyModel.meanings).selectinload(MeaningModel.definitions),
                selectinload(VocabularyModel.sentences)
            )
        )
        results = await session.scalars(stmt)
        vocabularies: list[VocabularyModel] = results.unique().all()

        return VocabularyResponse(vocabularies=[VocabularyOut.model_validate(v) for v in vocabularies], total=total)
    except Exception as e:
        my_logger.exception(f"Exception while fetching vocabulary list, e: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@vocabularies_router.delete("/delete", status_code=204)
async def delete_vocabulary(jwt: strictJwtDependency, vocabulary_ids: list[UUID], session: DBSession):
    try:
        stmt = delete(UserVocabularyModel).where(UserVocabularyModel.user_id == jwt.user_id, UserVocabularyModel.vocabulary_id.in_(vocabulary_ids))
        session.execute(stmt)
        await session.commit()
    except Exception as e:
        my_logger.exception(f"Exception while deleting vocabularies, e: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@vocabularies_router.get(path="/sentences", response_model=SentenceResponse, status_code=200)
async def get_sentences(jwt: strictJwtDependency, session: DBSession, offset: int = 0, limit: int = 20):
    try:
        base_stmt = (select(SentenceModel).where(SentenceModel.owner_id == jwt.user_id))

        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total = await session.scalar(count_stmt)

        stmt = (
            base_stmt
            .order_by(SentenceModel.created_at.asc())
            .offset(offset)
            .limit(limit)
            .options(
                selectinload(SentenceModel.words), selectinload(SentenceModel.words).selectinload(VocabularyModel.phonetics),
                selectinload(SentenceModel.words).selectinload(VocabularyModel.meanings).selectinload(MeaningModel.definitions),
            )
        )
        results = await session.scalars(stmt)
        sentences: list[SentenceModel] = results.unique().all()

        return SentenceResponse(sentences=[SentenceOut.model_validate(sentence) for sentence in sentences], total=total)
    except Exception as e:
        my_logger.exception(f"Exception while creating feed, e: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@vocabularies_router.delete("/sentences/delete", status_code=204)
async def delete_sentence(jwt: strictJwtDependency, sentence_ids: list[UUID], session: DBSession):
    try:
        stmt = delete(SentenceModel).where(SentenceModel.owner_id == jwt.user_id, SentenceModel.id.in_(sentence_ids))
        session.execute(stmt)
        await session.commit()
    except Exception as e:
        my_logger.exception(f"Exception while deleting sentences, e: {e}")
        raise HTTPException(status_code=500, detail=str(e))
