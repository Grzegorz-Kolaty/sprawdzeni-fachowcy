from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Date,
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


class CompanyCredential(Base):
    __tablename__ = "company_credentials"

    __table_args__ = (
        UniqueConstraint(
            "provider",
            "credential_number",
            name="uq_company_credentials_provider_credential_number",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        index=True,
    )

    source_id: Mapped[int] = mapped_column(
        ForeignKey("sources.id", ondelete="RESTRICT"),
        index=True,
    )

    provider: Mapped[str] = mapped_column(
        String(50),
    )

    credential_type: Mapped[str] = mapped_column(
        String(100),
    )

    issuer: Mapped[str] = mapped_column(
        String(255),
    )

    credential_number: Mapped[str] = mapped_column(
        String(100),
    )

    status: Mapped[str] = mapped_column(
        String(100),
    )

    scope: Mapped[str | None] = mapped_column(
        Text,
    )

    issued_at: Mapped[date | None] = mapped_column(
        Date,
    )

    valid_until: Mapped[date | None] = mapped_column(
        Date,
    )

    status_changed_at: Mapped[date | None] = mapped_column(
        Date,
    )

    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    company: Mapped[Company] = relationship(
        back_populates="credentials",
    )

    source: Mapped[Source] = relationship()
