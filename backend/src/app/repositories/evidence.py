from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.evidence import Evidence


def add_evidence(
    db: Session,
    *,
    company_id: int,
    source_id: int,
    evidence_type: str,
    observed_value: str | None,
    normalized_value: str | None,
    confidence: str,
) -> Evidence:
    statement = select(Evidence).where(
        Evidence.company_id == company_id,
        Evidence.source_id == source_id,
        Evidence.evidence_type == evidence_type,
        Evidence.normalized_value == normalized_value,
    )

    evidence = db.scalar(statement)

    if evidence is not None:
        evidence.observed_value = observed_value
        evidence.confidence = confidence
        evidence.last_observed_at = datetime.now(UTC)

        return evidence

    evidence = Evidence(
        company_id=company_id,
        source_id=source_id,
        evidence_type=evidence_type,
        observed_value=observed_value,
        normalized_value=normalized_value,
        confidence=confidence,
    )

    db.add(evidence)

    return evidence


def get_company_evidence(
    db: Session,
    company_id: int,
) -> list[Evidence]:
    statement = (
        select(Evidence)
        .where(Evidence.company_id == company_id)
        .options(
            selectinload(Evidence.source),
        )
        .order_by(Evidence.last_observed_at.desc())
    )

    return list(db.scalars(statement).all())
