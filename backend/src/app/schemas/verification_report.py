from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.brand import BrandRead
from app.schemas.company import CompanyRead
from app.schemas.company_website import CompanyWebsiteRead


class VerificationSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    source_type: str
    title: str | None
    fetched_at: datetime


class VerificationEvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    evidence_type: str
    observed_value: str | None
    normalized_value: str | None
    confidence: str
    created_at: datetime
    last_observed_at: datetime

    source: VerificationSourceRead


class CompanyCredentialReportRead(BaseModel):
    id: int

    provider: str
    credential_type: str
    issuer: str

    credential_number: str
    status: str
    scope: str | None

    issued_at: date | None
    valid_until: date | None
    status_changed_at: date | None

    verified_at: datetime

    source: VerificationSourceRead


class VerificationSummaryRead(BaseModel):
    identity_verified: bool
    official_credentials_found: bool

    evidence_count: int
    credential_count: int


class CompanyVerificationReportRead(BaseModel):
    company: CompanyRead

    brands: list[BrandRead]
    websites: list[CompanyWebsiteRead]

    summary: VerificationSummaryRead

    credentials: list[CompanyCredentialReportRead]
    evidence: list[VerificationEvidenceRead]
