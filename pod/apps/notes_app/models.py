from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, UUID, String, Text, Boolean, DateTime, ARRAY, CheckConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.users_app.models import UserModel, BaseModel


class ChecklistModel(BaseModel):
    __tablename__ = "checklist_table"
    __table_args__ = (UniqueConstraint("text", "is_done", "note_id", name="uq_note_checklist"),)
    text: Mapped[str] = mapped_column(Text)
    is_done: Mapped[bool] = mapped_column(Boolean)
    note_id: Mapped[UUID] = mapped_column(ForeignKey("note_table.id", ondelete="CASCADE"), nullable=False)
    note: Mapped["NoteModel"] = relationship(argument="NoteModel", back_populates="checklists")

    def __repr__(self):
        return f"ChecklistModel: {self.text}"


class NoteModel(BaseModel):
    __tablename__ = "note_table"
    __table_args__ = (CheckConstraint('(title IS NOT NULL AND body IS NULL) OR (body IS NULL AND title IS NOT NULL)', name='one_field_not_null_constraint'),)
    title: Mapped[Optional[str]] = mapped_column(String(length=64), nullable=True)
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    color: Mapped[Optional[str]] = mapped_column(String(length=6), nullable=True)
    reminder_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    tags: Mapped[Optional[list[str]]] = mapped_column((ARRAY(item_type=String(length=36))), nullable=True)
    collaborators: Mapped[Optional[list[str]]] = mapped_column((ARRAY(item_type=String(length=36))), nullable=True)
    images: Mapped[Optional[list[str]]] = mapped_column(ARRAY(item_type=String(length=255), dimensions=12), nullable=True)
    checklists: Mapped[Optional[list["ChecklistModel"]]] = relationship(argument="ChecklistModel", back_populates="note", cascade="all, delete-orphan", passive_deletes=True)

    owner_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey(column="user_table.id", ondelete="CASCADE"), nullable=True)
    owner: Mapped["UserModel"] = relationship(argument="UserModel", back_populates="notes", passive_deletes=True)

    def __repr__(self):
        return f"NoteModel: {self.title}"
