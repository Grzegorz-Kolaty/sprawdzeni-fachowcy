from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.company_credential import CompanyCredential
from app.providers.udt_fgas import UdtFgasCredential


def get_company_credential(
    db: Session,
    *,
    provider: str,
    credential_number: str,
) -> CompanyCredential | None:
    statement = select(CompanyCredential).where(
        CompanyCredential.provider == provider,
        CompanyCredential.credential_number == credential_number,
    )

    return db.scalar(statement)


def upsert_udt_fgas_credential(
    db: Session,
    *,
    company_id: int,
    source_id: int,
    credential: UdtFgasCredential,
) -> CompanyCredential:
    existing = get_company_credential(
        db,
        provider="udt_fgas",
        credential_number=credential.credential_number,
    )

    if existing is None:
        existing = CompanyCredential(
            company_id=company_id,
            source_id=source_id,
            provider="udt_fgas",
            credential_type="fgas_company",
            issuer="Urząd Dozoru Technicznego",
            credential_number=credential.credential_number,
            status=credential.status,
            scope=credential.scope,
            issued_at=credential.issued_at,
            valid_until=None,
            status_changed_at=credential.status_changed_at,
        )

        db.add(existing)

        return existing

    if existing.company_id != company_id:
        raise ValueError("Credential is already assigned to another company")

    existing.source_id = source_id
    existing.status = credential.status
    existing.scope = credential.scope
    existing.issued_at = credential.issued_at
    existing.status_changed_at = credential.status_changed_at
    existing.verified_at = datetime.now(UTC)

    return existing


def get_company_credentials(
    db: Session,
    company_id: int,
) -> list[CompanyCredential]:
    statement = (
        select(CompanyCredential)
        .where(CompanyCredential.company_id == company_id)
        .options(
            selectinload(CompanyCredential.source),
        )
        .order_by(
            CompanyCredential.verified_at.desc(),
        )
    )

    return list(db.scalars(statement).all())
