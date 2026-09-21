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
    from app.models.source import Source


class Evidence(Base):
    __tablename__ = "evidence"

    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "source_id",
            "evidence_type",
            "normalized_value",
            name="uq_evidence_company_source_type_value",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

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
            ondelete="CASCADE",
        ),
        index=True,
    )

    evidence_type: Mapped[str] = mapped_column(
        String(100),
    )

    observed_value: Mapped[str | None] = mapped_column(
        Text,
    )

    normalized_value: Mapped[str | None] = mapped_column(
        Text,
    )

    confidence: Mapped[str] = mapped_column(
        String(20),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    last_observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    company: Mapped[Company] = relationship(
        back_populates="evidence",
    )

    source: Mapped[Source] = relationship()
