from typing import Optional

from sqlalchemy import ForeignKey, UUID, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql.schema import UniqueConstraint

from apps.users_app.models import BaseModel, UserModel


class SentenceModel(BaseModel):
    __tablename__ = "sentence_table"

    sentence: Mapped[str] = mapped_column(Text)
    translation: Mapped[str] = mapped_column(Text)
    target_language: Mapped[str] = mapped_column(String(length=10), default="uz")
    owner_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("user_table.id", ondelete="CASCADE"))
    owner: Mapped["UserModel"] = relationship("UserModel", back_populates="sentences")
    words: Mapped[list["VocabularyModel"]] = relationship(secondary="sentence_word_association", back_populates="sentences")

    def __repr__(self):
        return f"SentenceModel, sentence: {self.sentence[:10]}"


class SentenceWordAssociation(BaseModel):
    __tablename__ = "sentence_word_association"
    sentence_id: Mapped[UUID] = mapped_column(ForeignKey("sentence_table.id"), primary_key=True)
    word_id: Mapped[UUID] = mapped_column(ForeignKey("vocabulary_table.id"), primary_key=True)


class VocabularyModel(BaseModel):
    __tablename__ = "vocabulary_table"

    word: Mapped[str] = mapped_column(String(length=255), unique=True)
    translation: Mapped[str] = mapped_column(String(length=255))
    target_language: Mapped[str] = mapped_column(String(length=10), default="uz")
    phonetics: Mapped[list["PhoneticModel"]] = relationship(back_populates="vocabulary")
    meanings: Mapped[list["MeaningModel"]] = relationship(back_populates="vocabulary")
    sentences: Mapped[list["SentenceModel"]] = relationship(secondary="sentence_word_association", back_populates="words")
    users: Mapped[list["UserModel"]] = relationship(secondary="user_vocabulary_table", back_populates="vocabularies")


class UserVocabularyModel(BaseModel):
    __tablename__ = "user_vocabulary_table"
    __table_args__ = (UniqueConstraint("user_id", "vocabulary_id", name="_user_vocab_uc"),)

    user_id: Mapped[UUID] = mapped_column(ForeignKey("user_table.id", ondelete="CASCADE"))
    vocabulary_id: Mapped[UUID] = mapped_column(ForeignKey("vocabulary_table.id", ondelete="CASCADE"))


class PhoneticModel(BaseModel):
    __tablename__ = "phonetic_table"
    text: Mapped[Optional[str]] = mapped_column(String(length=255), nullable=True)
    audio: Mapped[Optional[str]]
    vocabulary_id: Mapped[UUID] = mapped_column(ForeignKey("vocabulary_table.id"))
    vocabulary: Mapped["VocabularyModel"] = relationship(back_populates="phonetics")


class MeaningModel(BaseModel):
    __tablename__ = "meaning_table"
    part_of_speech: Mapped[str] = mapped_column(String(length=50))
    definitions: Mapped[list["DefinitionModel"]] = relationship(argument="DefinitionModel", back_populates="meaning")
    vocabulary_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("vocabulary_table.id"))
    vocabulary: Mapped["VocabularyModel"] = relationship(back_populates="meanings")


class DefinitionModel(BaseModel):
    __tablename__ = "definition_table"
    definition: Mapped[str] = mapped_column(Text)
    example: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    meaning_id: Mapped[UUID] = mapped_column(ForeignKey("meaning_table.id"))
    meaning: Mapped["MeaningModel"] = relationship(argument="MeaningModel", back_populates="definitions")
