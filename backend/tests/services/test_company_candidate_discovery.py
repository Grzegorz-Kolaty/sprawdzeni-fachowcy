import pytest

from app.providers.web_discovery import WebDiscoveryResult
from app.services.company_candidate_discovery import (
    CompanyCandidateDiscovery,
    CompanyCandidateDiscoveryInputError,
    build_company_candidate_queries,
)


class FakeWebDiscoveryProvider:
    def __init__(
        self,
        results_by_query: dict[str, tuple[WebDiscoveryResult, ...]] | None = None,
    ) -> None:
        self.results_by_query = results_by_query or {}
        self.calls: list[tuple[str, str, int]] = []

    def search(
        self,
        query: str,
        *,
        language: str = "pl",
        limit: int = 10,
    ) -> tuple[WebDiscoveryResult, ...]:
        self.calls.append(
            (
                query,
                language,
                limit,
            )
        )

        return self.results_by_query.get(query, ())


def _result(
    url: str,
    *,
    title: str | None = "Candidate title",
    content: str | None = "Roof repair in North Harbor",
    engine: str | None = "test-search",
    score: float | None = 1.0,
) -> WebDiscoveryResult:
    return WebDiscoveryResult(
        title=title,
        url=url,
        content=content,
        engine=engine,
        score=score,
    )


def test_service_and_location_build_generic_search_queries() -> None:
    queries = build_company_candidate_queries(
        service="roof repair",
        location="north harbor",
    )

    assert queries == (
        "roof repair north harbor",
        '"roof repair" "north harbor"',
        "roof repair firma north harbor",
    )


def test_discovery_searches_provider_with_queries_from_service_and_location() -> None:
    provider = FakeWebDiscoveryProvider()
    discovery = CompanyCandidateDiscovery(
        provider,
        results_per_query=3,
    )

    result = discovery.discover(
        service="  roof   repair  ",
        location=" north   harbor ",
    )

    assert result.queries == (
        "roof repair north harbor",
        '"roof repair" "north harbor"',
        "roof repair firma north harbor",
    )
    assert provider.calls == [
        (
            "roof repair north harbor",
            "pl",
            3,
        ),
        (
            '"roof repair" "north harbor"',
            "pl",
            3,
        ),
        (
            "roof repair firma north harbor",
            "pl",
            3,
        ),
    ]


def test_provider_results_are_returned_as_company_website_candidates() -> None:
    query = "roof repair north harbor"
    provider = FakeWebDiscoveryProvider(
        {
            query: (
                _result(
                    "https://www.Example-Contractor.test/services?utm_source=search",
                    title="Example Contractor",
                    content="Roof repair in North Harbor",
                    engine="fake-engine",
                    score=4.5,
                ),
            ),
        }
    )
    discovery = CompanyCandidateDiscovery(provider)

    result = discovery.discover(
        service="roof repair",
        location="north harbor",
    )

    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.url == "https://example-contractor.test/services"
    assert candidate.domain == "example-contractor.test"
    assert candidate.title == "Example Contractor"
    assert candidate.snippet == "Roof repair in North Harbor"
    assert candidate.source_query == query
    assert candidate.provider_score == 4.5
    assert candidate.provider_engine == "fake-engine"


def test_multi_word_service_rejects_result_matching_only_generic_fragment() -> None:
    query = "montaż klimatyzacji Szczecin"
    provider = FakeWebDiscoveryProvider(
        {
            query: (
                _result(
                    "https://dictionary.example/montaz",
                    title="Montaż - definicja i pisownia",
                    content="Artykuł omawia znaczenie słowa montaż.",
                    score=100.0,
                ),
                _result(
                    "https://contractor.example/klimatyzacja-szczecin",
                    title="Montaż klimatyzacji Szczecin",
                    content="Instalacja klimatyzacji w domach i biurach.",
                    score=1.0,
                ),
            ),
        }
    )
    discovery = CompanyCandidateDiscovery(provider)

    result = discovery.discover(
        service="montaż klimatyzacji",
        location="Szczecin",
    )

    assert [candidate.domain for candidate in result.candidates] == ["contractor.example"]


def test_service_relevance_matches_simple_morphological_variants() -> None:
    query = "montaż klimatyzacji Szczecin"
    provider = FakeWebDiscoveryProvider(
        {
            query: (
                _result(
                    "https://climate.example/oferta",
                    title="Klimatyzacja Szczecin",
                    content="Montaż systemów chłodzenia dla mieszkań i biur.",
                ),
            ),
        }
    )
    discovery = CompanyCandidateDiscovery(provider)

    result = discovery.discover(
        service="montaż klimatyzacji",
        location="Szczecin",
    )

    assert len(result.candidates) == 1
    assert result.candidates[0].domain == "climate.example"


def test_strong_service_relevance_ranks_above_better_provider_score() -> None:
    query = "premium roof repair north harbor"
    provider = FakeWebDiscoveryProvider(
        {
            query: (
                _result(
                    "https://generic.example/roof-repair",
                    title="Roof repair guide",
                    content="Advice for roof repair projects.",
                    score=100.0,
                ),
                _result(
                    "https://contractor.example/premium-roof-repair",
                    title="Premium roof repair contractor",
                    content="Premium roof repair in North Harbor.",
                    score=1.0,
                ),
            ),
        }
    )
    discovery = CompanyCandidateDiscovery(provider)

    result = discovery.discover(
        service="premium roof repair",
        location="north harbor",
    )

    assert [candidate.domain for candidate in result.candidates] == [
        "contractor.example",
        "generic.example",
    ]


def test_location_match_improves_ranking() -> None:
    query = "roof repair north harbor"
    provider = FakeWebDiscoveryProvider(
        {
            query: (
                _result(
                    "https://remote.example/roof-repair",
                    title="Roof repair contractor",
                    content="Roof repair for residential storm damage.",
                    score=100.0,
                ),
                _result(
                    "https://local.example/roof-repair",
                    title="Roof repair contractor",
                    content="Roof repair in North Harbor for residential storm damage.",
                    score=1.0,
                ),
            ),
        }
    )
    discovery = CompanyCandidateDiscovery(provider)

    result = discovery.discover(
        service="roof repair",
        location="north harbor",
    )

    assert [candidate.domain for candidate in result.candidates] == [
        "local.example",
        "remote.example",
    ]


def test_multi_word_service_relevance_is_generic() -> None:
    query = "orion gasket welding delta city"
    provider = FakeWebDiscoveryProvider(
        {
            query: (
                _result(
                    "https://fragment.example/orion",
                    title="Orion terminology",
                    content="A reference article that only discusses the word Orion.",
                    score=100.0,
                ),
                _result(
                    "https://fabricator.example/gasket-welding",
                    title="Gasket welding services",
                    content="Industrial gasket welding teams serving Delta City.",
                    score=1.0,
                ),
            ),
        }
    )
    discovery = CompanyCandidateDiscovery(provider)

    result = discovery.discover(
        service="orion gasket welding",
        location="delta city",
    )

    assert [candidate.domain for candidate in result.candidates] == ["fabricator.example"]


def test_results_are_deduplicated_by_domain_and_keep_best_provider_score() -> None:
    first_query = "roof repair north harbor"
    second_query = '"roof repair" "north harbor"'
    provider = FakeWebDiscoveryProvider(
        {
            first_query: (
                _result(
                    "https://www.example.test/?utm_source=search#result",
                    title="Lower scored home result",
                    score=1.0,
                ),
                _result(
                    "https://example.test/services",
                    title="Middle scored services result",
                    score=2.0,
                ),
            ),
            second_query: (
                _result(
                    "https://example.test/contact",
                    title="Higher scored contact result",
                    score=3.0,
                ),
            ),
        }
    )
    discovery = CompanyCandidateDiscovery(provider)

    result = discovery.discover(
        service="roof repair",
        location="north harbor",
    )

    assert len(result.candidates) == 1
    assert result.candidates[0].url == "https://example.test/contact"
    assert result.candidates[0].title == "Higher scored contact result"
    assert result.candidates[0].source_query == second_query


def test_homepage_results_are_deduplicated_by_domain() -> None:
    query = "roof repair north harbor"
    provider = FakeWebDiscoveryProvider(
        {
            query: (
                _result(
                    "https://www.example.test/",
                    title="WWW home",
                    score=1.0,
                ),
                _result(
                    "http://example.test",
                    title="HTTP home",
                    score=2.0,
                ),
            ),
        }
    )
    discovery = CompanyCandidateDiscovery(provider)

    result = discovery.discover(
        service="roof repair",
        location="north harbor",
    )

    assert len(result.candidates) == 1
    assert result.candidates[0].domain == "example.test"
    assert result.candidates[0].title == "HTTP home"


def test_all_queries_are_searched_before_applying_max_candidates() -> None:
    first_query = "roof repair north harbor"
    second_query = '"roof repair" "north harbor"'
    third_query = "roof repair firma north harbor"
    provider = FakeWebDiscoveryProvider(
        {
            first_query: (
                _result(
                    "https://first.example.test/",
                    title="First query candidate",
                    score=1.0,
                ),
            ),
            second_query: (
                _result(
                    "https://second.example.test/",
                    title="Second query candidate",
                    score=3.0,
                ),
            ),
            third_query: (
                _result(
                    "https://third.example.test/",
                    title="Third query candidate",
                    score=2.0,
                ),
            ),
        }
    )
    discovery = CompanyCandidateDiscovery(
        provider,
        max_candidates=1,
    )

    result = discovery.discover(
        service="roof repair",
        location="north harbor",
    )

    assert [call[0] for call in provider.calls] == [
        first_query,
        second_query,
        third_query,
    ]
    assert len(result.candidates) == 1
    assert result.candidates[0].domain == "second.example.test"
    assert result.candidates[0].provider_score == 3.0


@pytest.mark.parametrize(
    ("service", "location"),
    [
        (
            "",
            "north harbor",
        ),
        (
            "roof repair",
            "",
        ),
        (
            "   ",
            "north harbor",
        ),
        (
            "roof repair",
            "   ",
        ),
        (
            None,
            "north harbor",
        ),
    ],
)
def test_empty_or_invalid_input_is_rejected(
    service: str,
    location: str,
) -> None:
    discovery = CompanyCandidateDiscovery(FakeWebDiscoveryProvider())

    with pytest.raises(CompanyCandidateDiscoveryInputError):
        discovery.discover(
            service=service,
            location=location,
        )


def test_discovery_has_no_database_dependency() -> None:
    provider = FakeWebDiscoveryProvider(
        {
            "roof repair north harbor": (_result("https://example.test/"),),
        }
    )
    discovery = CompanyCandidateDiscovery(provider)

    result = discovery.discover(
        service="roof repair",
        location="north harbor",
    )

    assert len(result.candidates) == 1
    assert not hasattr(discovery, "_db")


def test_query_generation_uses_same_generic_template_for_different_inputs() -> None:
    first = build_company_candidate_queries(
        service="alpha service",
        location="beta town",
    )
    second = build_company_candidate_queries(
        service="gamma craft",
        location="delta city",
    )

    assert first == (
        "alpha service beta town",
        '"alpha service" "beta town"',
        "alpha service firma beta town",
    )
    assert second == (
        "gamma craft delta city",
        '"gamma craft" "delta city"',
        "gamma craft firma delta city",
    )
