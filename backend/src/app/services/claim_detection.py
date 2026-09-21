from urllib.parse import urlsplit

import httpx
from sqlalchemy.orm import Session

from app.providers.claim_analyzer import (
    ClaimAnalyzer,
)
from app.repositories.claim import (
    upsert_claim,
)
from app.repositories.company import (
    get_company,
)
from app.repositories.company_website import (
    get_company_website,
)
from app.repositories.source import (
    get_or_create_source,
)
from app.schemas.claim import (
    ClaimDetectionRead,
    ClaimRead,
)


class CompanyNotFoundError(Exception):
    pass


class WebsiteNotFoundError(Exception):
    pass


class WebsiteDoesNotBelongToCompanyError(Exception):
    pass


class SourceDoesNotBelongToWebsiteError(Exception):
    pass


class ClaimDetectionError(Exception):
    pass


def normalize_hostname(
    hostname: str,
) -> str:
    hostname = hostname.lower().rstrip(".")

    if hostname.startswith("www."):
        hostname = hostname[4:]

    return hostname


def detect_company_claims(
    db: Session,
    *,
    company_id: int,
    website_id: int,
    source_url: str,
) -> ClaimDetectionRead:
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

    if website.company_id != company.id:
        raise (WebsiteDoesNotBelongToCompanyError("Website does not belong to this company"))

    hostname = urlsplit(source_url).hostname

    if hostname is None:
        raise (SourceDoesNotBelongToWebsiteError("Source URL has no hostname"))

    source_hostname = normalize_hostname(hostname)

    website_domain = normalize_hostname(website.domain)

    if source_hostname != website_domain and not source_hostname.endswith(f".{website_domain}"):
        raise (
            SourceDoesNotBelongToWebsiteError("Source URL does not belong to the company website")
        )

    try:
        with httpx.Client(
            timeout=15.0,
            follow_redirects=True,
            headers={
                "User-Agent": ("SprawdzeniFachowcy/0.1 (company claim discovery)"),
            },
        ) as client:
            response = client.get(source_url)

            response.raise_for_status()

    except httpx.HTTPError as exc:
        raise ClaimDetectionError("Could not fetch company website") from exc

    analyzer = ClaimAnalyzer()

    candidates = analyzer.analyze(
        response.text,
        source_url=source_url,
    )

    source = get_or_create_source(
        db,
        url=source_url,
        source_type=("company_website"),
        title=None,
    )

    db.flush()

    claims = [
        upsert_claim(
            db,
            company_id=company.id,
            source_id=source.id,
            candidate=candidate,
        )
        for candidate in candidates
    ]

    db.commit()

    for claim in claims:
        db.refresh(claim)

    return ClaimDetectionRead(
        company_id=company.id,
        website_id=website.id,
        source_url=source.url,
        detected_count=len(claims),
        claims=[ClaimRead.model_validate(claim) for claim in claims],
    )
