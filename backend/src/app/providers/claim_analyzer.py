from dataclasses import replace

from app.providers.claim_context import (
    ClaimContextExtractor,
)
from app.providers.claim_detection import (
    ClaimCandidate,
    ClaimDetector,
)


class ClaimAnalyzer:
    def __init__(self) -> None:
        self._detector = ClaimDetector()
        self._context_extractor = ClaimContextExtractor()

    def analyze(
        self,
        html: str,
        *,
        source_url: str,
    ) -> list[ClaimCandidate]:
        candidates = self._detector.detect(
            html,
            source_url=source_url,
        )

        result: list[ClaimCandidate] = []

        for candidate in candidates:
            self._context_extractor.extract_best(
                html,
                source_url=source_url,
                claim_text=candidate.claim_text,
                claimed_entity=candidate.claimed_entity,
            )

            result.append(
                replace(
                    candidate,
                    evidence_candidate_url=None,
                )
            )

        return result
