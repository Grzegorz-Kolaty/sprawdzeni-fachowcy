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
