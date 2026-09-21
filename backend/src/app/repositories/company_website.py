from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.company_website import CompanyWebsite


def create_company_website(
    db: Session,
    *,
    company_id: int,
    brand_id: int | None,
    domain: str,
    canonical_url: str,
) -> CompanyWebsite:
    website = CompanyWebsite(
        company_id=company_id,
        brand_id=brand_id,
        domain=domain,
        canonical_url=canonical_url,
    )

    db.add(website)
    db.commit()
    db.refresh(website)

    return website


def get_company_websites(
    db: Session,
    company_id: int,
) -> list[CompanyWebsite]:
    statement = (
        select(CompanyWebsite)
        .where(CompanyWebsite.company_id == company_id)
        .order_by(CompanyWebsite.id)
    )

    return list(db.scalars(statement).all())


def get_company_website(
    db: Session,
    website_id: int,
) -> CompanyWebsite | None:
    return db.get(CompanyWebsite, website_id)
