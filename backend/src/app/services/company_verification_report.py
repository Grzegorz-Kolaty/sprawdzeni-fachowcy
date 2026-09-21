from sqlalchemy.orm import Session

from app.repositories.brand import (
    get_company_brands,
)
from app.repositories.company import (
    get_company,
)
from app.repositories.company_credential import (
    get_company_credentials,
)
from app.repositories.company_website import (
    get_company_websites,
)
from app.repositories.evidence import (
    get_company_evidence,
)
from app.schemas.brand import (
    BrandRead,
)
from app.schemas.company import (
    CompanyRead,
)
from app.schemas.company_website import (
    CompanyWebsiteRead,
)
from app.schemas.verification_report import (
    CompanyCredentialReportRead,
    CompanyVerificationReportRead,
    VerificationEvidenceRead,
    VerificationSourceRead,
    VerificationSummaryRead,
)


class CompanyNotFoundError(Exception):
    pass


def get_company_verification_report(
    db: Session,
    *,
    company_id: int,
) -> CompanyVerificationReportRead:
    company = get_company(
        db,
        company_id,
    )

    if company is None:
        raise CompanyNotFoundError(f"Company {company_id} does not exist")

    brands = get_company_brands(
        db,
        company_id,
    )

    websites = get_company_websites(
        db,
        company_id,
    )

    credentials = get_company_credentials(
        db,
        company_id,
    )

    evidence = get_company_evidence(
        db,
        company_id,
    )

    identity_verified = any(item.evidence_type == "website_company_nip_match" for item in evidence)

    return CompanyVerificationReportRead(
        company=(CompanyRead.model_validate(company)),
        brands=[BrandRead.model_validate(item) for item in brands],
        websites=[(CompanyWebsiteRead.model_validate(item)) for item in websites],
        summary=(
            VerificationSummaryRead(
                identity_verified=(identity_verified),
                official_credentials_found=(bool(credentials)),
                evidence_count=len(evidence),
                credential_count=len(credentials),
            )
        ),
        credentials=[
            CompanyCredentialReportRead(
                id=item.id,
                provider=item.provider,
                credential_type=(item.credential_type),
                issuer=item.issuer,
                credential_number=(item.credential_number),
                status=item.status,
                scope=item.scope,
                issued_at=item.issued_at,
                valid_until=(item.valid_until),
                status_changed_at=(item.status_changed_at),
                verified_at=(item.verified_at),
                source=(VerificationSourceRead.model_validate(item.source)),
            )
            for item in credentials
        ],
        evidence=[
            VerificationEvidenceRead(
                id=item.id,
                evidence_type=(item.evidence_type),
                observed_value=(item.observed_value),
                normalized_value=(item.normalized_value),
                confidence=(item.confidence),
                created_at=(item.created_at),
                last_observed_at=(item.last_observed_at),
                source=(VerificationSourceRead.model_validate(item.source)),
            )
            for item in evidence
        ],
    )
