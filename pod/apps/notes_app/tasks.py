from typing import Annotated, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from taskiq import TaskiqDepends

from apps.notes_app.models import NoteModel
from apps.notes_app.schemas import NoteIn
from settings.my_database import get_session
from settings.my_taskiq import broker
from utility.my_logger import my_logger


@broker.task(task_name="create_note_task")
async def create_note_task(owner_id: UUID, schema: NoteIn, session: Annotated[AsyncSession, TaskiqDepends(get_session)]):
    try:
        new_note = NoteModel(
            title=schema.title,
            body=schema.body,
            background_color=schema.background_color,
            background_image_url=schema.background_image_url,
            image_url=schema.image_url,
            remind_at=schema.remind_at,
            is_pinned=schema.is_pinned,
            owner_id=owner_id,
            tab_id=schema.tab_id
        )

        session.add(new_note)
        await session.commit()
        return {"ok": True}
    except Exception as e:
        my_logger.exception(f"Note creation failed: {e}")
        await session.rollback()
        raise e


@broker.task(task_name="delete_note_task")
async def delete_note_task(owner_id: UUID, note_id: UUID, session: Annotated[AsyncSession, TaskiqDepends(get_session)]):
    stmt = select(NoteModel).where(NoteModel.id == note_id, NoteModel.owner_id == owner_id)
    result = await session.execute(stmt)
    note: Optional[NoteModel] = result.scalar_one_or_none()

    if not note:
        return {"ok": False}

    await session.delete(note)
    await session.commit()

    return {"ok": True}
