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


class ManufacturerAuthorization(Base):
    __tablename__ = "manufacturer_authorizations"

    __table_args__ = (
        UniqueConstraint(
            "manufacturer",
            "source_id",
            "external_name",
            name="uq_manufacturer_authorizations_manufacturer_source_name",
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
            ondelete="RESTRICT",
        ),
        index=True,
    )

    manufacturer: Mapped[str] = mapped_column(
        String(100),
    )

    authorization_type: Mapped[str] = mapped_column(
        String(100),
    )

    authorization_level: Mapped[str | None] = mapped_column(
        String(100),
    )

    external_name: Mapped[str] = mapped_column(
        String(255),
    )

    scope: Mapped[str | None] = mapped_column(
        Text,
    )

    website_url: Mapped[str | None] = mapped_column(
        Text,
    )

    email: Mapped[str | None] = mapped_column(
        String(320),
    )

    phone: Mapped[str | None] = mapped_column(
        String(50),
    )

    address: Mapped[str | None] = mapped_column(
        Text,
    )

    match_method: Mapped[str] = mapped_column(
        String(50),
    )

    match_confidence: Mapped[str] = mapped_column(
        String(20),
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
        back_populates="manufacturer_authorizations",
    )

    source: Mapped[Source] = relationship()
