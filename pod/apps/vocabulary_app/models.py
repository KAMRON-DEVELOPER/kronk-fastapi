from typing import Optional

from sqlalchemy import ForeignKey, UUID, String, Text, JSON
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.notes_app.models import TabModel
from apps.users_app.models import BaseModel, UserModel


class VocabularyCollaboratorLink(BaseModel):
    __tablename__ = "vocabulary_collaborator_link_table"
    vocabulary_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("vocabulary_table.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("user_table.id", ondelete="CASCADE"), primary_key=True)


class VocabularyModel(BaseModel):
    __tablename__ = "vocabulary_table"

    word: Mapped[str] = mapped_column(String(length=255))
    translation: Mapped[str] = mapped_column(String(length=255))
    definition: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    part_of_speech: Mapped[str] = mapped_column(String(length=50))
    examples: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    synonyms: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    transcription: Mapped[Optional[str]] = mapped_column(String(length=255), nullable=True)
    audio_pronunciation_url: Mapped[str] = mapped_column(String(length=255))

    tab_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tab_table.id", ondelete="CASCADE"), nullable=True)
    tab: Mapped["TabModel"] = relationship(argument="TabModel", back_populates="vocabularies", passive_deletes=True)
    owner_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey(column="user_table.id", ondelete="CASCADE"), nullable=True)
    owner: Mapped["UserModel"] = relationship(argument="UserModel", back_populates="vocabularies", passive_deletes=True)
    collaborators: Mapped[list["UserModel"]] = relationship(secondary="vocabulary_collaborator_link_table", back_populates="collaborative_vocabularies", viewonly=False)

    def __repr__(self):
        return "VocabularyModel"
