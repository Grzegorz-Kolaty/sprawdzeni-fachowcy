from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.brand import Brand
from app.repositories.brand import create_brand
from app.repositories.company import get_company
from app.schemas.brand import BrandCreate


class CompanyNotFoundError(Exception):
    pass


class BrandAlreadyExistsError(Exception):
    pass


def create_brand_service(
    db: Session,
    company_id: int,
    data: BrandCreate,
) -> Brand:
    company = get_company(db, company_id)

    if company is None:
        raise CompanyNotFoundError(f"Company {company_id} does not exist")

    try:
        return create_brand(
            db,
            company_id=company_id,
            name=data.name,
        )
    except IntegrityError as exc:
        db.rollback()

        raise BrandAlreadyExistsError("Brand already exists for this company") from exc
