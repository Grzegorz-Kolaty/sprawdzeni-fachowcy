from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.claim import (
    ClaimDetectionCreate,
    ClaimDetectionRead,
)
from app.schemas.claim_evidence_verification import (
    ClaimEvidenceVerificationRead,
)
from app.schemas.udt_fgas import UdtFgasVerificationRead
from app.schemas.verification import (
    WebsiteIdentityVerificationCreate,
    WebsiteIdentityVerificationRead,
)
from app.schemas.verification_report import (
    CompanyVerificationReportRead,
)
from app.services.claim_detection import (
    ClaimDetectionError,
    detect_company_claims,
)
from app.services.claim_detection import (
    CompanyNotFoundError as ClaimCompanyNotFoundError,
)
from app.services.claim_detection import (
    WebsiteNotFoundError as ClaimWebsiteNotFoundError,
)
from app.services.claim_evidence_verification import (
    ClaimContextNotFoundError,
    ClaimDoesNotBelongToCompanyError,
    ClaimNotFoundError,
    ClaimSourceFetchError,
    ClaimSourceNotFoundError,
    verify_claim_evidence,
)
from app.services.claim_evidence_verification import (
    CompanyNotFoundError as ClaimVerificationCompanyNotFoundError,
)
from app.services.company_verification_report import (
    CompanyNotFoundError as ReportCompanyNotFoundError,
)
from app.services.company_verification_report import (
    get_company_verification_report,
)
from app.services.udt_fgas_verification import (
    CompanyNotFoundError as UdtCompanyNotFoundError,
)
from app.services.udt_fgas_verification import (
    UdtFgasVerificationError,
    verify_company_udt_fgas,
)
from app.services.website_verification import (
    CompanyNotFoundError,
    InvalidObservedNipError,
    SourceDoesNotBelongToWebsiteError,
    WebsiteDoesNotBelongToCompanyError,
    WebsiteNotFoundError,
    verify_website_identity,
)

router = APIRouter(
    prefix="/api/companies",
    tags=["verification"],
)


@router.post(
    "/{company_id}/websites/{website_id}/verify-identity",
    response_model=WebsiteIdentityVerificationRead,
    status_code=status.HTTP_201_CREATED,
)
def verify_identity(
    company_id: int,
    website_id: int,
    data: WebsiteIdentityVerificationCreate,
    db: Session = Depends(get_db),
) -> WebsiteIdentityVerificationRead:
    try:
        return verify_website_identity(
            db,
            company_id=company_id,
            website_id=website_id,
            data=data,
        )

    except (
        CompanyNotFoundError,
        WebsiteNotFoundError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except (
        WebsiteDoesNotBelongToCompanyError,
        SourceDoesNotBelongToWebsiteError,
        InvalidObservedNipError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc


@router.post(
    "/{company_id}/verify/udt-fgas",
    response_model=UdtFgasVerificationRead,
)
def verify_udt_fgas(
    company_id: int,
    db: Session = Depends(get_db),
) -> UdtFgasVerificationRead:
    try:
        return verify_company_udt_fgas(
            db,
            company_id=company_id,
        )

    except UdtCompanyNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except UdtFgasVerificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.get(
    "/{company_id}/verification",
    response_model=CompanyVerificationReportRead,
)
def get_verification_report(
    company_id: int,
    db: Session = Depends(get_db),
) -> CompanyVerificationReportRead:
    try:
        return get_company_verification_report(
            db,
            company_id=company_id,
        )

    except ReportCompanyNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post(
    "/{company_id}/websites/{website_id}/detect-claims",
    response_model=ClaimDetectionRead,
)
def detect_claims(
    company_id: int,
    website_id: int,
    data: ClaimDetectionCreate,
    db: Session = Depends(get_db),
) -> ClaimDetectionRead:
    try:
        return detect_company_claims(
            db,
            company_id=company_id,
            website_id=website_id,
            source_url=str(data.source_url),
        )

    except ClaimCompanyNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except ClaimWebsiteNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except (
        WebsiteDoesNotBelongToCompanyError,
        SourceDoesNotBelongToWebsiteError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    except ClaimDetectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.post(
    "/{company_id}/claims/{claim_id}/verify",
    response_model=ClaimEvidenceVerificationRead,
)
def verify_claim(
    company_id: int,
    claim_id: int,
    db: Session = Depends(get_db),
) -> ClaimEvidenceVerificationRead:
    try:
        return verify_claim_evidence(
            db,
            company_id=company_id,
            claim_id=claim_id,
        )

    except (
        ClaimVerificationCompanyNotFoundError,
        ClaimNotFoundError,
        ClaimSourceNotFoundError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except ClaimDoesNotBelongToCompanyError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    except (
        ClaimSourceFetchError,
        ClaimContextNotFoundError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
