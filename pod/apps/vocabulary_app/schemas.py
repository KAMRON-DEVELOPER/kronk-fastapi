from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class DefinitionSchema(BaseModel):
    definition: str
    example: Optional[str] = None


class MeaningSchema(BaseModel):
    part_of_speech: str
    definitions: list[DefinitionSchema] = Field(default_factory=list)


class PhoneticSchema(BaseModel):
    text: Optional[str]
    audio: Optional[str]


class DictionaryIn(BaseModel):
    word: str
    phonetics: list[PhoneticSchema] = Field(default_factory=list)
    meanings: list[MeaningSchema]


''' OUTPUT '''


class DefinitionOut(BaseModel):
    id: UUID
    created_at: datetime
    updated_at: datetime
    definition: str
    example: Optional[str] = None

    class Config:
        from_attributes = True
        json_encoders = {UUID: lambda v: v.hex, datetime: lambda v: int(v.timestamp()) if v is not None else None}


class MeaningOut(BaseModel):
    id: UUID
    created_at: datetime
    updated_at: datetime
    part_of_speech: str
    definitions: list[DefinitionOut] = []

    class Config:
        from_attributes = True
        json_encoders = {UUID: lambda v: v.hex, datetime: lambda v: int(v.timestamp()) if v is not None else None}


class PhoneticOut(BaseModel):
    id: UUID
    created_at: datetime
    updated_at: datetime
    text: Optional[str] = None
    audio: Optional[str] = None

    class Config:
        from_attributes = True
        json_encoders = {UUID: lambda v: v.hex, datetime: lambda v: int(v.timestamp()) if v is not None else None}


class VocabularyOut(BaseModel):
    id: UUID
    created_at: datetime
    updated_at: datetime
    word: str
    translation: str
    target_language: str
    phonetics: list[PhoneticOut]
    meanings: list[MeaningOut]

    class Config:
        from_attributes = True
        json_encoders = {UUID: lambda v: v.hex, datetime: lambda v: int(v.timestamp()) if v is not None else None}


class SentenceOut(BaseModel):
    id: UUID
    sentence: str
    translation: str
    target_language: str
    words: list[VocabularyOut]

    class Config:
        from_attributes = True
        json_encoders = {UUID: lambda v: v.hex, datetime: lambda v: int(v.timestamp()) if v is not None else None}
