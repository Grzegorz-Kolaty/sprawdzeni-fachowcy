from datetime import datetime

from pydantic import BaseModel, ConfigDict, HttpUrl


class ClaimDetectionCreate(BaseModel):
    source_url: HttpUrl


class ClaimRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    source_id: int

    claim_type: str

    claimed_entity: str | None
    normalized_entity: str | None

    claim_text: str

    evidence_candidate_url: str | None

    status: str

    created_at: datetime
    last_observed_at: datetime


class ClaimDetectionRead(BaseModel):
    company_id: int
    website_id: int
    source_url: str

    detected_count: int

    claims: list[ClaimRead]
