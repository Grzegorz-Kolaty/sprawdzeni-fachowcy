import re
from dataclasses import dataclass

from bs4 import BeautifulSoup, NavigableString


@dataclass(frozen=True)
class ClaimCandidate:
    claim_type: str
    claimed_entity: str | None
    normalized_entity: str | None
    claim_text: str
    evidence_candidate_url: str | None = None


class ClaimDetector:
    _AUTHORIZATION_PATTERNS = (
        re.compile(
            r"""
            \b
            (?:jesteśmy\s+)?
            (?:
                certyfikowanym?
                |
                autoryzowanym?
            )
            \s+
            (?:
                wykonawcą
                | wykonawca
                | partnerem
                | partner
                | serwisem
                | serwis
                | instalatorem
                | instalator
                | dealerem
                | dealer
            )
            \s+
            (?P<entity>.+?)
            [.!]?
            $
            """,
            re.IGNORECASE | re.VERBOSE,
        ),
        re.compile(
            r"""
            \b
            posiada
            \s+
            certyfikat
            \s+
            (?:
                autoryzowanego
                |
                certyfikowanego
            )
            \s+
            (?:
                wykonawcy
                | partnera
                | serwisu
                | instalatora
                | dealera
            )
            \s+
            (?P<entity>.+?)
            [.!]?
            $
            """,
            re.IGNORECASE | re.VERBOSE,
        ),
        re.compile(
            r"""
            \b
            (?:
                authorized
                |
                certified
            )
            \s+
            (?:
                contractor
                | partner
                | installer
                | dealer
                | service
            )
            \s+
            (?P<entity>.+?)
            [.!]?
            $
            """,
            re.IGNORECASE | re.VERBOSE,
        ),
    )

    _MEMBERSHIP_PATTERNS = (
        re.compile(
            r"""
            \b
            jesteśmy
            \s+
            członkiem
            \s+
            (?P<entity>.+?)
            [.!]?
            $
            """,
            re.IGNORECASE | re.VERBOSE,
        ),
        re.compile(
            r"""
            \b
            (?:firma\s+.+?\s+)?
            należy
            \s+
            do
            \s+
            (?P<entity>.+?)
            [.!]?
            $
            """,
            re.IGNORECASE | re.VERBOSE,
        ),
        re.compile(
            r"""
            \b
            member
            \s+
            of
            \s+
            (?P<entity>.+?)
            [.!]?
            $
            """,
            re.IGNORECASE | re.VERBOSE,
        ),
    )

    def detect(
        self,
        html: str,
        *,
        source_url: str,
    ) -> list[ClaimCandidate]:
        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        candidates: list[ClaimCandidate] = []

        for text_node in soup.find_all(string=True):
            if not isinstance(
                text_node,
                NavigableString,
            ):
                continue

            text = self._normalize_text(str(text_node))

            if not text:
                continue

            candidate = self.detect_text(text)

            if candidate is not None:
                candidates.append(candidate)

        return self._deduplicate(candidates)

    def detect_text(
        self,
        text: str,
    ) -> ClaimCandidate | None:
        for pattern in self._AUTHORIZATION_PATTERNS:
            match = pattern.search(text)

            if match is None:
                continue

            entity = self._clean_entity(match.group("entity"))

            return ClaimCandidate(
                claim_type=("manufacturer_authorization"),
                claimed_entity=entity,
                normalized_entity=(self._normalize_entity(entity)),
                claim_text=text,
            )

        for pattern in self._MEMBERSHIP_PATTERNS:
            match = pattern.search(text)

            if match is None:
                continue

            entity = self._clean_entity(match.group("entity"))

            return ClaimCandidate(
                claim_type=("organization_membership"),
                claimed_entity=entity,
                normalized_entity=(self._normalize_entity(entity)),
                claim_text=text,
            )

        return None

    @staticmethod
    def _normalize_text(
        value: str,
    ) -> str:
        return re.sub(
            r"\s+",
            " ",
            value,
        ).strip()

    @staticmethod
    def _clean_entity(
        value: str,
    ) -> str | None:
        entity = re.sub(
            r"\s+",
            " ",
            value,
        ).strip(" \t\r\n.,;:–—-|")

        if not entity:
            return None

        if len(entity) > 255:
            entity = entity[:255].rstrip()

        return entity

    @staticmethod
    def _normalize_entity(
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        normalized = (
            re.sub(
                r"\s+",
                " ",
                value,
            )
            .strip()
            .casefold()
        )

        return normalized or None

    @staticmethod
    def _deduplicate(
        candidates: list[ClaimCandidate],
    ) -> list[ClaimCandidate]:
        result: list[ClaimCandidate] = []

        seen: set[
            tuple[
                str,
                str | None,
            ]
        ] = set()

        for candidate in candidates:
            key = (
                candidate.claim_type,
                candidate.normalized_entity,
            )

            if key in seen:
                continue

            seen.add(key)
            result.append(candidate)

        return result
