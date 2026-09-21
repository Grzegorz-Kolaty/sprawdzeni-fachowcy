import re
from dataclasses import dataclass

from app.providers.evidence_candidate_inspector import (
    EvidenceCandidateInspection,
)


@dataclass(frozen=True)
class EvidenceCandidateContext:
    url: str
    title: str | None
    description: str | None

    snippets: tuple[str, ...]


class EvidenceCandidateContextBuilder:
    _WINDOW_SIZE = 450
    _MAX_SNIPPETS = 5

    def build(
        self,
        inspection: EvidenceCandidateInspection,
        *,
        claim_text: str,
        claimed_entity: str | None,
        company_names: list[str],
    ) -> EvidenceCandidateContext:
        search_terms = self._build_search_terms(
            claim_text=claim_text,
            claimed_entity=claimed_entity,
            company_names=company_names,
        )

        snippets = self._find_snippets(
            inspection.visible_text,
            search_terms=search_terms,
        )

        return EvidenceCandidateContext(
            url=inspection.final_url,
            title=inspection.title,
            description=inspection.description,
            snippets=tuple(snippets),
        )

    def _find_snippets(
        self,
        text: str,
        *,
        search_terms: set[str],
    ) -> list[str]:
        if not text:
            return []

        lowered = text.casefold()

        candidates: list[tuple[int, int, str]] = []

        seen_ranges: set[tuple[int, int]] = set()

        for term in search_terms:
            start_from = 0

            while True:
                position = lowered.find(
                    term,
                    start_from,
                )

                if position == -1:
                    break

                start = max(
                    0,
                    position - self._WINDOW_SIZE,
                )

                end = min(
                    len(text),
                    position + len(term) + self._WINDOW_SIZE,
                )

                range_key = (
                    start,
                    end,
                )

                if range_key not in seen_ranges:
                    snippet = self._normalize_text(text[start:end])

                    score = self._score_snippet(
                        snippet,
                        search_terms=search_terms,
                    )

                    candidates.append(
                        (
                            score,
                            start,
                            snippet,
                        )
                    )

                    seen_ranges.add(range_key)

                start_from = position + len(term)

        candidates.sort(
            key=lambda item: (
                -item[0],
                item[1],
            )
        )

        result: list[str] = []

        for _, _, snippet in candidates:
            if self._is_duplicate(
                snippet,
                result,
            ):
                continue

            result.append(snippet)

            if len(result) >= self._MAX_SNIPPETS:
                break

        return result

    def _build_search_terms(
        self,
        *,
        claim_text: str,
        claimed_entity: str | None,
        company_names: list[str],
    ) -> set[str]:
        result: set[str] = set()

        if claimed_entity:
            normalized_entity = self._normalize_text(claimed_entity).casefold()

            if normalized_entity:
                result.add(normalized_entity)

        for company_name in company_names:
            normalized_name = self._normalize_text(company_name).casefold()

            if normalized_name:
                result.add(normalized_name)

            result.update(self._significant_tokens(company_name))

        result.update(self._significant_tokens(claim_text))

        return result

    @staticmethod
    def _significant_tokens(
        value: str,
    ) -> set[str]:
        ignored = {
            "jestesmy",
            "jesteśmy",
            "firma",
            "uslugi",
            "usługi",
            "budowlane",
            "system",
            "systems",
            "posiada",
            "certyfikat",
            "wykonawca",
            "wykonawcą",
            "wykonawcy",
            "autoryzowany",
            "autoryzowanego",
            "certyfikowany",
            "certyfikowanym",
        }

        return {
            token
            for token in re.findall(
                r"[0-9a-ząćęłńóśźż]+",
                value.casefold(),
            )
            if (len(token) >= 3 and token not in ignored)
        }

    @staticmethod
    def _score_snippet(
        snippet: str,
        *,
        search_terms: set[str],
    ) -> int:
        lowered = snippet.casefold()

        return sum(1 for term in search_terms if term in lowered)

    @staticmethod
    def _is_duplicate(
        candidate: str,
        existing: list[str],
    ) -> bool:
        candidate_normalized = candidate.casefold()

        for item in existing:
            item_normalized = item.casefold()

            if candidate_normalized in item_normalized or item_normalized in candidate_normalized:
                return True

        return False

    @staticmethod
    def _normalize_text(
        value: str,
    ) -> str:
        return re.sub(
            r"\s+",
            " ",
            value,
        ).strip()
