from types import SimpleNamespace

from app.providers.evidence_source_discovery import EvidenceSourceCandidate
from app.services.claim_evidence_verification import (
    _build_direct_candidate_urls,
    _discover_web_candidates,
    _source_order_context_links,
)


def _link(url: str):
    return SimpleNamespace(
        external=True,
        url=url,
    )


def _candidate(
    url: str,
    *,
    score: float,
    signals: tuple[str, ...] = (),
) -> EvidenceSourceCandidate:
    return EvidenceSourceCandidate(
        title=None,
        url=url,
        query="test query",
        score=score,
        signals=signals,
    )


class StubSourceDiscovery:
    def __init__(
        self,
        *,
        recovery: tuple[EvidenceSourceCandidate, ...] = (),
        general: tuple[EvidenceSourceCandidate, ...] = (),
    ) -> None:
        self.recovery = recovery
        self.general = general
        self.calls: list[str | None] = []

    def discover(
        self,
        *,
        claim_text: str,
        claimed_entity: str | None,
        company_names: list[str],
        company_domains: list[str],
        original_candidate_url: str | None = None,
    ) -> tuple[EvidenceSourceCandidate, ...]:
        del claim_text, claimed_entity, company_names, company_domains

        self.calls.append(original_candidate_url)

        if original_candidate_url is not None:
            return self.recovery

        return self.general


def test_source_order_context_links_restores_dom_order() -> None:
    html = """
        <section>
          <a href="https://reklamy-beskid.pl/">Reklamy Beskid</a>
          <a href="https://www.drewnopartner.pl/">Drewno Partner</a>
          <a href="https://knaphouse.pl/">Knap House</a>
          <a href="https://www.blachotrapez.pl/">Blachotrapez</a>
          <a href="https://www.btr.pl/">BTR</a>
        </section>
    """

    best_context = SimpleNamespace(
        links=[
            _link("https://www.btr.pl/"),
            _link("https://reklamy-beskid.pl/"),
            _link("https://www.drewnopartner.pl/"),
            _link("https://knaphouse.pl/"),
            _link("https://www.blachotrapez.pl/"),
        ]
    )

    result = _source_order_context_links(
        html=html,
        source_url="https://domybos.pl/",
        best_context=best_context,
    )

    assert [link.url for link in result] == [
        "https://reklamy-beskid.pl/",
        "https://www.drewnopartner.pl/",
        "https://knaphouse.pl/",
        "https://www.blachotrapez.pl/",
        "https://www.btr.pl/",
    ]


def test_direct_candidates_use_real_neighbours_of_detector_candidate() -> None:
    context_links = [
        _link("https://reklamy-beskid.pl/"),
        _link("https://www.drewnopartner.pl/"),
        _link("https://knaphouse.pl/"),
        _link("https://www.blachotrapez.pl/"),
        _link("https://www.btr.pl/"),
    ]

    result = _build_direct_candidate_urls(
        evidence_candidate_url="https://www.btr.pl/",
        context_links=context_links,
    )

    assert result == [
        "https://www.btr.pl/",
        "https://www.blachotrapez.pl/",
        "https://knaphouse.pl/",
    ]


def test_web_discovery_uses_recovery_before_general_search() -> None:
    recovery_candidate = _candidate(
        "https://www.blachotrapez.eu/",
        score=61.0,
        signals=("same_source_identity",),
    )
    general_candidate = _candidate(
        "https://example.com/",
        score=20.0,
    )

    discovery = StubSourceDiscovery(
        recovery=(recovery_candidate,),
        general=(general_candidate,),
    )

    result = _discover_web_candidates(
        source_discovery=discovery,
        claim_text="Jesteśmy Certyfikowanym Wykonawcą BTR System",
        claimed_entity="BTR System",
        company_names=["BOS USŁUGI BUDOWLANE MICHAŁ OMYŁA"],
        company_domains=["domybos.pl"],
        original_candidate_urls=["https://www.blachotrapez.pl/"],
    )

    assert discovery.calls == ["https://www.blachotrapez.pl/"]
    assert result == (recovery_candidate,)


def test_web_discovery_falls_back_to_general_when_recovery_is_empty() -> None:
    general_candidate = _candidate(
        "https://example.com/",
        score=20.0,
    )

    discovery = StubSourceDiscovery(
        recovery=(),
        general=(general_candidate,),
    )

    result = _discover_web_candidates(
        source_discovery=discovery,
        claim_text="Jesteśmy Certyfikowanym Wykonawcą BTR System",
        claimed_entity="BTR System",
        company_names=["BOS USŁUGI BUDOWLANE MICHAŁ OMYŁA"],
        company_domains=["domybos.pl"],
        original_candidate_urls=["https://www.blachotrapez.pl/"],
    )

    assert discovery.calls == [
        "https://www.blachotrapez.pl/",
        None,
    ]
    assert result == (general_candidate,)
