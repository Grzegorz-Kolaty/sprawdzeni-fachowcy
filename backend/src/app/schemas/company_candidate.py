from typing import Annotated

from pydantic import BaseModel, StringConstraints

NonEmptyString = Annotated[
    str,
    StringConstraints(
        min_length=1,
        strict=True,
        strip_whitespace=True,
    ),
]


class CompanyCandidateDiscoveryRequest(BaseModel):
    service: NonEmptyString
    location: NonEmptyString


class CompanyWebsiteIdentityExtractionRequest(BaseModel):
    candidate_url: NonEmptyString


class CompanyWebsiteCandidateRead(BaseModel):
    url: str
    domain: str
    title: str | None
    snippet: str | None
    source_query: str
    provider_score: float | None
    provider_engine: str | None


class CompanyCandidateDiscoveryRead(BaseModel):
    service: str
    location: str
    queries: list[str]
    candidates: list[CompanyWebsiteCandidateRead]


class CompanyWebsiteIdentityClueRead(BaseModel):
    field: str
    value: str
    source_url: str
    source_kind: str


class InspectedCompanyWebsiteIdentityPageRead(BaseModel):
    requested_url: str
    final_url: str


class CompanyWebsiteIdentityExtractionRead(BaseModel):
    candidate_url: str
    website_domain: str | None
    inspected_pages: list[InspectedCompanyWebsiteIdentityPageRead]
    identity_clues: list[CompanyWebsiteIdentityClueRead]
    errors: list[str]
