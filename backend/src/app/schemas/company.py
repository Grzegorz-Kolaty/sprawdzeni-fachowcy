import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


def normalize_identifier(value: str) -> str:
    return re.sub(r"[\s-]", "", value)


class CompanyCreate(BaseModel):
    legal_name: str
    nip: str
    regon: str | None = None
    krs: str | None = None

    @field_validator("nip")
    @classmethod
    def validate_nip(cls, value: str) -> str:
        value = normalize_identifier(value)

        if not value.isdigit() or len(value) != 10:
            raise ValueError("NIP must contain exactly 10 digits")

        return value

    @field_validator("regon")
    @classmethod
    def validate_regon(cls, value: str | None) -> str | None:
        if value is None:
            return None

        value = normalize_identifier(value)

        if not value.isdigit() or len(value) not in (9, 14):
            raise ValueError("REGON must contain 9 or 14 digits")

        return value

    @field_validator("krs")
    @classmethod
    def validate_krs(cls, value: str | None) -> str | None:
        if value is None:
            return None

        value = normalize_identifier(value)

        if not value.isdigit() or len(value) != 10:
            raise ValueError("KRS must contain exactly 10 digits")

        return value


class CompanyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    legal_name: str
    nip: str
    regon: str | None
    krs: str | None
    created_at: datetime
    updated_at: datetime
