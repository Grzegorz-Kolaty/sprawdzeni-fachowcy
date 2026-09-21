import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.providers.web_discovery import WebDiscoveryProvider, WebDiscoveryResult

_POLISH_TRANSLATION = str.maketrans(
    {
        "ł": "l",
        "Ł": "L",
    }
)

_RELATION_STEMS = (
    "akredyt",
    "autoryz",
    "authorized",
    "certified",
    "certyfik",
    "contractor",
    "czlonk",
    "dealer",
    "instalat",
    "installer",
    "licenc",
    "member",
    "membership",
    "nalezy",
    "partner",
    "serwis",
    "service",
    "uprawn",
    "wykonawc",
)

_DOMAIN_NOISE_TOKENS = {
    "co",
    "com",
    "eu",
    "net",
    "org",
    "pl",
    "www",
}


@dataclass(frozen=True)
class EvidenceSourceCandidate:
    title: str | None
    url: str
    query: str
    score: float
    signals: tuple[str, ...]


class EvidenceSourceDiscovery:
    def __init__(
        self,
        web_discovery: WebDiscoveryProvider,
        *,
        results_per_query: int = 10,
        max_candidates: int = 12,
    ) -> None:
        self._web_discovery = web_discovery
        self._results_per_query = results_per_query
        self._max_candidates = max_candidates

    def discover(
        self,
        *,
        claim_text: str,
        claimed_entity: str | None,
        company_names: list[str],
        company_domains: list[str],
        original_candidate_url: str | None = None,
    ) -> tuple[EvidenceSourceCandidate, ...]:
        queries = self._build_queries(
            claim_text=claim_text,
            claimed_entity=claimed_entity,
            company_names=company_names,
            original_candidate_url=original_candidate_url,
        )

        candidates: dict[str, EvidenceSourceCandidate] = {}

        for query in queries:
            results = self._web_discovery.search(
                query,
                language="pl",
                limit=self._results_per_query,
            )

            for result in results:
                candidate = self._score_result(
                    result=result,
                    query=query,
                    claimed_entity=claimed_entity,
                    company_names=company_names,
                    company_domains=company_domains,
                    original_candidate_url=original_candidate_url,
                )

                if candidate is None:
                    continue

                canonical = self._canonical_url(candidate.url)
                existing = candidates.get(canonical)

                if existing is None or candidate.score > existing.score:
                    candidates[canonical] = candidate

        ranked = sorted(
            candidates.values(),
            key=lambda candidate: candidate.score,
            reverse=True,
        )

        return tuple(ranked[: self._max_candidates])

    def _build_queries(
        self,
        *,
        claim_text: str,
        claimed_entity: str | None,
        company_names: list[str],
        original_candidate_url: str | None,
    ) -> tuple[str, ...]:
        primary_company = self._primary_company_phrase(company_names)
        relation_phrase = self._relation_query_phrase(claim_text)
        source_identity = self._source_identity_phrase(original_candidate_url)

        # Recovery ma odnaleźć to samo źródło pod nowym adresem.
        # Nie wymagamy tu nazwy firmy, bo sprawdzenie firmy i claima
        # należy później do crawlera oraz EvidenceVerifiera.
        if source_identity:
            recovery_query = self._compact_query(
                source_identity,
                claimed_entity,
                relation_phrase,
            )

            if recovery_query:
                return (recovery_query,)

        # General discovery nie zna źródła, więc używa firmy,
        # encji oraz istotnej relacji z claima.
        company_query = (
            f'"{primary_company}"'
            if primary_company and " " in primary_company
            else primary_company
        )

        general_query = self._compact_query(
            company_query,
            claimed_entity,
            relation_phrase,
        )

        if not general_query:
            return ()

        return (general_query,)

    @staticmethod
    def _primary_company_phrase(
        company_names: list[str],
    ) -> str | None:
        names = [name.strip() for name in company_names if name.strip()]

        if not names:
            return None

        shortest = min(names, key=len)
        words = shortest.split()

        # Nie wrzucamy do wyszukiwarki całej,
        # potencjalnie bardzo długiej nazwy prawnej.
        return " ".join(words[:4])

    def _relation_query_phrase(
        self,
        claim_text: str,
    ) -> str | None:
        words = re.findall(
            r"[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż0-9-]+",
            claim_text,
        )

        selected: list[str] = []
        seen: set[str] = set()

        for word in words:
            normalized = self._normalize_text(word)

            if not normalized or normalized in seen:
                continue

            if not any(stem in normalized for stem in _RELATION_STEMS):
                continue

            seen.add(normalized)
            selected.append(word)

            if len(selected) >= 3:
                break

        if not selected:
            return None

        return " ".join(selected)

    @staticmethod
    def _compact_query(
        *parts: str | None,
    ) -> str:
        tokens: list[str] = []
        seen: set[str] = set()

        for part in parts:
            if not part:
                continue

            for token in part.split():
                normalized = token.casefold().strip()

                if not normalized or normalized in seen:
                    continue

                seen.add(normalized)
                tokens.append(token)

                if len(tokens) >= 12:
                    return " ".join(tokens)

        return " ".join(tokens)

    def _score_result(
        self,
        *,
        result: WebDiscoveryResult,
        query: str,
        claimed_entity: str | None,
        company_names: list[str],
        company_domains: list[str],
        original_candidate_url: str | None,
    ) -> EvidenceSourceCandidate | None:
        # Strona samej firmy nie jest niezależnym źródłem evidence.
        if self._belongs_to_company(result.url, company_domains):
            return None

        text = " ".join(
            part
            for part in (
                result.title,
                result.content,
                result.url,
            )
            if part
        )
        normalized_text = self._normalize_text(text)

        same_source_identity = self._same_source_identity(
            original_candidate_url,
            result.url,
        )
        entity_score = self._entity_score(
            normalized_text=normalized_text,
            claimed_entity=claimed_entity,
        )
        relation_score = self._relation_score(normalized_text)
        company_score = self._company_score(
            normalized_text=normalized_text,
            company_names=company_names,
        )

        # Eligibility jest ważniejsze niż ranking.
        # Samo ogólne słowo typu "service" / "partner"
        # nie może przepuścić przypadkowej strony.
        if original_candidate_url:
            # Recovery ma odnaleźć to samo źródło pod nowym adresem.
            if not same_source_identity:
                return None
        else:
            # General discovery musi wskazywać firmę oraz co najmniej
            # jeden sygnał dotyczący claima.
            if company_score == 0:
                return None

            if entity_score == 0 and relation_score == 0:
                return None

        score = 0.0
        signals: list[str] = []

        if same_source_identity:
            score += 60
            signals.append("same_source_identity")

        if entity_score:
            score += entity_score
            signals.append(f"entity:{entity_score}")

        if relation_score:
            score += relation_score
            signals.append(f"relation:{relation_score}")

        if company_score:
            score += company_score
            signals.append(f"company:{company_score}")

        search_score = max(float(result.score or 0.0), 0.0)

        # Wynik SearXNG służy tylko jako tie-breaker/ranking hint.
        score += min(search_score, 5.0)

        return EvidenceSourceCandidate(
            title=result.title,
            url=result.url,
            query=query,
            score=round(score, 2),
            signals=tuple(signals),
        )

    def _entity_score(
        self,
        *,
        normalized_text: str,
        claimed_entity: str | None,
    ) -> int:
        if not claimed_entity:
            return 0

        normalized_entity = self._normalize_text(claimed_entity)

        if normalized_entity and normalized_entity in normalized_text:
            return 20

        return 0

    def _company_score(
        self,
        *,
        normalized_text: str,
        company_names: list[str],
    ) -> int:
        for company_name in company_names:
            normalized_company = self._normalize_text(company_name)

            if normalized_company and normalized_company in normalized_text:
                return 10

        return 0

    @staticmethod
    def _relation_score(
        normalized_text: str,
    ) -> int:
        matched = {stem for stem in _RELATION_STEMS if stem in normalized_text}

        if len(matched) >= 2:
            return 15

        if matched:
            return 10

        return 0

    def _same_source_identity(
        self,
        original_candidate_url: str | None,
        candidate_url: str,
    ) -> bool:
        if not original_candidate_url:
            return False

        original_tokens = self._source_identity_tokens(original_candidate_url)
        candidate_tokens = self._source_identity_tokens(candidate_url)
        common = original_tokens & candidate_tokens

        return any(len(token) >= 5 for token in common)

    def _source_identity_phrase(
        self,
        url: str | None,
    ) -> str | None:
        if not url:
            return None

        tokens = self._source_identity_tokens(url)

        if not tokens:
            return None

        return " ".join(sorted(tokens))

    def _source_identity_tokens(
        self,
        url: str,
    ) -> set[str]:
        hostname = self._hostname(url)

        if hostname is None:
            return set()

        return {
            token
            for token in re.findall(
                r"[a-z0-9]+",
                self._normalize_text(hostname),
            )
            if token not in _DOMAIN_NOISE_TOKENS and len(token) >= 3
        }

    def _belongs_to_company(
        self,
        url: str,
        company_domains: list[str],
    ) -> bool:
        hostname = self._hostname(url)

        if hostname is None:
            return False

        for company_domain in company_domains:
            normalized_domain = self._domain_hostname(company_domain)

            if normalized_domain is None:
                continue

            if hostname == normalized_domain or hostname.endswith(f".{normalized_domain}"):
                return True

        return False

    @staticmethod
    def _domain_hostname(
        value: str,
    ) -> str | None:
        value = value.strip()

        if not value:
            return None

        if "://" not in value:
            value = f"//{value}"

        hostname = urlsplit(value).hostname

        if hostname is None:
            return None

        return hostname.casefold().rstrip(".").removeprefix("www.")

    @staticmethod
    def _hostname(
        url: str,
    ) -> str | None:
        hostname = urlsplit(url).hostname

        if hostname is None:
            return None

        return hostname.casefold().rstrip(".").removeprefix("www.")

    @staticmethod
    def _canonical_url(
        url: str,
    ) -> str:
        parsed = urlsplit(url)
        hostname = (parsed.hostname or "").casefold().removeprefix("www.")
        path = parsed.path.rstrip("/") or "/"

        return f"{parsed.scheme.casefold()}://{hostname}{path}"

    @staticmethod
    def _normalize_text(
        value: str,
    ) -> str:
        value = value.translate(_POLISH_TRANSLATION)
        value = value.casefold()
        value = unicodedata.normalize("NFKD", value)
        value = "".join(character for character in value if not unicodedata.combining(character))
        value = re.sub(
            r"[^a-z0-9]+",
            " ",
            value,
        )

        return " ".join(value.split())
