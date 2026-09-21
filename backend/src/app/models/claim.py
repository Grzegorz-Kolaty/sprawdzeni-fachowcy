from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.company import Company
    from app.models.evidence import Evidence
    from app.models.source import Source


class Claim(Base):
    __tablename__ = "claims"

    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "source_id",
            "fingerprint",
            name="uq_claims_company_source_fingerprint",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    company_id: Mapped[int] = mapped_column(
        ForeignKey(
            "companies.id",
            ondelete="CASCADE",
        ),
        index=True,
    )

    source_id: Mapped[int] = mapped_column(
        ForeignKey(
            "sources.id",
            ondelete="RESTRICT",
        ),
        index=True,
    )

    claim_type: Mapped[str] = mapped_column(
        String(100),
        index=True,
    )

    claimed_entity: Mapped[str | None] = mapped_column(
        String(255),
    )

    normalized_entity: Mapped[str | None] = mapped_column(
        String(255),
    )

    claim_text: Mapped[str] = mapped_column(
        Text,
    )

    evidence_candidate_url: Mapped[str | None] = mapped_column(
        Text,
    )

    fingerprint: Mapped[str] = mapped_column(
        String(64),
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default="unverified",
        server_default="unverified",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    last_observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    company: Mapped[Company] = relationship(
        back_populates="claims",
    )

    source: Mapped[Source] = relationship()

    evidence_links: Mapped[list[ClaimEvidence]] = relationship(
        back_populates="claim",
        cascade="all, delete-orphan",
    )


class ClaimEvidence(Base):
    __tablename__ = "claim_evidence"

    __table_args__ = (
        UniqueConstraint(
            "claim_id",
            "evidence_id",
            name="uq_claim_evidence_claim_evidence",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    claim_id: Mapped[int] = mapped_column(
        ForeignKey(
            "claims.id",
            ondelete="CASCADE",
        ),
        index=True,
    )

    evidence_id: Mapped[int] = mapped_column(
        ForeignKey(
            "evidence.id",
            ondelete="CASCADE",
        ),
        index=True,
    )

    relation: Mapped[str] = mapped_column(
        String(20),
    )

    confidence: Mapped[str] = mapped_column(
        String(20),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    claim: Mapped[Claim] = relationship(
        back_populates="evidence_links",
    )

    evidence: Mapped[Evidence] = relationship()
