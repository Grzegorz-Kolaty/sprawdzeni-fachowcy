from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.claim import ClaimEvidence


def upsert_claim_evidence(
    db: Session,
    *,
    claim_id: int,
    evidence_id: int,
    relation: str,
    confidence: str,
) -> ClaimEvidence:
    statement = select(ClaimEvidence).where(
        ClaimEvidence.claim_id == claim_id,
        ClaimEvidence.evidence_id == evidence_id,
    )

    existing = db.scalar(statement)

    if existing is not None:
        existing.relation = relation
        existing.confidence = confidence

        return existing

    link = ClaimEvidence(
        claim_id=claim_id,
        evidence_id=evidence_id,
        relation=relation,
        confidence=confidence,
    )

    db.add(link)

    db.flush()

    return link
