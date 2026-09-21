from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.company import Company
from app.repositories.company import get_companies
from app.schemas.company import CompanyCreate, CompanyRead
from app.services.company import (
    CompanyAlreadyExistsError,
    create_company_service,
)

router = APIRouter(
    prefix="/api/companies",
    tags=["companies"],
)


@router.post(
    "",
    response_model=CompanyRead,
    status_code=status.HTTP_201_CREATED,
)
def create(
    data: CompanyCreate,
    db: Session = Depends(get_db),
) -> Company:
    try:
        return create_company_service(db, data)
    except CompanyAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get(
    "",
    response_model=list[CompanyRead],
)
def list_companies(
    db: Session = Depends(get_db),
) -> list[Company]:
    return get_companies(db)
