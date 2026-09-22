import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.providers.web_discovery import WebDiscoveryProvider, WebDiscoveryResult

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_POLISH_TRANSLITERATION = str.maketrans(
    {
        "\u0105": "a",
        "\u0107": "c",
        "\u0119": "e",
        "\u0142": "l",
        "\u0144": "n",
        "\u00f3": "o",
        "\u015b": "s",
        "\u017a": "z",
        "\u017c": "z",
    }
)
_TITLE_MATCH_WEIGHT = 5
_CONTENT_MATCH_WEIGHT = 4
_DOMAIN_MATCH_WEIGHT = 3
_URL_MATCH_WEIGHT = 2
_TOKEN_MATCH_WEIGHT = 100
_PHRASE_MATCH_WEIGHT = 25


class CompanyCandidateDiscoveryInputError(ValueError):
    pass


@dataclass(frozen=True)
class CompanyWebsiteCandidate:
    url: str
    domain: str
    title: str | None
    snippet: str | None
    source_query: str
    provider_score: float | None
    provider_engine: str | None


@dataclass(frozen=True)
class CompanyCandidateDiscoveryResult:
    service: str
    location: str
    queries: tuple[str, ...]
    candidates: tuple[CompanyWebsiteCandidate, ...]


@dataclass(frozen=True)
class _ParsedCandidateUrl:
    url: str
    domain: str


@dataclass(frozen=True)
class _RelevanceProfile:
    tokens: tuple[str, ...]
    phrase: str | None


@dataclass(frozen=True)
class _NormalizedCandidateField:
    text: str
    tokens: frozenset[str]
    weight: int


@dataclass(frozen=True)
class _ProfileMatch:
    matched_count: int
    score: int


@dataclass(frozen=True)
class _CandidateRelevance:
    service_score: int
    location_score: int


@dataclass(frozen=True)
class _ScoredCompanyWebsiteCandidate:
    candidate: CompanyWebsiteCandidate
    relevance: _CandidateRelevance


def build_company_candidate_queries(
    *,
    service: str,
    location: str,
) -> tuple[str, ...]:
    normalized_service = _normalize_required_input(
        service,
        field_name="service",
    )
    normalized_location = _normalize_required_input(
        location,
        field_name="location",
    )

    queries = (
        f"{normalized_service} {normalized_location}",
        f'"{normalized_service}" "{normalized_location}"',
        f"{normalized_service} firma {normalized_location}",
    )

    return _deduplicate_text(queries)


class CompanyCandidateDiscovery:
    def __init__(
        self,
        web_discovery: WebDiscoveryProvider,
        *,
        results_per_query: int = 10,
        max_candidates: int = 20,
    ) -> None:
        self._web_discovery = web_discovery
        self._results_per_query = results_per_query
        self._max_candidates = max_candidates

    def discover(
        self,
        *,
        service: str,
        location: str,
    ) -> CompanyCandidateDiscoveryResult:
        normalized_service = _normalize_required_input(
            service,
            field_name="service",
        )
        normalized_location = _normalize_required_input(
            location,
            field_name="location",
        )
        queries = build_company_candidate_queries(
            service=normalized_service,
            location=normalized_location,
        )
        service_profile = _build_relevance_profile(normalized_service)
        location_profile = _build_relevance_profile(normalized_location)

        candidates: dict[str, _ScoredCompanyWebsiteCandidate] = {}

        for query in queries:
            results = self._web_discovery.search(
                query,
                language="pl",
                limit=self._results_per_query,
            )

            for result in results:
                candidate = self._candidate_from_result(
                    result=result,
                    source_query=query,
                    service_profile=service_profile,
                    location_profile=location_profile,
                )

                if candidate is None:
                    continue

                key = self._dedupe_key(candidate)
                existing = candidates.get(key)

                if existing is None or self._is_better_candidate(candidate, existing):
                    candidates[key] = candidate

        ranked = sorted(
            candidates.values(),
            key=self._candidate_rank_value,
            reverse=True,
        )

        return CompanyCandidateDiscoveryResult(
            service=normalized_service,
            location=normalized_location,
            queries=queries,
            candidates=tuple(scored.candidate for scored in ranked[: self._max_candidates]),
        )

    def _candidate_from_result(
        self,
        *,
        result: WebDiscoveryResult,
        source_query: str,
        service_profile: _RelevanceProfile,
        location_profile: _RelevanceProfile,
    ) -> _ScoredCompanyWebsiteCandidate | None:
        parsed = _parse_candidate_url(result.url)

        if parsed is None:
            return None

        relevance = _score_result_relevance(
            result=result,
            parsed=parsed,
            service_profile=service_profile,
            location_profile=location_profile,
        )

        if relevance is None:
            return None

        candidate = CompanyWebsiteCandidate(
            url=parsed.url,
            domain=parsed.domain,
            title=result.title,
            snippet=result.content,
            source_query=source_query,
            provider_score=result.score,
            provider_engine=result.engine,
        )

        return _ScoredCompanyWebsiteCandidate(
            candidate=candidate,
            relevance=relevance,
        )

    @staticmethod
    def _dedupe_key(
        candidate: _ScoredCompanyWebsiteCandidate,
    ) -> str:
        parsed = _parse_candidate_url(candidate.candidate.url)

        if parsed is None:
            return candidate.candidate.url

        return parsed.domain

    def _is_better_candidate(
        self,
        candidate: _ScoredCompanyWebsiteCandidate,
        existing: _ScoredCompanyWebsiteCandidate,
    ) -> bool:
        return self._candidate_rank_value(candidate) > self._candidate_rank_value(existing)

    def _candidate_rank_value(
        self,
        scored: _ScoredCompanyWebsiteCandidate,
    ) -> tuple[int, int, float]:
        return (
            scored.relevance.service_score,
            scored.relevance.location_score,
            self._provider_score_value(scored.candidate),
        )

    @staticmethod
    def _provider_score_value(
        candidate: CompanyWebsiteCandidate,
    ) -> float:
        if candidate.provider_score is None:
            return float("-inf")

        return candidate.provider_score


def _normalize_required_input(
    value: str,
    *,
    field_name: str,
) -> str:
    if not isinstance(value, str):
        raise CompanyCandidateDiscoveryInputError(f"{field_name} must be a non-empty string")

    normalized = " ".join(value.split())

    if not normalized:
        raise CompanyCandidateDiscoveryInputError(f"{field_name} must be a non-empty string")

    return normalized


def _score_result_relevance(
    *,
    result: WebDiscoveryResult,
    parsed: _ParsedCandidateUrl,
    service_profile: _RelevanceProfile,
    location_profile: _RelevanceProfile,
) -> _CandidateRelevance | None:
    fields = (
        _build_candidate_field(result.title, _TITLE_MATCH_WEIGHT),
        _build_candidate_field(result.content, _CONTENT_MATCH_WEIGHT),
        _build_candidate_field(parsed.domain, _DOMAIN_MATCH_WEIGHT),
        _build_candidate_field(parsed.url, _URL_MATCH_WEIGHT),
    )

    service_match = _score_profile_match(service_profile, fields)

    if not _has_sufficient_service_relevance(service_profile, service_match):
        return None

    location_match = _score_profile_match(location_profile, fields)

    return _CandidateRelevance(
        service_score=service_match.score,
        location_score=location_match.score,
    )


def _build_candidate_field(
    value: str | None,
    weight: int,
) -> _NormalizedCandidateField:
    normalized = _normalize_search_text(value or "")

    return _NormalizedCandidateField(
        text=normalized,
        tokens=frozenset(_TOKEN_RE.findall(normalized)),
        weight=weight,
    )


def _build_relevance_profile(
    value: str,
) -> _RelevanceProfile:
    tokens = _deduplicate_tokens(
        token
        for token in _TOKEN_RE.findall(_normalize_search_text(value))
        if _is_meaningful_token(token)
    )

    return _RelevanceProfile(
        tokens=tokens,
        phrase=" ".join(tokens) if tokens else None,
    )


def _score_profile_match(
    profile: _RelevanceProfile,
    fields: tuple[_NormalizedCandidateField, ...],
) -> _ProfileMatch:
    matched_count = 0
    score = 0

    for profile_token in profile.tokens:
        token_score = max(
            (field.weight for field in fields if _token_matches_field(profile_token, field.tokens)),
            default=0,
        )

        if token_score == 0:
            continue

        matched_count += 1
        score += _TOKEN_MATCH_WEIGHT + token_score

    if profile.phrase and any(profile.phrase in field.text for field in fields):
        score += _PHRASE_MATCH_WEIGHT

    return _ProfileMatch(
        matched_count=matched_count,
        score=score,
    )


def _has_sufficient_service_relevance(
    profile: _RelevanceProfile,
    match: _ProfileMatch,
) -> bool:
    if not profile.tokens:
        return False

    if len(profile.tokens) == 1:
        return match.matched_count == 1

    required_matches = max(
        2,
        (len(profile.tokens) + 1) // 2,
    )

    return match.matched_count >= required_matches


def _token_matches_field(
    profile_token: str,
    field_tokens: frozenset[str],
) -> bool:
    if profile_token in field_tokens:
        return True

    return any(_tokens_are_related(profile_token, field_token) for field_token in field_tokens)


def _tokens_are_related(
    requested_token: str,
    candidate_token: str,
) -> bool:
    if requested_token == candidate_token:
        return True

    shorter_length = min(
        len(requested_token),
        len(candidate_token),
    )

    if shorter_length < 5:
        return False

    common_prefix_length = _common_prefix_length(
        requested_token,
        candidate_token,
    )
    required_prefix_length = max(
        5,
        (shorter_length * 3) // 4,
    )

    return common_prefix_length >= required_prefix_length


def _common_prefix_length(
    first: str,
    second: str,
) -> int:
    count = 0

    for first_character, second_character in zip(first, second, strict=False):
        if first_character != second_character:
            break

        count += 1

    return count


def _is_meaningful_token(
    token: str,
) -> bool:
    return len(token) >= 3 or (len(token) >= 2 and any(character.isdigit() for character in token))


def _deduplicate_tokens(
    values: Iterable[str],
) -> tuple[str, ...]:
    deduplicated: list[str] = []
    seen: set[str] = set()

    for value in values:
        if value in seen:
            continue

        seen.add(value)
        deduplicated.append(value)

    return tuple(deduplicated)


def _normalize_search_text(
    value: str,
) -> str:
    normalized = value.casefold().translate(_POLISH_TRANSLITERATION)
    normalized = unicodedata.normalize(
        "NFKD",
        normalized,
    )
    normalized = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    normalized = re.sub(
        r"[^a-z0-9]+",
        " ",
        normalized,
    )

    return " ".join(normalized.split())


def _deduplicate_text(
    values: tuple[str, ...],
) -> tuple[str, ...]:
    deduplicated: list[str] = []
    seen: set[str] = set()

    for value in values:
        normalized = value.casefold()

        if normalized in seen:
            continue

        seen.add(normalized)
        deduplicated.append(value)

    return tuple(deduplicated)


def _parse_candidate_url(
    url: str,
) -> _ParsedCandidateUrl | None:
    parsed = urlsplit(url.strip())

    if parsed.scheme.casefold() not in {"http", "https"}:
        return None

    if parsed.hostname is None:
        return None

    domain = parsed.hostname.casefold().rstrip(".").removeprefix("www.")
    path = parsed.path.rstrip("/") or "/"
    canonical_url = f"{parsed.scheme.casefold()}://{domain}{path}"

    return _ParsedCandidateUrl(
        url=canonical_url,
        domain=domain,
    )
