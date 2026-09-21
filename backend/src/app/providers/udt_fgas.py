import time
from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx

UDT_FGAS_REGISTRY_URL = "https://www.udt.gov.pl/wykazy/REJ_ZAKL_UPR_FG.html"

UDT_FGAS_DATA_URL = "https://www.udt.gov.pl/wykazy/server_processing_ZAKL_UPR_FG.php"


class UdtFgasProviderError(Exception):
    pass


@dataclass(frozen=True)
class UdtFgasCredential:
    credential_number: str
    company_name_and_address: str
    nip: str
    krs: str | None
    scope: str
    issued_at: date | None
    status: str
    status_changed_at: date | None


class UdtFgasProvider:
    provider_name = "udt_fgas"
    issuer = "Urząd Dozoru Technicznego"
    credential_type = "fgas_company"

    def __init__(
        self,
        *,
        timeout: float = 15.0,
    ) -> None:
        self._timeout = timeout

    def find_by_nip(
        self,
        nip: str,
    ) -> list[UdtFgasCredential]:
        normalized_nip = self._normalize_nip(nip)

        try:
            with httpx.Client(
                timeout=self._timeout,
                follow_redirects=True,
                headers={
                    "User-Agent": ("SprawdzeniFachowcy/0.1 (public registry verification)"),
                },
            ) as client:
                # Najpierw otwieramy publiczną stronę rejestru.
                # Dzięki temu zachowujemy ewentualne cookies / sesję,
                # z których później korzysta request DataTables.
                registry_response = client.get(
                    UDT_FGAS_REGISTRY_URL,
                )
                registry_response.raise_for_status()

                response = client.get(
                    UDT_FGAS_DATA_URL,
                    params=self._build_params(normalized_nip),
                    headers={
                        "Accept": ("application/json, text/javascript, */*; q=0.01"),
                        "Referer": UDT_FGAS_REGISTRY_URL,
                        "X-Requested-With": "XMLHttpRequest",
                    },
                )

                response.raise_for_status()

        except httpx.HTTPError as exc:
            raise UdtFgasProviderError("Could not query UDT F-gas registry") from exc

        try:
            payload = response.json()

        except ValueError as exc:
            content_type = response.headers.get(
                "content-type",
                "<missing>",
            )

            preview = response.text[:500]

            raise UdtFgasProviderError(
                "UDT returned a non-JSON response. "
                f"status={response.status_code}, "
                f"content_type={content_type}, "
                f"body={preview!r}"
            ) from exc

        data = payload.get("data")

        if not isinstance(data, list):
            raise UdtFgasProviderError("UDT response does not contain a valid data array")

        credentials: list[UdtFgasCredential] = []

        for row in data:
            if not isinstance(row, dict):
                continue

            row_nip = "".join(
                character for character in str(row.get("NIP") or "") if character.isdigit()
            )

            # Nie ufamy recordsFiltered ani globalnemu search DataTables.
            # Rekord uznajemy dopiero wtedy, gdy jego NIP
            # dokładnie odpowiada szukanemu NIP-owi.
            if row_nip != normalized_nip:
                continue

            credentials.append(self._map_row(row))

        return credentials

    @staticmethod
    def _normalize_nip(
        value: str,
    ) -> str:
        normalized = "".join(character for character in value if character.isdigit())

        if len(normalized) != 10:
            raise ValueError("NIP must contain exactly 10 digits")

        return normalized

    @staticmethod
    def _parse_date(
        value: Any,
    ) -> date | None:
        if value is None:
            return None

        raw = str(value).strip()

        if not raw:
            return None

        try:
            return date.fromisoformat(raw)

        except ValueError as exc:
            raise UdtFgasProviderError(f"Unexpected UDT date format: {raw}") from exc

    def _map_row(
        self,
        row: dict[str, Any],
    ) -> UdtFgasCredential:
        credential_number = str(row.get("NR_DEC") or "").strip()

        company_name_and_address = str(row.get("NAZWA_ZJO") or "").strip()

        nip = self._normalize_nip(str(row.get("NIP") or ""))

        krs = self._optional_string(row.get("KRS"))

        scope = str(row.get("OPIS") or "").strip()

        issued_at = self._parse_date(row.get("DATA_WYD"))

        status = str(row.get("STAN") or "").strip()

        status_changed_at = self._parse_date(row.get("DATA_STATUSU"))

        return UdtFgasCredential(
            credential_number=credential_number,
            company_name_and_address=company_name_and_address,
            nip=nip,
            krs=krs,
            scope=scope,
            issued_at=issued_at,
            status=status,
            status_changed_at=status_changed_at,
        )

    @staticmethod
    def _optional_string(
        value: Any,
    ) -> str | None:
        if value is None:
            return None

        result = str(value).strip()

        return result or None

    @staticmethod
    def _build_params(
        search_value: str,
    ) -> dict[str, str]:
        columns = [
            "NR_DEC",
            "NAZWA_ZJO",
            "NIP",
            "KRS",
            "OPIS",
            "DATA_WYD",
            "STAN",
            "DATA_STATUSU",
        ]

        params: dict[str, str] = {
            "draw": "1",
            "order[0][column]": "1",
            "order[0][dir]": "asc",
            "order[0][name]": "",
            "start": "0",
            "length": "50",
            "search[value]": search_value,
            "search[regex]": "false",
            "_": str(int(time.time() * 1000)),
        }

        for index, column in enumerate(columns):
            prefix = f"columns[{index}]"

            params[f"{prefix}[data]"] = column
            params[f"{prefix}[name]"] = ""
            params[f"{prefix}[searchable]"] = "true"
            params[f"{prefix}[orderable]"] = "true"
            params[f"{prefix}[search][value]"] = ""
            params[f"{prefix}[search][regex]"] = "false"

        return params
