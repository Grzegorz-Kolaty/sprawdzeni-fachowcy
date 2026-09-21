from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.brand import Brand
from app.models.company_website import CompanyWebsite
from app.repositories.brand import get_company_brands
from app.repositories.company_website import get_company_websites
from app.schemas.brand import BrandCreate, BrandRead
from app.schemas.company_website import (
    CompanyWebsiteCreate,
    CompanyWebsiteRead,
)
from app.services.brand import (
    BrandAlreadyExistsError,
    create_brand_service,
)
from app.services.brand import (
    CompanyNotFoundError as BrandCompanyNotFoundError,
)
from app.services.company_website import (
    BrandDoesNotBelongToCompanyError,
    BrandNotFoundError,
    WebsiteAlreadyExistsError,
    create_company_website_service,
)
from app.services.company_website import (
    CompanyNotFoundError as WebsiteCompanyNotFoundError,
)

router = APIRouter(
    prefix="/api/companies",
    tags=["company identity"],
)


@router.post(
    "/{company_id}/brands",
    response_model=BrandRead,
    status_code=status.HTTP_201_CREATED,
)
def create_brand(
    company_id: int,
    data: BrandCreate,
    db: Session = Depends(get_db),
) -> Brand:
    try:
        return create_brand_service(db, company_id, data)

    except BrandCompanyNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except BrandAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get(
    "/{company_id}/brands",
    response_model=list[BrandRead],
)
def list_brands(
    company_id: int,
    db: Session = Depends(get_db),
) -> list[Brand]:
    return get_company_brands(db, company_id)


@router.post(
    "/{company_id}/websites",
    response_model=CompanyWebsiteRead,
    status_code=status.HTTP_201_CREATED,
)
def create_website(
    company_id: int,
    data: CompanyWebsiteCreate,
    db: Session = Depends(get_db),
) -> CompanyWebsite:
    try:
        return create_company_website_service(
            db,
            company_id,
            data,
        )

    except (
        WebsiteCompanyNotFoundError,
        BrandNotFoundError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except BrandDoesNotBelongToCompanyError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    except WebsiteAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get(
    "/{company_id}/websites",
    response_model=list[CompanyWebsiteRead],
)
def list_websites(
    company_id: int,
    db: Session = Depends(get_db),
) -> list[CompanyWebsite]:
    return get_company_websites(db, company_id)
