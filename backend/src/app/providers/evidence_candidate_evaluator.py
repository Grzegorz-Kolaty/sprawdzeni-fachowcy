import re
import unicodedata
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

from app.providers.evidence_candidate_context import (
    EvidenceCandidateContext,
)

EvidenceClassification = Literal[
    "irrelevant",
    "potentially_supports",
    "potentially_contradicts",
    "uncertain",
]


@dataclass(frozen=True)
class EvidenceEvaluationThresholds:
    minimum_company_score: int = 55
    minimum_entity_score: int = 55
    minimum_relation_score: int = 25
    minimum_contradiction_score: int = 40


@dataclass(frozen=True)
class EvidenceCandidateEvaluation:
    classification: EvidenceClassification

    independent_source: bool

    company_score: int
    entity_score: int
    relation_score: int
    contradiction_score: int

    signals: tuple[str, ...]


@dataclass(frozen=True)
class ClaimProfile:
    positive_stems: tuple[str, ...]
    negative_stems: tuple[str, ...]


CLAIM_PROFILES: dict[str, ClaimProfile] = {
    "manufacturer_authorization": ClaimProfile(
        positive_stems=(
            "autoryz",
            "certyfik",
            "authorized",
            "certified",
            "partner",
            "wykonawc",
            "contractor",
            "instalat",
            "installer",
            "dealer",
            "serwis",
            "service",
        ),
        negative_stems=(
            "cofniet",
            "cofnięt",
            "wygasl",
            "wygasł",
            "wygas",
            "revoked",
            "expired",
            "suspended",
            "zawieszon",
            "utracil",
            "utracił",
        ),
    ),
    "organization_membership": ClaimProfile(
        positive_stems=(
            "czlonk",
            "członk",
            "nalezy",
            "należy",
            "member",
            "membership",
            "stowarzysz",
            "association",
            "izb",
            "chamber",
            "organizac",
        ),
        negative_stems=(
            "wykluczon",
            "usuniet",
            "usunięt",
            "rezygn",
            "membership ended",
            "no longer member",
            "suspended",
        ),
    ),
}

_POLISH_TRANSLATION = str.maketrans(
    {
        "ł": "l",
        "Ł": "L",
    }
)

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


class EvidenceCandidateEvaluator:
    def __init__(
        self,
        *,
        thresholds: EvidenceEvaluationThresholds | None = None,
    ) -> None:
        self._thresholds = thresholds or EvidenceEvaluationThresholds()

    def evaluate(
        self,
        *,
        context: EvidenceCandidateContext,
        claim_type: str,
        claim_text: str,
        claimed_entity: str | None,
        company_names: list[str],
        company_domains: list[str] | None = None,
    ) -> EvidenceCandidateEvaluation:
        company_domains = company_domains or []

        corpus = self._build_corpus(context)

        independent_source = self._is_independent_source(
            context.url,
            company_domains=company_domains,
        )

        company_score, company_signals = self._company_score(
            corpus,
            company_names=company_names,
        )

        entity_score, entity_signals = self._entity_score(
            corpus,
            claimed_entity=claimed_entity,
        )

        relation_score, relation_signals = self._relation_score(
            corpus,
            claim_type=claim_type,
            claim_text=claim_text,
        )

        (
            contradiction_score,
            contradiction_signals,
        ) = self._contradiction_score(
            corpus,
            claim_type=claim_type,
        )

        signals = [
            *company_signals,
            *entity_signals,
            *relation_signals,
            *contradiction_signals,
        ]

        if not independent_source:
            signals.append("source_is_company_owned")

        classification = self._classify(
            independent_source=independent_source,
            company_score=company_score,
            entity_score=entity_score,
            relation_score=relation_score,
            contradiction_score=contradiction_score,
        )

        return EvidenceCandidateEvaluation(
            classification=classification,
            independent_source=independent_source,
            company_score=company_score,
            entity_score=entity_score,
            relation_score=relation_score,
            contradiction_score=contradiction_score,
            signals=tuple(signals),
        )

    def _classify(
        self,
        *,
        independent_source: bool,
        company_score: int,
        entity_score: int,
        relation_score: int,
        contradiction_score: int,
    ) -> EvidenceClassification:
        thresholds = self._thresholds

        if not independent_source:
            return "uncertain"

        company_matches = company_score >= thresholds.minimum_company_score

        entity_matches = entity_score >= thresholds.minimum_entity_score

        relation_matches = relation_score >= thresholds.minimum_relation_score

        contradiction_matches = contradiction_score >= thresholds.minimum_contradiction_score

        if company_matches and entity_matches and contradiction_matches:
            return "potentially_contradicts"

        if company_matches and entity_matches and relation_matches:
            return "potentially_supports"

        if company_score == 0 and entity_score == 0:
            return "irrelevant"

        return "uncertain"

    def _company_score(
        self,
        corpus: str,
        *,
        company_names: list[str],
    ) -> tuple[int, list[str]]:
        best_score = 0
        best_signals: list[str] = []

        for company_name in company_names:
            regular_score, regular_signals = self._name_match_score(
                corpus,
                company_name,
                signal_prefix="company",
            )

            (
                abbreviated_score,
                abbreviated_signals,
            ) = self._abbreviated_company_prefix_score(
                corpus,
                company_name,
            )

            if abbreviated_score > regular_score:
                score = abbreviated_score
                signals = abbreviated_signals
            else:
                score = regular_score
                signals = regular_signals

            if score > best_score:
                best_score = score
                best_signals = signals

        return (
            min(
                best_score,
                100,
            ),
            best_signals,
        )

    def _abbreviated_company_prefix_score(
        self,
        corpus: str,
        company_name: str,
    ) -> tuple[int, list[str]]:
        normalized_name = self._normalize_phrase(company_name)

        words = re.findall(
            r"[a-z0-9]+",
            normalized_name,
        )

        if len(words) < 4:
            return 0, []

        minimum_length = max(
            3,
            (len(words) * 3 + 4) // 5,
        )

        for end in range(
            len(words) - 1,
            minimum_length - 1,
            -1,
        ):
            prefix_words = words[:end]

            distinctive_words = [
                word for word in prefix_words if word not in _GENERIC_COMPANY_TOKENS
            ]

            if not distinctive_words:
                continue

            prefix = " ".join(prefix_words)

            if not re.search(
                (
                    rf"(?<![a-z0-9])"
                    rf"{re.escape(prefix)}"
                    rf"(?![a-z0-9])"
                ),
                corpus,
            ):
                continue

            return (
                90,
                [(f"company_abbreviated_prefix:{prefix}")],
            )

        return 0, []

    def _entity_score(
        self,
        corpus: str,
        *,
        claimed_entity: str | None,
    ) -> tuple[int, list[str]]:
        if not claimed_entity:
            return 0, []

        return self._name_match_score(
            corpus,
            claimed_entity,
            signal_prefix="entity",
        )

    def _name_match_score(
        self,
        corpus: str,
        value: str,
        *,
        signal_prefix: str,
    ) -> tuple[int, list[str]]:
        normalized_value = self._normalize_phrase(value)

        if not normalized_value:
            return 0, []

        #
        # Pełna fraza zawsze jest najmocniejszym
        # możliwym dopasowaniem.
        #
        if normalized_value in corpus:
            return (
                100,
                [f"{signal_prefix}_exact_phrase"],
            )

        value_tokens = self._tokens(value)

        #
        # Przy nazwie firmy nie liczymy generycznych
        # określeń jako dowodu tożsamości.
        #
        # Np. samo:
        #
        #   "usługi budowlane"
        #
        # nie może wskazywać firmy:
        #
        #   "BOS USŁUGI BUDOWLANE MICHAŁ OMYŁA"
        #
        if signal_prefix == "company":
            value_tokens = {token for token in value_tokens if token not in _GENERIC_COMPANY_TOKENS}

        if not value_tokens:
            return 0, []

        corpus_tokens = set(self._tokens(corpus))

        matching_tokens = value_tokens & corpus_tokens

        coverage = len(matching_tokens) / len(value_tokens)

        if coverage >= 0.8:
            score = 90
        elif coverage >= 0.6:
            score = 75
        elif coverage >= 0.4:
            score = 55
        elif matching_tokens:
            score = 30
        else:
            score = 0

        signals: list[str] = []

        if matching_tokens:
            signals.append(f"{signal_prefix}_tokens:" + ",".join(sorted(matching_tokens)))

        return score, signals

    def _relation_score(
        self,
        corpus: str,
        *,
        claim_type: str,
        claim_text: str,
    ) -> tuple[int, list[str]]:
        profile = CLAIM_PROFILES.get(claim_type)

        signals: list[str] = []

        if profile is None:
            return self._generic_relation_score(
                corpus,
                claim_text=claim_text,
            )

        matches = {stem for stem in profile.positive_stems if stem in corpus}

        score = min(
            len(matches) * 25,
            100,
        )

        if matches:
            signals.append("relation_terms:" + ",".join(sorted(matches)))

        return score, signals

    def _generic_relation_score(
        self,
        corpus: str,
        *,
        claim_text: str,
    ) -> tuple[int, list[str]]:
        """Score unprofiled claim types by overlap with the claim's own terms.

        This fallback keeps verification generic: it avoids company-specific
        rules while still requiring the evidence page to mention the substance
        of the original claim.
        """
        claim_tokens = self._meaningful_tokens(claim_text)

        if not claim_tokens:
            return 0, []

        corpus_tokens = set(self._tokens(corpus))

        matches = claim_tokens & corpus_tokens

        coverage = len(matches) / len(claim_tokens)

        score = round(coverage * 100)

        signals: list[str] = []

        if matches:
            signals.append("claim_terms:" + ",".join(sorted(matches)))

        return score, signals

    def _contradiction_score(
        self,
        corpus: str,
        *,
        claim_type: str,
    ) -> tuple[int, list[str]]:
        profile = CLAIM_PROFILES.get(claim_type)

        if profile is None:
            return 0, []

        matches = {stem for stem in profile.negative_stems if stem in corpus}

        score = min(
            len(matches) * 40,
            100,
        )

        signals: list[str] = []

        if matches:
            signals.append("negative_terms:" + ",".join(sorted(matches)))

        return score, signals

    def _build_corpus(
        self,
        context: EvidenceCandidateContext,
    ) -> str:
        parts = [
            context.title or "",
            context.description or "",
            *context.snippets,
        ]

        return self._normalize_phrase(" ".join(parts))

    def _is_independent_source(
        self,
        url: str,
        *,
        company_domains: list[str],
    ) -> bool:
        hostname = urlsplit(url).hostname

        if hostname is None:
            return False

        hostname = self._normalize_domain(hostname)

        for company_domain in company_domains:
            normalized_company_domain = self._normalize_domain(company_domain)

            if hostname == normalized_company_domain or hostname.endswith(
                "." + normalized_company_domain
            ):
                return False

        return True

    def _meaningful_tokens(
        self,
        value: str,
    ) -> set[str]:
        ignored = {
            "firma",
            "jest",
            "jestesmy",
            "jesteśmy",
            "posiada",
            "mamy",
            "nasz",
            "nasza",
            "oraz",
            "dla",
            "the",
            "and",
            "with",
        }

        return {token for token in self._tokens(value) if token not in ignored}

    def _tokens(
        self,
        value: str,
    ) -> set[str]:
        normalized = self._normalize_phrase(value)

        raw_tokens = re.findall(
            r"[a-z0-9]+",
            normalized,
        )

        return {self._normalize_token(token) for token in raw_tokens if len(token) >= 3}

    @staticmethod
    def _normalize_token(
        token: str,
    ) -> str:
        #
        # Prosta normalizacja angielskiej
        # liczby mnogiej:
        #
        # system / systems
        # contractor / contractors
        #
        if len(token) > 4 and token.endswith("s") and not token.endswith("ss"):
            token = token[:-1]

        return token

    @staticmethod
    def _normalize_phrase(
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

    @staticmethod
    def _normalize_domain(
        value: str,
    ) -> str:
        value = value.casefold().strip().rstrip(".")

        if value.startswith("www."):
            value = value[4:]

        return value
