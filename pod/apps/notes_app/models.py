from datetime import datetime
from typing import Optional
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, UUID, String, Text, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.users_app.models import UserModel, BaseModel

if TYPE_CHECKING:
    pass


# note_collaborator_table = Table(
#     "note_collaborator_table",
#     BaseModel.metadata,
#     Column("note_id", PG_UUID(as_uuid=True), ForeignKey("note_table.id", ondelete="CASCADE"), primary_key=True),
#     Column("user_id", PG_UUID(as_uuid=True), ForeignKey("user_table.id", ondelete="CASCADE"), primary_key=True),
# )


# class TabModel(BaseModel):
#     __tablename__ = "tab_table"

#     name: Mapped[str] = mapped_column(String(length=30))
#     owner_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey(column="user_table.id", ondelete="CASCADE"))
#     owner: Mapped["UserModel"] = relationship(argument="UserModel", back_populates="tabs", passive_deletes=True)

#     notes: Mapped[list["NoteModel"]] = relationship(back_populates="tab", cascade="all, delete-orphan", passive_deletes=True)
#     vocabularies: Mapped[list["VocabularyModel"]] = relationship(back_populates="tab", cascade="all, delete-orphan", passive_deletes=True)

#     def __repr__(self):
#         return f"TabModel: {self.name}"

class NoteModel(BaseModel):
    __tablename__ = "note_table"

    title: Mapped[str] = mapped_column(String(length=50))
    body: Mapped[str] = mapped_column(Text)
    background_color: Mapped[Optional[str]] = mapped_column(String(length=6), nullable=True)
    background_image_url: Mapped[Optional[str]] = mapped_column(String(length=255), nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(length=255), nullable=True)
    remind_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)

    owner_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey(column="user_table.id", ondelete="CASCADE"), nullable=True)
    owner: Mapped["UserModel"] = relationship(argument="UserModel", back_populates="notes", passive_deletes=True)

    def __repr__(self):
        return f"NoteModel: {self.title}"
