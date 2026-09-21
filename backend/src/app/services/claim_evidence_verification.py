import json
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.providers.claim_context import ClaimContextExtractor
from app.providers.evidence_candidate_context import EvidenceCandidateContextBuilder
from app.providers.evidence_candidate_evaluator import (
    EvidenceCandidateEvaluation,
    EvidenceCandidateEvaluator,
)
from app.providers.evidence_candidate_inspector import (
    EvidenceCandidateInspectionError,
    EvidenceCandidateInspector,
)
from app.providers.evidence_site_explorer import (
    EvidenceSiteExploration,
    EvidenceSiteExplorer,
    EvidenceSitePageResult,
)
from app.providers.evidence_source_discovery import (
    EvidenceSourceCandidate,
    EvidenceSourceDiscovery,
)
from app.providers.evidence_verifier import (
    EvidenceVerificationDecision,
    EvidenceVerifier,
)
from app.providers.searxng_web_discovery import SearxngWebDiscoveryProvider
from app.repositories.brand import get_company_brands
from app.repositories.claim import get_claim
from app.repositories.claim_evidence import upsert_claim_evidence
from app.repositories.company import get_company
from app.repositories.company_website import get_company_websites
from app.repositories.evidence import add_evidence
from app.repositories.source import get_or_create_source, get_source
from app.schemas.claim_evidence_verification import (
    ClaimEvidenceVerificationRead,
    EvidenceCandidateEvaluationRead,
)

_DIRECT_CANDIDATE_LIMIT = 12
_DIRECT_CONTEXT_NEIGHBOR_LIMIT = 2
_WEB_CANDIDATE_LIMIT = 8


class CompanyNotFoundError(Exception):
    pass


class ClaimNotFoundError(Exception):
    pass


class ClaimDoesNotBelongToCompanyError(Exception):
    pass


class ClaimSourceNotFoundError(Exception):
    pass


class ClaimSourceFetchError(Exception):
    pass


class ClaimContextNotFoundError(Exception):
    pass


def verify_claim_evidence(
        db: Session,
        *,
        company_id: int,
        claim_id: int,
) -> ClaimEvidenceVerificationRead:
    company = get_company(
        db,
        company_id,
    )

    if company is None:
        raise CompanyNotFoundError(f"Company {company_id} does not exist")

    claim = get_claim(
        db,
        claim_id,
    )

    if claim is None:
        raise ClaimNotFoundError(f"Claim {claim_id} does not exist")

    if claim.company_id != company.id:
        raise ClaimDoesNotBelongToCompanyError("Claim does not belong to this company")

    claim_source = get_source(
        db,
        claim.source_id,
    )

    if claim_source is None:
        raise ClaimSourceNotFoundError("Claim source does not exist")

    #
    # Rekonstruujemy aktualny kontekst claima
    # na stronie firmy.
    #
    try:
        with httpx.Client(
                timeout=15.0,
                follow_redirects=True,
                headers={"User-Agent": ("SprawdzeniFachowcy/0.1 (claim evidence verification)")},
        ) as client:
            response = client.get(claim_source.url)

            response.raise_for_status()

    except httpx.HTTPError as exc:
        raise ClaimSourceFetchError("Could not fetch original claim source") from exc

    context_extractor = ClaimContextExtractor()

    claim_context = context_extractor.extract_best(
        response.text,
        source_url=claim_source.url,
        claim_text=claim.claim_text,
        claimed_entity=claim.claimed_entity,
    )

    if claim_context is None:
        raise ClaimContextNotFoundError("Could not reconstruct claim context")

    context_links = _source_order_context_links(
        html=response.text,
        source_url=claim_source.url,
        best_context=claim_context,
    )

    brands = get_company_brands(
        db,
        company.id,
    )

    websites = get_company_websites(
        db,
        company.id,
    )

    company_names = [
        company.legal_name,
        *[brand.name for brand in brands],
    ]

    company_domains = [website.domain for website in websites]

    #
    # Budujemy mały zestaw kandydatów bezpośrednich.
    #
    # Jeśli detector wskazał konkretny URL, sprawdzamy go jako pierwszy,
    # ale nie ufamy mu bezwarunkowo. Dobieramy również najbliższe linki
    # z tego samego lokalnego kontekstu claima. Dzięki temu błędny trop
    # nie odcina właściwego źródła, a jednocześnie nie odpytujemy całej
    # sekcji partnerów.
    #
    candidate_urls = _build_direct_candidate_urls(
        evidence_candidate_url=claim.evidence_candidate_url,
        context_links=context_links,
    )

    inspector = EvidenceCandidateInspector()
    context_builder = EvidenceCandidateContextBuilder()
    evaluator = EvidenceCandidateEvaluator()

    explorer = EvidenceSiteExplorer(
        max_pages=8,
        max_depth=2,
    )

    verifier = EvidenceVerifier()

    source_discovery = EvidenceSourceDiscovery(SearxngWebDiscoveryProvider())

    evaluations: list[EvidenceCandidateEvaluationRead] = []

    supporting_count = 0
    contradicting_count = 0
    checked_count = 0

    failed_candidate_urls: list[str] = []

    #
    # ============================================================
    # ETAP 1
    # Kandydaci bezpośrednio wskazani przy claimie.
    # ============================================================
    #
    for candidate_url in candidate_urls:
        checked_count += 1

        #
        # Tani preflight.
        #
        # Jeżeli już strona startowa jest kompletnie niezwiązana
        # z firmą, podmiotem claima ani relacją, nie uruchamiamy
        # dla niej pełnego crawl + sitemap.
        #
        try:
            inspection = inspector.inspect(candidate_url)

        except EvidenceCandidateInspectionError as exc:
            failed_candidate_urls.append(candidate_url)

            evaluations.append(
                EvidenceCandidateEvaluationRead(
                    url=candidate_url,
                    classification=None,
                    error=str(exc),
                )
            )

            continue

        candidate_context = context_builder.build(
            inspection,
            claim_text=claim.claim_text,
            claimed_entity=claim.claimed_entity,
            company_names=company_names,
        )

        preflight_evaluation = evaluator.evaluate(
            context=candidate_context,
            claim_type=claim.claim_type,
            claim_text=claim.claim_text,
            claimed_entity=claim.claimed_entity,
            company_names=company_names,
            company_domains=company_domains,
        )

        if _is_clearly_irrelevant(preflight_evaluation):
            evaluations.append(
                _evaluation_read(
                    url=inspection.final_url,
                    evaluation=preflight_evaluation,
                )
            )

            continue

        exploration = explorer.explore(
            start_url=inspection.final_url,
            claim_type=claim.claim_type,
            claim_text=claim.claim_text,
            claimed_entity=claim.claimed_entity,
            company_names=company_names,
            company_domains=company_domains,
        )

        page, decision = _find_final_decision(
            exploration=exploration,
            verifier=verifier,
            claim_type=claim.claim_type,
            claimed_entity=claim.claimed_entity,
            company_names=company_names,
        )

        if page is not None and decision is not None:
            evidence_id = _persist_verified_evidence(
                db,
                company_id=company.id,
                claim=claim,
                page=page,
                decision=decision,
            )

            if decision.status == "conflicted":
                contradicting_count += 1

            else:
                supporting_count += 1

            evaluations.append(
                _evaluation_read(
                    url=page.url,
                    evaluation=page.evaluation,
                    evidence_id=evidence_id,
                    decision=decision,
                )
            )

            #
            # Konflikt ma najwyższy priorytet.
            #
            if decision.status == "conflicted":
                break

            continue

        representative = _representative_page(exploration)

        if representative is not None:
            representative_decision = verifier.verify(
                context=representative.context,
                evaluation=representative.evaluation,
                claim_type=claim.claim_type,
                claimed_entity=claim.claimed_entity,
                company_names=company_names,
            )

            evaluations.append(
                _evaluation_read(
                    url=representative.url,
                    evaluation=representative.evaluation,
                    decision=representative_decision,
                )
            )

        elif exploration.error:
            evaluations.append(
                EvidenceCandidateEvaluationRead(
                    url=candidate_url,
                    classification=None,
                    error=exploration.error,
                )
            )

    #
    # ============================================================
    # ETAP 2
    # Web discovery.
    #
    # Uruchamiamy tylko wtedy, gdy źródła wskazane bezpośrednio
    # przez stronę firmy nie dały rozstrzygającego wyniku.
    #
    # Przykład:
    #
    # blachotrapez.pl nie działa
    # ↓
    # SearXNG
    # ↓
    # blachotrapez.eu
    # ============================================================
    #
    if supporting_count == 0 and contradicting_count == 0:
        web_candidates = _discover_web_candidates(
            source_discovery=source_discovery,
            claim_text=claim.claim_text,
            claimed_entity=claim.claimed_entity,
            company_names=company_names,
            company_domains=company_domains,
            original_candidate_urls=failed_candidate_urls,
        )

        checked_canonical_urls = {_canonical_url(url) for url in candidate_urls}

        for candidate in web_candidates:
            canonical = _canonical_url(candidate.url)

            if canonical in checked_canonical_urls:
                continue

            checked_canonical_urls.add(canonical)

            checked_count += 1

            exploration = explorer.explore(
                start_url=candidate.url,
                claim_type=claim.claim_type,
                claim_text=claim.claim_text,
                claimed_entity=claim.claimed_entity,
                company_names=company_names,
                company_domains=company_domains,
            )

            page, decision = _find_final_decision(
                exploration=exploration,
                verifier=verifier,
                claim_type=claim.claim_type,
                claimed_entity=claim.claimed_entity,
                company_names=company_names,
            )

            if page is not None and decision is not None:
                evidence_id = _persist_verified_evidence(
                    db,
                    company_id=company.id,
                    claim=claim,
                    page=page,
                    decision=decision,
                    discovery_candidate=candidate,
                )

                if decision.status == "conflicted":
                    contradicting_count += 1

                else:
                    supporting_count += 1

                evaluations.append(
                    _evaluation_read(
                        url=page.url,
                        evaluation=page.evaluation,
                        evidence_id=evidence_id,
                        decision=decision,
                        extra_signals=(
                            "web_discovery",
                            *candidate.signals,
                        ),
                    )
                )

                #
                # Web discovery jest fallbackiem.
                # Pierwsze poprawnie zweryfikowane
                # źródło wystarczy.
                #
                break

            representative = _representative_page(exploration)

            if representative is not None:
                representative_decision = verifier.verify(
                    context=representative.context,
                    evaluation=representative.evaluation,
                    claim_type=claim.claim_type,
                    claimed_entity=claim.claimed_entity,
                    company_names=company_names,
                )

                evaluations.append(
                    _evaluation_read(
                        url=representative.url,
                        evaluation=representative.evaluation,
                        decision=representative_decision,
                        extra_signals=(
                            "web_discovery",
                            *candidate.signals,
                        ),
                    )
                )

            elif exploration.error:
                evaluations.append(
                    EvidenceCandidateEvaluationRead(
                        url=candidate.url,
                        classification=None,
                        error=exploration.error,
                    )
                )

    #
    # ============================================================
    # STATUS CLAIMA
    # ============================================================
    #
    # Konflikt ma pierwszeństwo.
    #
    if contradicting_count > 0:
        claim.status = "conflicted"

    elif supporting_count > 0:
        claim.status = "verified"

    #
    # Brak znalezionego dowodu NIE oznacza,
    # że claim jest fałszywy.
    #
    # Jeżeli niczego nie znaleźliśmy,
    # nie zmieniamy obecnego statusu.
    #
    db.commit()

    db.refresh(claim)

    return ClaimEvidenceVerificationRead(
        company_id=company.id,
        claim_id=claim.id,
        status=claim.status,
        checked_count=checked_count,
        supporting_evidence_count=(supporting_count),
        contradicting_evidence_count=(contradicting_count),
        evaluations=evaluations,
    )


def _source_order_context_links(
        *,
        html: str,
        source_url: str,
        best_context,
):
    """Restore the original DOM order for links from extract_best().

    extract_best() may rank or promote links for relevance.  Direct-candidate
    neighbour selection, however, needs the order in which those same links
    actually appeared in the source document.  We therefore reorder only the
    links already present in best_context by their first occurrence in the HTML.
    """
    soup = BeautifulSoup(html, "html.parser")

    dom_positions: dict[str, int] = {}

    for position, anchor in enumerate(soup.find_all("a", href=True)):
        href = anchor.get("href")

        if not isinstance(href, str) or not href.strip():
            continue

        absolute_url = urljoin(source_url, href.strip())
        canonical = _canonical_url(absolute_url)

        dom_positions.setdefault(canonical, position)

    indexed_links = list(enumerate(best_context.links))

    indexed_links.sort(
        key=lambda item: (
            dom_positions.get(
                _canonical_url(item[1].url),
                len(dom_positions) + item[0],
            ),
            item[0],
        )
    )

    return [link for _, link in indexed_links]


def _build_direct_candidate_urls(
        *,
        evidence_candidate_url: str | None,
        context_links,
) -> list[str]:
    external_urls: list[str] = []
    seen_external: set[str] = set()

    for link in context_links:
        if not link.external:
            continue

        canonical = _canonical_url(link.url)

        if canonical in seen_external:
            continue

        seen_external.add(canonical)
        external_urls.append(link.url)

    if not evidence_candidate_url:
        return external_urls[:_DIRECT_CANDIDATE_LIMIT]

    evidence_canonical = _canonical_url(evidence_candidate_url)

    anchor_index = next(
        (
            index
            for index, url in enumerate(external_urls)
            if _canonical_url(url) == evidence_canonical
        ),
        None,
    )

    # Detector candidate zawsze jest pierwszy.
    candidates = [evidence_candidate_url]
    seen_candidates = {evidence_canonical}

    # Jeśli detector wskazał URL spoza lokalnego kontekstu,
    # nie zgadujemy sąsiadów. Później zadziała web discovery.
    if anchor_index is None:
        return candidates

    # Dobieramy linki według RZECZYWISTEJ odległości od anchoru
    # w claim_context.links. Nie bierzemy pierwszych linków sekcji.
    # Dla: [..., knaphouse, blachotrapez, btr]
    # otrzymamy: [btr, blachotrapez, knaphouse].
    ordered_neighbor_indexes: list[int] = []

    for distance in range(1, len(external_urls)):
        left_index = anchor_index - distance
        right_index = anchor_index + distance

        if left_index >= 0:
            ordered_neighbor_indexes.append(left_index)

        if right_index < len(external_urls):
            ordered_neighbor_indexes.append(right_index)

        if len(ordered_neighbor_indexes) >= _DIRECT_CONTEXT_NEIGHBOR_LIMIT:
            break

    for neighbor_index in ordered_neighbor_indexes[:_DIRECT_CONTEXT_NEIGHBOR_LIMIT]:
        neighbor_url = external_urls[neighbor_index]
        canonical = _canonical_url(neighbor_url)

        if canonical in seen_candidates:
            continue

        seen_candidates.add(canonical)
        candidates.append(neighbor_url)

    return candidates


def _find_final_decision(
        *,
        exploration: EvidenceSiteExploration,
        verifier: EvidenceVerifier,
        claim_type: str,
        claimed_entity: str | None,
        company_names: list[str],
) -> tuple[
    EvidenceSitePageResult | None,
    EvidenceVerificationDecision | None,
]:
    verified: list[
        tuple[
            EvidenceSitePageResult,
            EvidenceVerificationDecision,
        ]
    ] = []

    for page in exploration.pages:
        decision = verifier.verify(
            context=page.context,
            evaluation=page.evaluation,
            claim_type=claim_type,
            claimed_entity=claimed_entity,
            company_names=company_names,
        )

        #
        # Konflikt ma pierwszeństwo przed wsparciem.
        #
        if decision.status == "conflicted":
            return page, decision

        if decision.status == "verified":
            verified.append(
                (
                    page,
                    decision,
                )
            )

    if not verified:
        return None, None

    return max(
        verified,
        key=lambda item: (
            item[1].confidence,
            item[0].evaluation.company_score
            + item[0].evaluation.entity_score
            + item[0].evaluation.relation_score,
        ),
    )


def _representative_page(
        exploration: EvidenceSiteExploration,
) -> EvidenceSitePageResult | None:
    if not exploration.pages:
        return None

    return max(
        exploration.pages,
        key=lambda page: (
                page.evaluation.company_score
                + page.evaluation.entity_score
                + page.evaluation.relation_score
                + page.evaluation.contradiction_score
        ),
    )


def _is_clearly_irrelevant(
        evaluation: EvidenceCandidateEvaluation,
) -> bool:
    return (
            evaluation.classification == "irrelevant"
            and evaluation.company_score == 0
            and evaluation.entity_score == 0
            and evaluation.relation_score == 0
            and evaluation.contradiction_score == 0
    )


def _persist_verified_evidence(
        db: Session,
        *,
        company_id: int,
        claim,
        page: EvidenceSitePageResult,
        decision: EvidenceVerificationDecision,
        discovery_candidate: EvidenceSourceCandidate | None = None,
) -> int:
    if decision.status == "verified":
        relation = "supports"

        evidence_type = "claim_external_support"

    elif decision.status == "conflicted":
        relation = "contradicts"

        evidence_type = "claim_external_contradiction"

    else:
        raise ValueError("Only verified or conflicted decisions can be persisted")

    external_source = get_or_create_source(
        db,
        url=page.url,
        source_type="external_web_source",
        title=page.context.title,
    )

    db.flush()

    observed_value_data = {
        "title": page.context.title,
        "description": page.context.description,
        "snippets": list(page.context.snippets),
        "supporting_snippet": (decision.supporting_snippet),
        "scores": {
            "company": (page.evaluation.company_score),
            "entity": (page.evaluation.entity_score),
            "relation": (page.evaluation.relation_score),
            "contradiction": (page.evaluation.contradiction_score),
        },
        "signals": list(page.evaluation.signals),
        "verifier": {
            "status": decision.status,
            "confidence": decision.confidence,
            "reasons": list(decision.reasons),
        },
        "site_discovery_method": (page.discovery_method),
    }

    if discovery_candidate is not None:
        observed_value_data["web_discovery"] = {
            "query": (discovery_candidate.query),
            "score": (discovery_candidate.score),
            "signals": list(discovery_candidate.signals),
            "title": (discovery_candidate.title),
            "url": (discovery_candidate.url),
        }

    observed_value = json.dumps(
        observed_value_data,
        ensure_ascii=False,
    )

    normalized_value = f"{claim.claim_type}:{claim.normalized_entity or claim.fingerprint}"

    evidence = add_evidence(
        db,
        company_id=company_id,
        source_id=external_source.id,
        evidence_type=evidence_type,
        observed_value=observed_value,
        normalized_value=normalized_value,
        confidence="strong",
    )

    db.flush()

    upsert_claim_evidence(
        db,
        claim_id=claim.id,
        evidence_id=evidence.id,
        relation=relation,
        confidence="strong",
    )

    return evidence.id


def _evaluation_read(
        *,
        url: str,
        evaluation: EvidenceCandidateEvaluation,
        evidence_id: int | None = None,
        decision: EvidenceVerificationDecision | None = None,
        extra_signals: tuple[str, ...] = (),
) -> EvidenceCandidateEvaluationRead:
    signals = [
        *evaluation.signals,
        *extra_signals,
    ]

    if decision is not None:
        signals.append(f"verifier:{decision.status}")

        signals.extend(f"verifier_reason:{reason}" for reason in decision.reasons)

    return EvidenceCandidateEvaluationRead(
        url=url,
        classification=(evaluation.classification),
        independent_source=(evaluation.independent_source),
        company_score=(evaluation.company_score),
        entity_score=(evaluation.entity_score),
        relation_score=(evaluation.relation_score),
        contradiction_score=(evaluation.contradiction_score),
        signals=signals,
        evidence_id=evidence_id,
    )


def _discover_web_candidates(
        *,
        source_discovery: EvidenceSourceDiscovery,
        claim_text: str,
        claimed_entity: str | None,
        company_names: list[str],
        company_domains: list[str],
        original_candidate_urls: list[str],
) -> tuple[EvidenceSourceCandidate, ...]:
    #
    # 1. Recovery starego źródła.
    #
    # Jeżeli bezpośredni URL przestał działać, najpierw próbujemy
    # odnaleźć nowe źródło o tej samej tożsamości.
    #
    if original_candidate_urls:
        origin = original_candidate_urls[0]

        try:
            recovered = source_discovery.discover(
                claim_text=claim_text,
                claimed_entity=claimed_entity,
                company_names=company_names,
                company_domains=company_domains,
                original_candidate_url=origin,
            )

        except (
                httpx.HTTPError,
                ValueError,
        ):
            recovered = ()

        if recovered:
            return _rank_discovery_candidates(recovered)

    #
    # 2. General discovery dopiero wtedy, gdy recovery
    # nie zwróciło użytecznych kandydatów.
    #
    try:
        discovered = source_discovery.discover(
            claim_text=claim_text,
            claimed_entity=claimed_entity,
            company_names=company_names,
            company_domains=company_domains,
            original_candidate_url=None,
        )

    except (
            httpx.HTTPError,
            ValueError,
    ):
        discovered = ()

    return _rank_discovery_candidates(discovered)


def _rank_discovery_candidates(
        candidates: tuple[EvidenceSourceCandidate, ...],
) -> tuple[EvidenceSourceCandidate, ...]:
    deduplicated: dict[
        str,
        EvidenceSourceCandidate,
    ] = {}

    for candidate in candidates:
        canonical = _canonical_url(candidate.url)

        existing = deduplicated.get(canonical)

        if existing is None or candidate.score > existing.score:
            deduplicated[canonical] = candidate

    ranked = sorted(
        deduplicated.values(),
        key=lambda candidate: candidate.score,
        reverse=True,
    )

    return tuple(ranked[:_WEB_CANDIDATE_LIMIT])


def _canonical_url(
        url: str,
) -> str:
    parsed = urlsplit(url)

    hostname = (parsed.hostname or "").casefold().removeprefix("www.")

    path = parsed.path.rstrip("/") or "/"

    return f"{parsed.scheme.casefold()}://{hostname}{path}"
