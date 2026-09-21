from sqlalchemy.orm import Session

from app.providers.udt_fgas import (
    UDT_FGAS_REGISTRY_URL,
    UdtFgasProvider,
    UdtFgasProviderError,
)
from app.repositories.company import (
    get_company,
)
from app.repositories.company_credential import (
    upsert_udt_fgas_credential,
)
from app.repositories.evidence import (
    add_evidence,
)
from app.repositories.source import (
    get_or_create_source,
)
from app.schemas.udt_fgas import (
    UdtFgasCredentialRead,
    UdtFgasVerificationRead,
)


class CompanyNotFoundError(Exception):
    pass


class UdtFgasVerificationError(Exception):
    pass


def verify_company_udt_fgas(
    db: Session,
    *,
    company_id: int,
) -> UdtFgasVerificationRead:
    company = get_company(
        db,
        company_id,
    )

    if company is None:
        raise CompanyNotFoundError(f"Company {company_id} does not exist")

    provider = UdtFgasProvider()

    try:
        results = provider.find_by_nip(company.nip)

    except UdtFgasProviderError as exc:
        raise UdtFgasVerificationError("UDT F-gas registry could not be verified") from exc

    source = get_or_create_source(
        db,
        url=UDT_FGAS_REGISTRY_URL,
        source_type=("official_registry"),
        title=("UDT – rejestr certyfikatów F-gaz przedsiębiorców"),
    )

    db.flush()

    stored_credentials = []

    if not results:
        add_evidence(
            db,
            company_id=company.id,
            source_id=source.id,
            evidence_type=("udt_fgas_not_found"),
            observed_value=(company.nip),
            normalized_value=(company.nip),
            confidence="strong",
        )

    for result in results:
        credential = upsert_udt_fgas_credential(
            db,
            company_id=company.id,
            source_id=source.id,
            credential=result,
        )

        db.flush()

        add_evidence(
            db,
            company_id=company.id,
            source_id=source.id,
            evidence_type=("udt_fgas_credential_found"),
            observed_value=(result.credential_number),
            normalized_value=(result.credential_number),
            confidence="strong",
        )

        stored_credentials.append(credential)

    db.commit()

    db.refresh(source)

    for credential in stored_credentials:
        db.refresh(credential)

    return UdtFgasVerificationRead(
        company_id=company.id,
        nip=company.nip,
        found=bool(stored_credentials),
        source_url=source.url,
        credentials=[
            UdtFgasCredentialRead(
                id=credential.id,
                credential_number=(credential.credential_number),
                status=(credential.status),
                scope=(credential.scope),
                issued_at=(credential.issued_at),
                status_changed_at=(credential.status_changed_at),
                verified_at=(credential.verified_at),
            )
            for credential in stored_credentials
        ],
    )
