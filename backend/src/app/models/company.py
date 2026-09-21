from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.brand import Brand
    from app.models.claim import Claim
    from app.models.company_credential import CompanyCredential
    from app.models.company_website import CompanyWebsite
    from app.models.evidence import Evidence
    from app.models.manufacturer_authorization import ManufacturerAuthorization


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)

    legal_name: Mapped[str] = mapped_column(
        String(255),
    )

    nip: Mapped[str] = mapped_column(
        String(10),
        unique=True,
    )

    regon: Mapped[str | None] = mapped_column(
        String(14),
        unique=True,
    )

    krs: Mapped[str | None] = mapped_column(
        String(10),
        unique=True,
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

    brands: Mapped[list[Brand]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
    )

    websites: Mapped[list[CompanyWebsite]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
    )

    evidence: Mapped[list[Evidence]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
    )

    credentials: Mapped[list[CompanyCredential]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
    )

    manufacturer_authorizations: Mapped[list[ManufacturerAuthorization]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
    )

    claims: Mapped[list[Claim]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
    )
