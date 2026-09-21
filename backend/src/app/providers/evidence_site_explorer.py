import heapq
import re
import unicodedata
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

from app.providers.evidence_candidate_context import (
    EvidenceCandidateContext,
    EvidenceCandidateContextBuilder,
)
from app.providers.evidence_candidate_evaluator import (
    EvidenceCandidateEvaluation,
    EvidenceCandidateEvaluator,
)
from app.providers.evidence_candidate_inspector import (
    EvidenceCandidateInspectionError,
    EvidenceCandidateInspector,
)
from app.providers.evidence_site_url_discovery import (
    EvidenceSiteUrlDiscoveryProvider,
)

_POLISH_TRANSLATION = str.maketrans(
    {
        "ł": "l",
        "Ł": "L",
    }
)

EvidenceDiscoveryMethod = Literal[
    "html",
    "sitemap",
]


@dataclass(frozen=True)
class EvidenceSitePageResult:
    url: str
    depth: int
    discovery_method: EvidenceDiscoveryMethod
    context: EvidenceCandidateContext
    evaluation: EvidenceCandidateEvaluation


@dataclass(frozen=True)
class EvidenceSiteExploration:
    start_url: str
    pages: tuple[EvidenceSitePageResult, ...]
    error: str | None = None

    @property
    def best_support(self) -> EvidenceSitePageResult | None:
        candidates = [
            page for page in self.pages if page.evaluation.classification == "potentially_supports"
        ]

        if not candidates:
            return None

        return max(
            candidates,
            key=lambda page: (
                page.evaluation.company_score
                + page.evaluation.entity_score
                + page.evaluation.relation_score
            ),
        )

    @property
    def best_contradiction(self) -> EvidenceSitePageResult | None:
        candidates = [
            page
            for page in self.pages
            if page.evaluation.classification == "potentially_contradicts"
        ]

        if not candidates:
            return None

        return max(
            candidates,
            key=lambda page: (
                page.evaluation.contradiction_score
                + page.evaluation.company_score
                + page.evaluation.entity_score
            ),
        )


class EvidenceSiteExplorer:
    def __init__(
        self,
        *,
        max_pages: int = 8,
        max_depth: int = 2,
    ) -> None:
        self._max_pages = max_pages
        self._max_depth = max_depth

        self._inspector = EvidenceCandidateInspector()
        self._context_builder = EvidenceCandidateContextBuilder()
        self._evaluator = EvidenceCandidateEvaluator()
        self._url_discovery = EvidenceSiteUrlDiscoveryProvider()

    def explore(
        self,
        *,
        start_url: str,
        claim_type: str,
        claim_text: str,
        claimed_entity: str | None,
        company_names: list[str],
        company_domains: list[str],
    ) -> EvidenceSiteExploration:
        start_host = self._hostname(start_url)

        if start_host is None:
            return EvidenceSiteExploration(
                start_url=start_url,
                pages=(),
                error="Start URL has no hostname",
            )

        query_tokens = self._build_query_tokens(
            claim_text=claim_text,
            claimed_entity=claimed_entity,
        )

        pages: list[EvidenceSitePageResult] = []
        visited: set[str] = set()
        queued: set[str] = set()

        first_error: str | None = None

        #
        # Nie pozwalamy normalnemu crawlerowi zużyć
        # całego budżetu przed sitemap fallback.
        #
        html_page_budget = max(
            1,
            self._max_pages // 2,
        )

        queue: list[
            tuple[
                int,
                int,
                int,
                str,
            ]
        ] = []

        sequence = 0

        heapq.heappush(
            queue,
            (
                -1000,
                0,
                sequence,
                start_url,
            ),
        )

        queued.add(self._canonical_url(start_url))

        #
        # Etap 1:
        # chodzenie po normalnych linkach HTML.
        #
        while queue and len(pages) < html_page_budget:
            (
                _negative_score,
                depth,
                _sequence,
                url,
            ) = heapq.heappop(queue)

            canonical_url = self._canonical_url(url)

            if canonical_url in visited:
                continue

            visited.add(canonical_url)

            try:
                inspection = self._inspector.inspect(url)
            except EvidenceCandidateInspectionError as exc:
                if first_error is None:
                    first_error = str(exc)

                continue

            page_result = self._evaluate_page(
                inspection=inspection,
                depth=depth,
                discovery_method="html",
                claim_type=claim_type,
                claim_text=claim_text,
                claimed_entity=claimed_entity,
                company_names=company_names,
                company_domains=company_domains,
            )

            pages.append(page_result)

            #
            # Jeśli normalny crawling już znalazł
            # mocny wynik, sitemap nie jest potrzebna.
            #
            if self._is_result(page_result):
                return EvidenceSiteExploration(
                    start_url=start_url,
                    pages=tuple(pages),
                )

            if depth >= self._max_depth:
                continue

            final_host = self._hostname(inspection.final_url)

            if final_host is None:
                continue

            for link in inspection.links:
                candidate_host = self._hostname(link.url)

                if candidate_host is None:
                    continue

                if not self._same_site(
                    final_host,
                    candidate_host,
                ):
                    continue

                canonical_candidate = self._canonical_url(link.url)

                if canonical_candidate in visited or canonical_candidate in queued:
                    continue

                score = self._link_score(
                    text=link.text,
                    url=link.url,
                    query_tokens=query_tokens,
                )

                if score <= 0:
                    continue

                sequence += 1

                heapq.heappush(
                    queue,
                    (
                        -score,
                        depth + 1,
                        sequence,
                        link.url,
                    ),
                )

                queued.add(canonical_candidate)

        #
        # Etap 2:
        # normalny crawler niczego nie potwierdził,
        # więc dopiero teraz uruchamiamy sitemap discovery.
        #
        if len(pages) < self._max_pages:
            discovery = self._url_discovery.discover(
                start_url,
                claim_text=claim_text,
                claimed_entity=claimed_entity,
            )

            if first_error is None and discovery.errors:
                first_error = discovery.errors[0]

            for candidate in discovery.candidates:
                if len(pages) >= self._max_pages:
                    break

                canonical_candidate = self._canonical_url(candidate.url)

                #
                # Strona mogła już zostać odwiedzona
                # podczas zwykłego crawl.
                #
                if canonical_candidate in visited:
                    continue

                visited.add(canonical_candidate)

                try:
                    inspection = self._inspector.inspect(candidate.url)
                except EvidenceCandidateInspectionError as exc:
                    if first_error is None:
                        first_error = str(exc)

                    continue

                page_result = self._evaluate_page(
                    inspection=inspection,
                    depth=-1,
                    discovery_method="sitemap",
                    claim_type=claim_type,
                    claim_text=claim_text,
                    claimed_entity=claimed_entity,
                    company_names=company_names,
                    company_domains=company_domains,
                )

                pages.append(page_result)

                if self._is_result(page_result):
                    break

        return EvidenceSiteExploration(
            start_url=start_url,
            pages=tuple(pages),
            error=(first_error if not pages else None),
        )

    def _evaluate_page(
        self,
        *,
        inspection,
        depth: int,
        discovery_method: EvidenceDiscoveryMethod,
        claim_type: str,
        claim_text: str,
        claimed_entity: str | None,
        company_names: list[str],
        company_domains: list[str],
    ) -> EvidenceSitePageResult:
        context = self._context_builder.build(
            inspection,
            claim_text=claim_text,
            claimed_entity=claimed_entity,
            company_names=company_names,
        )

        evaluation = self._evaluator.evaluate(
            context=context,
            claim_type=claim_type,
            claim_text=claim_text,
            claimed_entity=claimed_entity,
            company_names=company_names,
            company_domains=company_domains,
        )

        return EvidenceSitePageResult(
            url=inspection.final_url,
            depth=depth,
            discovery_method=discovery_method,
            context=context,
            evaluation=evaluation,
        )

    @staticmethod
    def _is_result(
        page: EvidenceSitePageResult,
    ) -> bool:
        return page.evaluation.classification in {
            "potentially_supports",
            "potentially_contradicts",
        }

    def _build_query_tokens(
        self,
        *,
        claim_text: str,
        claimed_entity: str | None,
    ) -> set[str]:
        ignored = {
            "firma",
            "jest",
            "jestesmy",
            "posiada",
            "mamy",
            "nasz",
            "nasza",
            "system",
            "systems",
            "the",
            "and",
            "with",
        }

        tokens = self._tokens(claim_text)

        if claimed_entity:
            tokens |= self._tokens(claimed_entity)

        return {token for token in tokens if token not in ignored}

    def _link_score(
        self,
        *,
        text: str,
        url: str,
        query_tokens: set[str],
    ) -> int:
        parsed = urlsplit(url)

        path_tokens = self._tokens(parsed.path)

        text_tokens = self._tokens(text)

        all_link_tokens = path_tokens | text_tokens

        matched_query_tokens = {
            query_token
            for query_token in query_tokens
            if any(
                self._tokens_related(
                    query_token,
                    link_token,
                )
                for link_token in all_link_tokens
            )
        }

        if not matched_query_tokens:
            return 0

        score = len(matched_query_tokens) * 10

        matched_in_text = {
            query_token
            for query_token in query_tokens
            if any(
                self._tokens_related(
                    query_token,
                    text_token,
                )
                for text_token in text_tokens
            )
        }

        #
        # Anchor text jest trochę silniejszym
        # sygnałem niż sama ścieżka URL.
        #
        score += len(matched_in_text) * 5

        return score

    @staticmethod
    def _tokens_related(
        first: str,
        second: str,
    ) -> bool:
        if first == second:
            return True

        shorter_length = min(
            len(first),
            len(second),
        )

        #
        # Krótkie identyfikatory typu:
        # BTR, PSD, UDT
        #
        # muszą pasować dokładnie.
        #
        if shorter_length < 7:
            return False

        common_prefix_length = 0

        for left, right in zip(
            first,
            second,
            strict=False,
        ):
            if left != right:
                break

            common_prefix_length += 1

        #
        # Obsługa odmian:
        #
        # certyfikowanym / certyfikowanych
        # wykonawca / wykonawcow
        #
        return common_prefix_length >= 7

    def _tokens(
        self,
        value: str,
    ) -> set[str]:
        normalized = self._normalize_text(value)

        return {
            token
            for token in re.findall(
                r"[a-z0-9]+",
                normalized,
            )
            if len(token) >= 3
        }

    @staticmethod
    def _same_site(
        first: str,
        second: str,
    ) -> bool:
        first = first.casefold().rstrip(".").removeprefix("www.")

        second = second.casefold().rstrip(".").removeprefix("www.")

        return first == second

    @staticmethod
    def _hostname(
        url: str,
    ) -> str | None:
        hostname = urlsplit(url).hostname

        if hostname is None:
            return None

        return hostname.casefold().rstrip(".")

    @staticmethod
    def _canonical_url(
        url: str,
    ) -> str:
        parsed = urlsplit(url)

        hostname = (parsed.hostname or "").casefold()

        if hostname.startswith("www."):
            hostname = hostname[4:]

        path = parsed.path.rstrip("/") or "/"

        return f"{parsed.scheme.casefold()}://{hostname}{path}"

    @staticmethod
    def _normalize_text(
        value: str,
    ) -> str:
        value = value.translate(_POLISH_TRANSLATION)

        value = value.casefold()

        value = unicodedata.normalize(
            "NFKD",
            value,
        )

        value = "".join(character for character in value if not unicodedata.combining(character))

        value = re.sub(
            r"[^a-z0-9]+",
            " ",
            value,
        )

        return re.sub(
            r"\s+",
            " ",
            value,
        ).strip()
