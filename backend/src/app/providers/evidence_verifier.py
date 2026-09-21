import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

from app.providers.evidence_candidate_context import EvidenceCandidateContext
from app.providers.evidence_candidate_evaluator import EvidenceCandidateEvaluation

EvidenceVerificationStatus = Literal[
    "verified",
    "conflicted",
    "unverified",
]


_POLISH_TRANSLATION = str.maketrans(
    {
        "ł": "l",
        "Ł": "L",
    }
)


_RELATION_STEMS: dict[str, set[str]] = {
    "manufacturer_authorization": {
        "autoryz",
        "certyfik",
        "partner",
        "wykonawc",
        "contractor",
        "instalat",
        "installer",
        "dealer",
        "serwis",
        "service",
    },
    "organization_membership": {
        "czlonk",
        "nalezy",
        "member",
        "membership",
        "stowarzysz",
        "association",
        "izb",
        "chamber",
        "organizac",
    },
}


_NEGATIVE_STEMS = {
    "cofniet",
    "cofnieto",
    "cofniety",
    "cofnieta",
    "wygasl",
    "wygasla",
    "wygaslo",
    "wygas",
    "revoked",
    "expired",
    "suspended",
    "zawieszon",
    "utracil",
    "utracila",
}


_GENERIC_COMPANY_TOKENS = {
    "firma",
    "usluga",
    "uslugi",
    "budowlana",
    "budowlane",
    "budowlany",
    "polska",
    "poland",
    "spolka",
    "sp",
    "zoo",
    "sa",
}


@dataclass(frozen=True)
class EvidenceVerificationDecision:
    status: EvidenceVerificationStatus
    confidence: float
    reasons: tuple[str, ...]
    supporting_snippet: str | None


class EvidenceVerifier:
    def verify(
        self,
        *,
        context: EvidenceCandidateContext,
        evaluation: EvidenceCandidateEvaluation,
        claim_type: str,
        claimed_entity: str | None,
        company_names: list[str],
    ) -> EvidenceVerificationDecision:
        if not evaluation.independent_source:
            return self._unverified("source_is_not_independent")

        if not claimed_entity:
            return self._unverified("claimed_entity_missing")

        local_windows = self._build_local_windows(context)

        company_phrases = self._company_phrases(
            company_names=company_names,
            evaluation=evaluation,
        )

        best_support: str | None = None

        for window in local_windows:
            company_match = self._matches_company(
                window,
                company_names,
                company_phrases=company_phrases,
            )

            if not company_match:
                continue

            entity_match = self._matches_entity(
                window,
                claimed_entity,
            )

            if not entity_match:
                continue

            negative_terms = self._find_stems(
                window,
                _NEGATIVE_STEMS,
            )

            if negative_terms:
                return EvidenceVerificationDecision(
                    status="conflicted",
                    confidence=0.95,
                    reasons=(
                        "independent_source",
                        "company_found_locally",
                        "entity_found_locally",
                        "local_negative_relation",
                        "negative_terms:" + ",".join(sorted(negative_terms)),
                    ),
                    supporting_snippet=window,
                )

            relation_terms = self._find_relation_terms(
                window,
                claim_type=claim_type,
            )

            if not relation_terms:
                continue

            best_support = window
            break

        if best_support is None:
            return self._unverified("no_local_company_entity_relation_match")

        if evaluation.classification != "potentially_supports":
            return self._unverified(
                "candidate_not_classified_as_supporting",
                supporting_snippet=best_support,
            )

        return EvidenceVerificationDecision(
            status="verified",
            confidence=self._support_confidence(evaluation),
            reasons=(
                "independent_source",
                "company_found_locally",
                "entity_found_locally",
                "relation_found_locally",
            ),
            supporting_snippet=best_support,
        )

    @staticmethod
    def _build_local_windows(
        context: EvidenceCandidateContext,
    ) -> tuple[str, ...]:
        snippets = [snippet.strip() for snippet in context.snippets if snippet.strip()]

        windows: list[str] = []
        seen: set[str] = set()

        #
        # Najpierw pojedyncze snippety.
        #
        for snippet in snippets:
            if snippet in seen:
                continue

            seen.add(snippet)
            windows.append(snippet)

        #
        # Potem pary sąsiednich snippetów.
        #
        # ContextBuilder może rozdzielić nagłówek programu
        # i konkretną firmę na dwa sąsiednie okna.
        #
        for index in range(len(snippets) - 1):
            combined = snippets[index] + " " + snippets[index + 1]

            if combined in seen:
                continue

            seen.add(combined)
            windows.append(combined)

        return tuple(windows)

    def _company_phrases(
        self,
        *,
        company_names: list[str],
        evaluation: EvidenceCandidateEvaluation,
    ) -> set[str]:
        phrases = {
            self._normalize_text(company_name)
            for company_name in company_names
            if company_name.strip()
        }

        signal_prefix = "company_abbreviated_prefix:"

        for signal in evaluation.signals:
            if not signal.startswith(signal_prefix):
                continue

            abbreviated_name = signal.removeprefix(signal_prefix).strip()

            if not abbreviated_name:
                continue

            normalized = self._normalize_text(abbreviated_name)

            if not normalized:
                continue

            tokens = normalized.split()

            #
            # Nie ufamy ślepo sygnałowi evaluatora.
            # Skrócona forma nadal musi mieć minimum trzy słowa
            # oraz przynajmniej jeden charakterystyczny token.
            #
            if len(tokens) < 3:
                continue

            distinctive_tokens = {
                token
                for token in tokens
                if len(token) >= 3 and token not in _GENERIC_COMPANY_TOKENS
            }

            if not distinctive_tokens:
                continue

            phrases.add(normalized)

        return phrases

    def _matches_company(
        self,
        value: str,
        company_names: list[str],
        *,
        company_phrases: set[str],
    ) -> bool:
        normalized_value = self._normalize_text(value)

        #
        # Najpierw dokładne lokalne dopasowanie pełnej nazwy
        # albo bezpiecznego skrótu zaakceptowanego przez evaluator.
        #
        if any(phrase and phrase in normalized_value for phrase in company_phrases):
            return True

        value_tokens = set(normalized_value.split())

        #
        # Zachowujemy wcześniejszy fallback oparty na
        # charakterystycznych tokenach pełnej nazwy.
        #
        for company_name in company_names:
            normalized_name = self._normalize_text(company_name)

            if not normalized_name:
                continue

            company_tokens = {
                token
                for token in normalized_name.split()
                if len(token) >= 3 and token not in _GENERIC_COMPANY_TOKENS
            }

            if not company_tokens:
                continue

            matched = {
                company_token
                for company_token in company_tokens
                if any(
                    self._tokens_related(
                        company_token,
                        value_token,
                    )
                    for value_token in value_tokens
                )
            }

            if matched == company_tokens:
                return True

        return False

    def _matches_entity(
        self,
        value: str,
        claimed_entity: str,
    ) -> bool:
        normalized_value = self._normalize_text(value)

        normalized_entity = self._normalize_text(claimed_entity)

        if not normalized_entity:
            return False

        if normalized_entity in normalized_value:
            return True

        value_tokens = set(normalized_value.split())

        entity_tokens = set(normalized_entity.split())

        if not entity_tokens:
            return False

        matched = {
            entity_token
            for entity_token in entity_tokens
            if any(
                self._tokens_related(
                    entity_token,
                    value_token,
                )
                for value_token in value_tokens
            )
        }

        return matched == entity_tokens

    def _find_relation_terms(
        self,
        value: str,
        *,
        claim_type: str,
    ) -> set[str]:
        stems = _RELATION_STEMS.get(
            claim_type,
            set(),
        )

        if not stems:
            return set()

        return self._find_stems(
            value,
            stems,
        )

    def _find_stems(
        self,
        value: str,
        stems: set[str],
    ) -> set[str]:
        normalized = self._normalize_text(value)

        tokens = set(normalized.split())

        return {stem for stem in stems if any(token.startswith(stem) for token in tokens)}

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

        return common_prefix_length >= 7

    @staticmethod
    def _support_confidence(
        evaluation: EvidenceCandidateEvaluation,
    ) -> float:
        average = (
            evaluation.company_score + evaluation.entity_score + evaluation.relation_score
        ) / 3

        return round(
            min(
                0.95,
                max(
                    0.75,
                    average / 100,
                ),
            ),
            2,
        )

    @staticmethod
    def _unverified(
        reason: str,
        *,
        supporting_snippet: str | None = None,
    ) -> EvidenceVerificationDecision:
        return EvidenceVerificationDecision(
            status="unverified",
            confidence=0.0,
            reasons=(reason,),
            supporting_snippet=supporting_snippet,
        )

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
