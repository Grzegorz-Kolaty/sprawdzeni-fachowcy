import re
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from app.repositories.company import (
    get_company,
)
from app.repositories.company_website import (
    get_company_website,
)
from app.repositories.evidence import (
    add_evidence,
)
from app.repositories.source import (
    get_or_create_source,
)
from app.schemas.verification import (
    WebsiteIdentityVerificationCreate,
    WebsiteIdentityVerificationRead,
)


class CompanyNotFoundError(Exception):
    pass


class WebsiteNotFoundError(Exception):
    pass


class WebsiteDoesNotBelongToCompanyError(Exception):
    pass


class SourceDoesNotBelongToWebsiteError(Exception):
    pass


class InvalidObservedNipError(Exception):
    pass


def normalize_nip(
    value: str,
) -> str:
    normalized = re.sub(
        r"\D",
        "",
        value,
    )

    if len(normalized) != 10:
        raise InvalidObservedNipError("Observed NIP must contain exactly 10 digits")

    return normalized


def normalize_hostname(
    hostname: str,
) -> str:
    hostname = hostname.lower().rstrip(".")

    if hostname.startswith("www."):
        hostname = hostname[4:]

    return hostname


def verify_website_identity(
    db: Session,
    *,
    company_id: int,
    website_id: int,
    data: WebsiteIdentityVerificationCreate,
) -> WebsiteIdentityVerificationRead:
    company = get_company(
        db,
        company_id,
    )

    if company is None:
        raise CompanyNotFoundError(f"Company {company_id} does not exist")

    website = get_company_website(
        db,
        website_id,
    )

    if website is None:
        raise WebsiteNotFoundError(f"Website {website_id} does not exist")

    if website.company_id != company_id:
        raise (WebsiteDoesNotBelongToCompanyError("Website does not belong to this company"))

    source_url = str(data.source_url)

    source_hostname = urlsplit(source_url).hostname

    if source_hostname is None:
        raise (SourceDoesNotBelongToWebsiteError("Source URL has no hostname"))

    source_hostname = normalize_hostname(source_hostname)

    website_domain = normalize_hostname(website.domain)

    if source_hostname != website_domain and not source_hostname.endswith(f".{website_domain}"):
        raise (
            SourceDoesNotBelongToWebsiteError(
                "Source URL does not belong to the verified website domain"
            )
        )

    normalized_nip = normalize_nip(data.observed_nip)

    matches = normalized_nip == company.nip

    evidence_type = "website_company_nip_match" if matches else ("website_company_nip_conflict")

    source = get_or_create_source(
        db,
        url=source_url,
        source_type=("company_website"),
        title=data.title,
    )

    db.flush()

    evidence = add_evidence(
        db,
        company_id=company.id,
        source_id=source.id,
        evidence_type=evidence_type,
        observed_value=(data.observed_nip),
        normalized_value=(normalized_nip),
        confidence="strong",
    )

    db.commit()

    db.refresh(source)

    db.refresh(evidence)

    return WebsiteIdentityVerificationRead(
        company_id=company.id,
        website_id=website.id,
        source_id=source.id,
        evidence_id=evidence.id,
        source_url=source.url,
        company_nip=company.nip,
        observed_nip=(data.observed_nip),
        normalized_nip=(normalized_nip),
        matches=matches,
        evidence_type=(evidence.evidence_type),
        confidence=(evidence.confidence),
    )
