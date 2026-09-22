from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.company_candidates import get_company_candidate_discovery, router
from app.services.company_candidate_discovery import (
    CompanyCandidateDiscoveryResult,
    CompanyWebsiteCandidate,
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


def _client(
    discovery: FakeCompanyCandidateDiscovery,
) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_company_candidate_discovery] = lambda: discovery

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
