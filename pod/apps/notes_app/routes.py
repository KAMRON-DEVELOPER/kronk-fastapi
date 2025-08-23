from fastapi import APIRouter
from fastapi.exceptions import HTTPException

from apps.notes_app.models import NoteModel
from apps.notes_app.schemas import NoteIn, NoteResponse, NoteOut
from settings.my_database import DBSession
from settings.my_dependency import strictJwtDependency
from utility.my_logger import my_logger

notes_router = APIRouter()


@notes_router.post(path="/create", response_model=NoteResponse, status_code=200)
async def create_note(jwt: strictJwtDependency, schema: NoteIn, session: DBSession):
    try:
        new_note = NoteModel(
            title=schema.title,
            body=schema.body,
            background_color=schema.background_color,
            background_image_url=schema.background_image_url,
            image_url=schema.image_url,
            remind_at=schema.remind_at,
            is_pinned=schema.is_pinned,
            owner_id=jwt.user_id,
        )

        session.add(new_note)
        session.commit()
        session.refresh(new_note)

        response = NoteOut.model_validate(new_note)
        return response
    except Exception as e:
        my_logger.exception(f"Exception while getting user notes, e: {e}")
        return HTTPException(status_code=500, detail=str(e))
