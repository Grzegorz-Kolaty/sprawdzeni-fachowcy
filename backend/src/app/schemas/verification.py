from pydantic import BaseModel, HttpUrl


class WebsiteIdentityVerificationCreate(BaseModel):
    source_url: HttpUrl
    observed_nip: str
    title: str | None = None


class WebsiteIdentityVerificationRead(BaseModel):
    company_id: int
    website_id: int

    source_id: int
    evidence_id: int

    source_url: str

    company_nip: str
    observed_nip: str
    normalized_nip: str

    matches: bool

    evidence_type: str
    confidence: str
