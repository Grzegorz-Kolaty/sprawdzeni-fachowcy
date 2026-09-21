from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.brand import Brand


def create_brand(
    db: Session,
    company_id: int,
    name: str,
) -> Brand:
    brand = Brand(
        company_id=company_id,
        name=name,
    )

    db.add(brand)
    db.commit()
    db.refresh(brand)

    return brand


def get_brand(
    db: Session,
    brand_id: int,
) -> Brand | None:
    return db.get(Brand, brand_id)


def get_company_brands(
    db: Session,
    company_id: int,
) -> list[Brand]:
    statement = select(Brand).where(Brand.company_id == company_id).order_by(Brand.id)

    return list(db.scalars(statement).all())
