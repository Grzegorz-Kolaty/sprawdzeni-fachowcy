from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.company import Company
from app.schemas.company import CompanyCreate


def create_company(
    db: Session,
    data: CompanyCreate,
) -> Company:
    company = Company(
        legal_name=data.legal_name,
        nip=data.nip,
        regon=data.regon,
        krs=data.krs,
    )

    db.add(company)
    db.commit()
    db.refresh(company)

    return company


def get_companies(db: Session) -> list[Company]:
    statement = select(Company).order_by(Company.id)

    return list(db.scalars(statement).all())


def get_company(
    db: Session,
    company_id: int,
) -> Company | None:
    return db.get(Company, company_id)
