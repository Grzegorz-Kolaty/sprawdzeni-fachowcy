from fastapi import APIRouter, Depends, HTTPException, status

from app.providers.searxng_web_discovery import SearxngWebDiscoveryProvider
from app.schemas.company_candidate import (
    CompanyCandidateDiscoveryRead,
    CompanyCandidateDiscoveryRequest,
    CompanyWebsiteIdentityExtractionRead,
    CompanyWebsiteIdentityExtractionRequest,
)
from app.services.company_candidate_discovery import (
    CompanyCandidateDiscovery,
    CompanyCandidateDiscoveryInputError,
)
from app.services.company_website_identity_extraction import (
    CompanyWebsiteIdentityExtractor,
)

router = APIRouter(
    prefix="/api/company-candidates",
    tags=["company candidates"],
)


def get_company_candidate_discovery() -> CompanyCandidateDiscovery:
    return CompanyCandidateDiscovery(SearxngWebDiscoveryProvider())


def get_company_website_identity_extractor() -> CompanyWebsiteIdentityExtractor:
    return CompanyWebsiteIdentityExtractor()


@router.post(
    "/discover",
    response_model=CompanyCandidateDiscoveryRead,
)
def discover_company_candidates(
    data: CompanyCandidateDiscoveryRequest,
    discovery: CompanyCandidateDiscovery = Depends(get_company_candidate_discovery),
) -> CompanyCandidateDiscoveryRead:
    try:
        result = discovery.discover(
            service=data.service,
            location=data.location,
        )
    except CompanyCandidateDiscoveryInputError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    return CompanyCandidateDiscoveryRead(
        service=result.service,
        location=result.location,
        queries=list(result.queries),
        candidates=[
            {
                "url": candidate.url,
                "domain": candidate.domain,
                "title": candidate.title,
                "snippet": candidate.snippet,
                "source_query": candidate.source_query,
                "provider_score": candidate.provider_score,
                "provider_engine": candidate.provider_engine,
            }
            for candidate in result.candidates
        ],
    )


@router.post(
    "/inspect-identity",
    response_model=CompanyWebsiteIdentityExtractionRead,
)
def inspect_company_website_identity(
    data: CompanyWebsiteIdentityExtractionRequest,
    extractor: CompanyWebsiteIdentityExtractor = Depends(get_company_website_identity_extractor),
) -> CompanyWebsiteIdentityExtractionRead:
    result = extractor.extract(data.candidate_url)

    return CompanyWebsiteIdentityExtractionRead(
        candidate_url=result.candidate_url,
        website_domain=result.website_domain,
        inspected_pages=[
            {
                "requested_url": page.requested_url,
                "final_url": page.final_url,
            }
            for page in result.inspected_pages
        ],
        identity_clues=[
            {
                "field": clue.field,
                "value": clue.value,
                "source_url": clue.source_url,
                "source_kind": clue.source_kind,
            }
            for clue in result.identity_clues
        ],
        errors=list(result.errors),
    )
