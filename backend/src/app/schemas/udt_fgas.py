from datetime import date, datetime

from pydantic import BaseModel


class UdtFgasCredentialRead(BaseModel):
    id: int
    credential_number: str
    status: str
    scope: str | None
    issued_at: date | None
    status_changed_at: date | None
    verified_at: datetime


class UdtFgasVerificationRead(BaseModel):
    company_id: int
    nip: str

    found: bool

    source_url: str

    credentials: list[UdtFgasCredentialRead]
