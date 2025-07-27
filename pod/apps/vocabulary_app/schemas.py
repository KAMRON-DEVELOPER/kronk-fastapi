from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, field_validator

from utility.validators import (validate_length)


class VocabularyCreateSchema(BaseModel):
    name: str
    username: str
    email: str
    password: str

    @field_validator("name")
    def validate_name(cls, value: str):
        validate_length(field=value, min_len=2, max_len=30, field_name="Name")
        return value

    class Config:
        from_attributes = True
        json_encoders = {UUID: lambda v: v.hex, datetime: lambda v: int(v.timestamp()) if v is not None else None}
