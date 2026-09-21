import hashlib
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.claim import Claim
from app.providers.claim_detection import ClaimCandidate


def build_claim_fingerprint(
    candidate: ClaimCandidate,
) -> str:
    semantic_value = candidate.normalized_entity or candidate.claim_text.casefold().strip()

    raw = f"{candidate.claim_type}\0{semantic_value}"

    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_claim_by_fingerprint(
    db: Session,
    *,
    company_id: int,
    source_id: int,
    fingerprint: str,
) -> Claim | None:
    statement = select(Claim).where(
        Claim.company_id == company_id,
        Claim.source_id == source_id,
        Claim.fingerprint == fingerprint,
    )

    return db.scalar(statement)


def upsert_claim(
    db: Session,
    *,
    company_id: int,
    source_id: int,
    candidate: ClaimCandidate,
) -> Claim:
    fingerprint = build_claim_fingerprint(candidate)

    claim = get_claim_by_fingerprint(
        db,
        company_id=company_id,
        source_id=source_id,
        fingerprint=fingerprint,
    )

    if claim is not None:
        claim.last_observed_at = datetime.now(UTC)

        claim.claimed_entity = candidate.claimed_entity

        claim.normalized_entity = candidate.normalized_entity

        claim.evidence_candidate_url = candidate.evidence_candidate_url

        # Jeżeli znaleźliśmy bardziej opisową wersję
        # tej samej deklaracji, zachowujemy ją.
        if len(candidate.claim_text) > len(claim.claim_text):
            claim.claim_text = candidate.claim_text

        return claim

    claim = Claim(
        company_id=company_id,
        source_id=source_id,
        claim_type=candidate.claim_type,
        claimed_entity=candidate.claimed_entity,
        normalized_entity=candidate.normalized_entity,
        claim_text=candidate.claim_text,
        evidence_candidate_url=candidate.evidence_candidate_url,
        fingerprint=fingerprint,
        status="unverified",
    )

    db.add(claim)
    db.flush()

    return claim


def get_claim(
    db: Session,
    claim_id: int,
) -> Claim | None:
    return db.get(
        Claim,
        claim_id,
    )
