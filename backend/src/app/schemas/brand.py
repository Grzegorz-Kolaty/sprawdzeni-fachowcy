from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class BrandCreate(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Brand name cannot be empty")

        return value


class BrandRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    name: str
    created_at: datetime
    updated_at: datetime
