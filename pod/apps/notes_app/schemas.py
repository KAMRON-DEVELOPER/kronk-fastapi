from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, field_validator

from settings.my_exceptions import ValidationException


class NoteCreateSchema(BaseModel):
    title: str
    body: str
    background_color: Optional[str] = None
    background_image_url: Optional[str] = None
    image_url: Optional[str] = None
    remind_at: Optional[datetime] = None
    is_pinned: bool = False
    tab_id: Optional[UUID] = None
    collaborator_ids: Optional[list[UUID]] = None

    class Config:
        use_enum_values = True
        from_attributes = True
        json_encoders = {UUID: lambda v: v.hex, datetime: lambda v: int(v.timestamp()) if v is not None else None}


class NoteSchema(BaseModel):
    id: UUID
    created_at: datetime
    updated_at: datetime
    title: str
    body: str
    background_color: Optional[str] = None
    background_image_url: Optional[str] = None
    image_url: Optional[str] = None
    remind_at: Optional[datetime] = None
    is_pinned: bool = False
    tab_id: Optional[UUID] = None
    owner_id: UUID

    class Config:
        use_enum_values = True
        from_attributes = True
        json_encoders = {UUID: lambda v: v.hex, datetime: lambda v: int(v.timestamp()) if v is not None else None}

    @field_validator("remind_at")
    def validate_birthdate(cls, value: Optional[datetime]):
        if value is not None:
            min_age_date = datetime.now(timezone.utc) - timedelta(days=12 * 365)
            max_age_date = datetime.now(timezone.utc) - timedelta(days=100 * 365)
            if not (max_age_date <= value <= min_age_date):
                raise ValidationException(detail="Birthdate must be between 12 and 100 years ago.")
        return value


class NoteResponseSchema(BaseModel):
    notes: list[NoteSchema] = []
    end: int = 0

    class Config:
        use_enum_values = True
        from_attributes = True
        json_encoders = {UUID: lambda v: v.hex, datetime: lambda v: int(v.timestamp()) if v is not None else None}
