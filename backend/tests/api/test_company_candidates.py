from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.company_candidates import (
    get_company_candidate_discovery,
    get_company_website_identity_extractor,
    router,
)
from app.services.company_candidate_discovery import (
    CompanyCandidateDiscoveryResult,
    CompanyWebsiteCandidate,
)
from app.services.company_website_identity_extraction import (
    CompanyWebsiteIdentityClue,
    CompanyWebsiteIdentityExtraction,
    InspectedCompanyWebsiteIdentityPage,
)


class FakeCompanyCandidateDiscovery:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def discover(
        self,
        *,
        service: str,
        location: str,
    ) -> CompanyCandidateDiscoveryResult:
        self.calls.append(
            (
                service,
                location,
            )
        )

        return CompanyCandidateDiscoveryResult(
            service=service,
            location=location,
            queries=(f"{service} {location}",),
            candidates=(
                CompanyWebsiteCandidate(
                    url="https://example.test/",
                    domain="example.test",
                    title="Example candidate",
                    snippet="Candidate snippet",
                    source_query=f"{service} {location}",
                    provider_score=2.5,
                    provider_engine="fake-engine",
                ),
            ),
        )


class FakeCompanyWebsiteIdentityExtractor:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def extract(
        self,
        candidate_url: str,
    ) -> CompanyWebsiteIdentityExtraction:
        self.calls.append(candidate_url)

        return CompanyWebsiteIdentityExtraction(
            candidate_url=candidate_url,
            website_domain="example.test",
            inspected_pages=(
                InspectedCompanyWebsiteIdentityPage(
                    requested_url=candidate_url,
                    final_url="https://example.test/",
                ),
            ),
            identity_clues=(
                CompanyWebsiteIdentityClue(
                    field="nip",
                    value="1234567890",
                    source_url="https://example.test/",
                    source_kind="page_text",
                ),
            ),
        )


def _client(
    discovery: FakeCompanyCandidateDiscovery,
    extractor: FakeCompanyWebsiteIdentityExtractor | None = None,
) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_company_candidate_discovery] = lambda: discovery

    if extractor is not None:
        app.dependency_overrides[get_company_website_identity_extractor] = lambda: extractor

    return TestClient(app)


def test_discover_company_candidates_returns_read_only_candidates() -> None:
    discovery = FakeCompanyCandidateDiscovery()
    client = _client(discovery)

    response = client.post(
        "/api/company-candidates/discover",
        json={
            "service": " roof repair ",
            "location": " north harbor ",
        },
    )

    assert response.status_code == 200
    assert discovery.calls == [
        (
            "roof repair",
            "north harbor",
        ),
    ]
    assert response.json() == {
        "service": "roof repair",
        "location": "north harbor",
        "queries": [
            "roof repair north harbor",
        ],
        "candidates": [
            {
                "url": "https://example.test/",
                "domain": "example.test",
                "title": "Example candidate",
                "snippet": "Candidate snippet",
                "source_query": "roof repair north harbor",
                "provider_score": 2.5,
                "provider_engine": "fake-engine",
            },
        ],
    }
    assert "verified" not in response.text.casefold()


def test_discover_company_candidates_rejects_empty_input() -> None:
    discovery = FakeCompanyCandidateDiscovery()
    client = _client(discovery)

    response = client.post(
        "/api/company-candidates/discover",
        json={
            "service": "   ",
            "location": "north harbor",
        },
    )

    assert response.status_code == 422
    assert discovery.calls == []


def test_inspect_company_website_identity_returns_unverified_read_only_clues() -> None:
    discovery = FakeCompanyCandidateDiscovery()
    extractor = FakeCompanyWebsiteIdentityExtractor()
    client = _client(
        discovery,
        extractor,
    )

    response = client.post(
        "/api/company-candidates/inspect-identity",
        json={
            "candidate_url": " https://example.test/ ",
        },
    )

    assert response.status_code == 200
    assert extractor.calls == ["https://example.test/"]
    assert response.json() == {
        "candidate_url": "https://example.test/",
        "website_domain": "example.test",
        "inspected_pages": [
            {
                "requested_url": "https://example.test/",
                "final_url": "https://example.test/",
            },
        ],
        "identity_clues": [
            {
                "field": "nip",
                "value": "1234567890",
                "source_url": "https://example.test/",
                "source_kind": "page_text",
            },
        ],
        "errors": [],
    }
    assert "verified" not in response.text.casefold()
