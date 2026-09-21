from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.company import Company
from app.repositories.company import create_company
from app.schemas.company import CompanyCreate


class CompanyAlreadyExistsError(Exception):
    pass


def create_company_service(
    db: Session,
    data: CompanyCreate,
) -> Company:
    try:
        return create_company(db, data)
    except IntegrityError as exc:
        db.rollback()

        raise CompanyAlreadyExistsError("Company with provided identifiers already exists") from exc
