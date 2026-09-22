from fastapi import APIRouter, Depends, HTTPException, status

from app.providers.searxng_web_discovery import SearxngWebDiscoveryProvider
from app.schemas.company_candidate import (
    CompanyCandidateDiscoveryRead,
    CompanyCandidateDiscoveryRequest,
)
from app.services.company_candidate_discovery import (
    CompanyCandidateDiscovery,
    CompanyCandidateDiscoveryInputError,
)

router = APIRouter(
    prefix="/api/company-candidates",
    tags=["company candidates"],
)


def get_company_candidate_discovery() -> CompanyCandidateDiscovery:
    return CompanyCandidateDiscovery(SearxngWebDiscoveryProvider())


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
