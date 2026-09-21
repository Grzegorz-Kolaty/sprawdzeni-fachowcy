from urllib.parse import urlsplit

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.company_website import CompanyWebsite
from app.repositories.brand import get_brand
from app.repositories.company import get_company
from app.repositories.company_website import create_company_website
from app.schemas.company_website import CompanyWebsiteCreate


class CompanyNotFoundError(Exception):
    pass


class BrandNotFoundError(Exception):
    pass


class BrandDoesNotBelongToCompanyError(Exception):
    pass


class WebsiteAlreadyExistsError(Exception):
    pass


def create_company_website_service(
    db: Session,
    company_id: int,
    data: CompanyWebsiteCreate,
) -> CompanyWebsite:
    company = get_company(db, company_id)

    if company is None:
        raise CompanyNotFoundError(f"Company {company_id} does not exist")

    if data.brand_id is not None:
        brand = get_brand(db, data.brand_id)

        if brand is None:
            raise BrandNotFoundError(f"Brand {data.brand_id} does not exist")

        if brand.company_id != company_id:
            raise BrandDoesNotBelongToCompanyError("Brand does not belong to this company")

    canonical_url = str(data.canonical_url)

    hostname = urlsplit(canonical_url).hostname

    if hostname is None:
        raise ValueError("Website URL has no hostname")

    domain = hostname.lower()

    try:
        return create_company_website(
            db,
            company_id=company_id,
            brand_id=data.brand_id,
            domain=domain,
            canonical_url=canonical_url,
        )
    except IntegrityError as exc:
        db.rollback()

        raise WebsiteAlreadyExistsError("Website already exists") from exc
