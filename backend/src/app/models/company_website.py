from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.brand import Brand
    from app.models.company import Company


class CompanyWebsite(Base):
    __tablename__ = "company_websites"

    id: Mapped[int] = mapped_column(primary_key=True)

    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        index=True,
    )

    brand_id: Mapped[int | None] = mapped_column(
        ForeignKey("brands.id", ondelete="SET NULL"),
        index=True,
    )

    domain: Mapped[str] = mapped_column(
        String(253),
        unique=True,
    )

    canonical_url: Mapped[str] = mapped_column(
        String(2048),
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
        back_populates="websites",
    )

    brand: Mapped[Brand | None] = relationship(
        back_populates="websites",
    )
