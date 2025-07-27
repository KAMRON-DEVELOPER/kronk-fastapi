from typing import Annotated
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from taskiq import TaskiqDepends

from apps.notes_app.models import NoteModel, NoteCollaboratorLink
from apps.notes_app.schemas import NoteCreateSchema
from apps.users_app.models import FollowModel
from settings.my_database import get_session
from settings.my_taskiq import broker
from utility.my_logger import my_logger


@broker.task(task_name="create_note_task")
async def create_note_task(owner_id: UUID, schema: NoteCreateSchema, session: Annotated[AsyncSession, TaskiqDepends(get_session)]):
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

        session.add(instance=new_note)
        await session.flush()

        if schema.collaborator_ids:
            links = [NoteCollaboratorLink(note_id=new_note.id, user_id=uid) for uid in schema.collaborator_ids]
            session.add_all(instances=links)

        await session.commit()
        return {"ok": True}
    except Exception as e:
        my_logger.exception(f"Note creation failed: {e}")
        await session.rollback()
        raise e


@broker.task(task_name="delete_follow_from_db")
async def delete_follow_from_db(
        user_id: UUID,
        following_id: UUID,
        session: Annotated[AsyncSession, TaskiqDepends(get_session)],
):
    stmt = select(FollowModel).where(FollowModel.follower_id == user_id, FollowModel.following_id == following_id)
    result = await session.execute(stmt)
    follow = result.scalar_one_or_none()

    if follow is None:
        my_logger.error("Following relation not exist")
        return {"ok": True}

    await session.delete(follow)
    await session.commit()

    return {"ok": True}
