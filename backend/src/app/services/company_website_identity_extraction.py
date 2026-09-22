import heapq
import json
import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, Tag

from app.providers.website_page_inspector import (
    MissingWebsitePageError,
    WebsitePageInspection,
    WebsitePageInspectionError,
    WebsitePageInspector,
)

IdentityClueField = Literal[
    "display_name",
    "legal_company_name",
    "nip",
    "regon",
    "krs",
    "street_address",
    "postal_code",
    "city",
    "phone",
    "email",
    "website_domain",
]

IdentityClueSourceKind = Literal[
    "input_url",
    "page_text",
    "json_ld",
    "html_metadata",
    "html_title",
    "link_href",
]

_EMAIL_RE = re.compile(
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    re.IGNORECASE,
)
_NIP_RE = re.compile(
    r"\bNIP(?:\s*PL)?\s*[:.\-]?\s*(?:PL\s*)?(?P<value>\d[\d\s-]{8,}\d)\b",
    re.IGNORECASE,
)
_REGON_RE = re.compile(
    r"\bREGON\s*[:.\-]?\s*(?P<value>\d[\d\s-]{7,}\d)\b",
    re.IGNORECASE,
)
_KRS_RE = re.compile(
    r"\bKRS\s*[:.\-]?\s*(?P<value>\d[\d\s-]{8,}\d)\b",
    re.IGNORECASE,
)
_PHONE_RE = re.compile(
    r"\b(?:tel\.?|telefon|phone|mobile|kom\.?)\s*[:.\-]?\s*(?P<value>\+?\d[\d\s()./-]{6,}\d)",
    re.IGNORECASE,
)
_STREET_RE = re.compile(
    r"\b(?P<value>(?:ul\.?|ulica|al\.?|aleja|pl\.?|plac|street|st\.|road|rd\.|avenue|ave\.)"
    r"\s+[\w .'\-]{2,80}?\s+\d+[A-Z]?(?:\s*/\s*\d+[A-Z]?)?)",
    re.IGNORECASE,
)
_POSTAL_CITY_RE = re.compile(
    r"\b(?P<postal_code>\d{2}-\d{3})\s+"
    r"(?P<city>[\w.'\-]+(?:\s+[\w.'\-]+){0,3})",
    re.IGNORECASE,
)
_LEGAL_NAME_RE = re.compile(
    r"^\s*(?:nazwa\s+firmy|nazwa\s+prawna|firma|company\s+name|legal\s+name|"
    r"administrator|operator|seller|sprzedawca|service\s+provider|uslugodawca)"
    r"\s*[:\-]\s*(?P<value>.+)$",
    re.IGNORECASE | re.MULTILINE,
)
_DISPLAY_NAME_RE = re.compile(
    r"^\s*(?:nazwa\s+handlowa|trading\s+name|trade\s+name|brand|marka)"
    r"\s*[:\-]\s*(?P<value>.+)$",
    re.IGNORECASE | re.MULTILINE,
)
_HTML_NAME_META = (
    ("property", "og:site_name"),
    ("name", "application-name"),
    ("name", "twitter:site"),
)
_IDENTITY_PATHS = (
    "/contact",
    "/kontakt",
    "/about",
    "/about-us",
    "/o-nas",
    "/onas",
    "/company",
    "/firma",
    "/legal",
    "/terms",
    "/regulamin",
    "/privacy",
    "/privacy-policy",
    "/polityka-prywatnosci",
)
_TRAILING_VALUE_LABEL_RE = re.compile(
    r"\b(?:NIP|REGON|KRS|VAT|Telefon|Tel\.?|Phone|E-mail|Email|Adres|Address)\b.*$",
    re.IGNORECASE,
)
_CITY_STOP_WORDS = {
    "nip",
    "regon",
    "krs",
    "vat",
    "tel",
    "telefon",
    "phone",
    "email",
    "e-mail",
    "adres",
    "address",
}
_SCHEMA_RELEVANT_TYPES = {
    "corporation",
    "localbusiness",
    "organization",
    "organisation",
    "professionalservice",
}


class WebsitePageInspectorProtocol(Protocol):
    def inspect(
        self,
        url: str,
        *,
        same_site_hostname: str | None = None,
    ) -> WebsitePageInspection: ...


@dataclass(frozen=True)
class CompanyWebsiteIdentityClue:
    field: IdentityClueField
    value: str
    source_url: str
    source_kind: IdentityClueSourceKind


@dataclass(frozen=True)
class InspectedCompanyWebsiteIdentityPage:
    requested_url: str
    final_url: str


@dataclass(frozen=True)
class CompanyWebsiteIdentityExtraction:
    candidate_url: str
    website_domain: str | None
    inspected_pages: tuple[InspectedCompanyWebsiteIdentityPage, ...]
    identity_clues: tuple[CompanyWebsiteIdentityClue, ...]
    errors: tuple[str, ...] = ()


class CompanyWebsiteIdentityParser:
    def parse(
        self,
        inspection: WebsitePageInspection,
    ) -> list[CompanyWebsiteIdentityClue]:
        soup = BeautifulSoup(
            inspection.html,
            "html.parser",
        )
        source_url = inspection.final_url

        clues: list[CompanyWebsiteIdentityClue] = []
        clues.extend(self._extract_json_ld_clues(soup, source_url=source_url))

        lines = self._page_text_lines(soup)
        text = "\n".join(lines)
        flat_text = " ".join(lines)

        clues.extend(
            self._extract_name_clues(
                text,
                source_url=source_url,
                source_kind="page_text",
            )
        )
        clues.extend(
            self._extract_identifier_clues(
                flat_text,
                source_url=source_url,
                source_kind="page_text",
            )
        )
        clues.extend(
            self._extract_contact_clues(
                flat_text,
                soup=soup,
                source_url=source_url,
            )
        )
        clues.extend(
            self._extract_address_clues(
                flat_text,
                source_url=source_url,
                source_kind="page_text",
            )
        )
        clues.extend(
            self._extract_html_metadata_clues(
                soup,
                inspection=inspection,
                source_url=source_url,
            )
        )

        return clues

    def _extract_json_ld_clues(
        self,
        soup: BeautifulSoup,
        *,
        source_url: str,
    ) -> list[CompanyWebsiteIdentityClue]:
        clues: list[CompanyWebsiteIdentityClue] = []

        for script in soup.find_all("script", attrs={"type": re.compile("ld\\+json", re.I)}):
            if not isinstance(script, Tag):
                continue

            raw_value = script.string or script.get_text()

            if not raw_value:
                continue

            try:
                parsed = json.loads(raw_value)
            except json.JSONDecodeError:
                continue

            for node in self._iter_json_ld_nodes(parsed):
                if not self._is_relevant_schema_node(node):
                    continue

                clues.extend(self._extract_json_ld_node_clues(node, source_url=source_url))

        return clues

    def _extract_json_ld_node_clues(
        self,
        node: Mapping[str, Any],
        *,
        source_url: str,
    ) -> list[CompanyWebsiteIdentityClue]:
        clues: list[CompanyWebsiteIdentityClue] = []

        for name in self._string_values(node.get("name")):
            clues.append(self._clue("display_name", name, source_url, "json_ld"))

        for legal_name in self._string_values(node.get("legalName")):
            clues.append(self._clue("legal_company_name", legal_name, source_url, "json_ld"))

        for alternate_name in self._string_values(node.get("alternateName")):
            clues.append(self._clue("display_name", alternate_name, source_url, "json_ld"))

        for tax_id in self._string_values(node.get("taxID")):
            clues.extend(
                self._extract_nip_value(
                    tax_id,
                    source_url=source_url,
                    source_kind="json_ld",
                )
            )

        for vat_id in self._string_values(node.get("vatID")):
            clues.extend(
                self._extract_nip_value(
                    vat_id,
                    source_url=source_url,
                    source_kind="json_ld",
                )
            )

        clues.extend(
            self._extract_json_ld_identifier_clues(
                node.get("identifier"),
                source_url=source_url,
            )
        )

        for telephone in self._string_values(node.get("telephone")):
            normalized = self._normalize_phone(telephone)

            if normalized:
                clues.append(self._clue("phone", normalized, source_url, "json_ld"))

        for email in self._string_values(node.get("email")):
            normalized = self._normalize_email(email)

            if normalized:
                clues.append(self._clue("email", normalized, source_url, "json_ld"))

        for website_url in self._string_values(node.get("url")):
            domain = _domain_from_url(website_url)

            if domain:
                clues.append(self._clue("website_domain", domain, source_url, "json_ld"))

        clues.extend(
            self._extract_json_ld_address_clues(
                node.get("address"),
                source_url=source_url,
            )
        )

        return clues

    def _extract_json_ld_identifier_clues(
        self,
        value: Any,
        *,
        source_url: str,
    ) -> list[CompanyWebsiteIdentityClue]:
        clues: list[CompanyWebsiteIdentityClue] = []

        for item in self._sequence_values(value):
            if isinstance(item, str):
                clues.extend(
                    self._extract_identifier_clues(
                        item,
                        source_url=source_url,
                        source_kind="json_ld",
                    )
                )
                continue

            if not isinstance(item, Mapping):
                continue

            raw_value = self._first_string(
                item.get("value"),
                item.get("@value"),
                item.get("identifier"),
            )

            if not raw_value:
                continue

            label_text = " ".join(
                value
                for value in (
                    self._first_string(item.get("propertyID")),
                    self._first_string(item.get("name")),
                    self._first_string(item.get("@type")),
                )
                if value
            )
            normalized_label = _normalize_search_text(label_text)

            if "nip" in normalized_label or "tax" in normalized_label or "vat" in normalized_label:
                clues.extend(
                    self._extract_nip_value(
                        raw_value,
                        source_url=source_url,
                        source_kind="json_ld",
                    )
                )
            elif "regon" in normalized_label:
                normalized = self._digits(raw_value)

                if len(normalized) in {9, 14}:
                    clues.append(self._clue("regon", normalized, source_url, "json_ld"))
            elif "krs" in normalized_label:
                normalized = self._digits(raw_value)

                if len(normalized) == 10:
                    clues.append(self._clue("krs", normalized, source_url, "json_ld"))
            else:
                clues.extend(
                    self._extract_identifier_clues(
                        raw_value,
                        source_url=source_url,
                        source_kind="json_ld",
                    )
                )

        return clues

    def _extract_json_ld_address_clues(
        self,
        value: Any,
        *,
        source_url: str,
    ) -> list[CompanyWebsiteIdentityClue]:
        clues: list[CompanyWebsiteIdentityClue] = []

        for item in self._sequence_values(value):
            if isinstance(item, str):
                clues.extend(
                    self._extract_address_clues(
                        item,
                        source_url=source_url,
                        source_kind="json_ld",
                    )
                )
                continue

            if not isinstance(item, Mapping):
                continue

            for street in self._string_values(item.get("streetAddress")):
                clues.append(self._clue("street_address", street, source_url, "json_ld"))

            for postal_code in self._string_values(item.get("postalCode")):
                normalized = postal_code.strip()

                if normalized:
                    clues.append(self._clue("postal_code", normalized, source_url, "json_ld"))

            for city in self._string_values(item.get("addressLocality")):
                normalized = city.strip()

                if normalized:
                    clues.append(self._clue("city", normalized, source_url, "json_ld"))

        return clues

    def _extract_html_metadata_clues(
        self,
        soup: BeautifulSoup,
        *,
        inspection: WebsitePageInspection,
        source_url: str,
    ) -> list[CompanyWebsiteIdentityClue]:
        clues: list[CompanyWebsiteIdentityClue] = []

        for attribute, expected_value in _HTML_NAME_META:
            meta = soup.find(
                "meta",
                attrs={attribute: re.compile(f"^{re.escape(expected_value)}$", re.IGNORECASE)},
            )

            if not isinstance(meta, Tag):
                continue

            content = meta.get("content")

            if isinstance(content, str) and content.strip():
                clues.append(self._clue("display_name", content, source_url, "html_metadata"))

        if inspection.title:
            clues.append(self._clue("display_name", inspection.title, source_url, "html_title"))

        return clues

    def _extract_name_clues(
        self,
        text: str,
        *,
        source_url: str,
        source_kind: IdentityClueSourceKind,
    ) -> list[CompanyWebsiteIdentityClue]:
        clues: list[CompanyWebsiteIdentityClue] = []

        for match in _LEGAL_NAME_RE.finditer(text):
            value = self._clean_labeled_value(match.group("value"))

            if value:
                clues.append(self._clue("legal_company_name", value, source_url, source_kind))

        for match in _DISPLAY_NAME_RE.finditer(text):
            value = self._clean_labeled_value(match.group("value"))

            if value:
                clues.append(self._clue("display_name", value, source_url, source_kind))

        return clues

    def _extract_identifier_clues(
        self,
        text: str,
        *,
        source_url: str,
        source_kind: IdentityClueSourceKind,
    ) -> list[CompanyWebsiteIdentityClue]:
        clues: list[CompanyWebsiteIdentityClue] = []

        for match in _NIP_RE.finditer(text):
            normalized = self._digits(match.group("value"))

            if len(normalized) == 10:
                clues.append(self._clue("nip", normalized, source_url, source_kind))

        for match in _REGON_RE.finditer(text):
            normalized = self._digits(match.group("value"))

            if len(normalized) in {9, 14}:
                clues.append(self._clue("regon", normalized, source_url, source_kind))

        for match in _KRS_RE.finditer(text):
            normalized = self._digits(match.group("value"))

            if len(normalized) == 10:
                clues.append(self._clue("krs", normalized, source_url, source_kind))

        return clues

    def _extract_nip_value(
        self,
        value: str,
        *,
        source_url: str,
        source_kind: IdentityClueSourceKind,
    ) -> list[CompanyWebsiteIdentityClue]:
        normalized = self._digits(value)

        if len(normalized) != 10:
            return []

        return [self._clue("nip", normalized, source_url, source_kind)]

    def _extract_contact_clues(
        self,
        text: str,
        *,
        soup: BeautifulSoup,
        source_url: str,
    ) -> list[CompanyWebsiteIdentityClue]:
        clues: list[CompanyWebsiteIdentityClue] = []

        for match in _EMAIL_RE.finditer(text):
            normalized = self._normalize_email(match.group(0))

            if normalized:
                clues.append(self._clue("email", normalized, source_url, "page_text"))

        for match in _PHONE_RE.finditer(text):
            normalized = self._normalize_phone(match.group("value"))

            if normalized:
                clues.append(self._clue("phone", normalized, source_url, "page_text"))

        for link in soup.find_all("a", href=True):
            href = link.get("href")

            if not isinstance(href, str):
                continue

            stripped = href.strip()
            lower = stripped.casefold()

            if lower.startswith("mailto:"):
                email = self._normalize_email(stripped[7:].split("?", 1)[0])

                if email:
                    clues.append(self._clue("email", email, source_url, "link_href"))

            if lower.startswith("tel:"):
                phone = self._normalize_phone(stripped[4:])

                if phone:
                    clues.append(self._clue("phone", phone, source_url, "link_href"))

        return clues

    def _extract_address_clues(
        self,
        text: str,
        *,
        source_url: str,
        source_kind: IdentityClueSourceKind,
    ) -> list[CompanyWebsiteIdentityClue]:
        clues: list[CompanyWebsiteIdentityClue] = []

        for match in _STREET_RE.finditer(text):
            street = self._clean_address_value(match.group("value"))

            if street:
                clues.append(self._clue("street_address", street, source_url, source_kind))

        for match in _POSTAL_CITY_RE.finditer(text):
            postal_code = match.group("postal_code").strip()
            city = self._clean_city_value(match.group("city"))

            if postal_code:
                clues.append(self._clue("postal_code", postal_code, source_url, source_kind))

            if city:
                clues.append(self._clue("city", city, source_url, source_kind))

        return clues

    def _page_text_lines(
        self,
        soup: BeautifulSoup,
    ) -> list[str]:
        for tag in soup.find_all(
            [
                "script",
                "style",
                "noscript",
                "template",
                "svg",
            ]
        ):
            tag.decompose()

        body = soup.body or soup

        return [
            _normalize_space(line)
            for line in body.get_text("\n", strip=True).splitlines()
            if _normalize_space(line)
        ]

    def _iter_json_ld_nodes(
        self,
        value: Any,
    ) -> Iterable[Mapping[str, Any]]:
        for item in self._sequence_values(value):
            if not isinstance(item, Mapping):
                continue

            graph = item.get("@graph")

            if graph is not None:
                yield from self._iter_json_ld_nodes(graph)

            yield item

    def _is_relevant_schema_node(
        self,
        node: Mapping[str, Any],
    ) -> bool:
        schema_types = self._schema_types(node.get("@type"))

        return bool(schema_types & _SCHEMA_RELEVANT_TYPES) or any(
            schema_type.endswith("business") for schema_type in schema_types
        )

    def _schema_types(
        self,
        value: Any,
    ) -> set[str]:
        result: set[str] = set()

        for item in self._string_values(value):
            normalized = item.rsplit("/", 1)[-1].rsplit("#", 1)[-1]
            normalized = _normalize_search_text(normalized).replace(" ", "")

            if normalized:
                result.add(normalized)

        return result

    def _sequence_values(
        self,
        value: Any,
    ) -> Iterable[Any]:
        if value is None:
            return ()

        if isinstance(value, list | tuple):
            return value

        return (value,)

    def _string_values(
        self,
        value: Any,
    ) -> Iterable[str]:
        for item in self._sequence_values(value):
            if isinstance(item, str) and item.strip():
                yield item.strip()

    def _first_string(
        self,
        *values: Any,
    ) -> str | None:
        for value in values:
            for item in self._string_values(value):
                return item

        return None

    @staticmethod
    def _clue(
        field: IdentityClueField,
        value: str,
        source_url: str,
        source_kind: IdentityClueSourceKind,
    ) -> CompanyWebsiteIdentityClue:
        return CompanyWebsiteIdentityClue(
            field=field,
            value=_normalize_space(value),
            source_url=source_url,
            source_kind=source_kind,
        )

    @staticmethod
    def _digits(
        value: str,
    ) -> str:
        return re.sub(
            r"\D",
            "",
            value,
        )

    @staticmethod
    def _normalize_email(
        value: str,
    ) -> str | None:
        value = value.strip().lower()

        if _EMAIL_RE.fullmatch(value):
            return value

        return None

    @staticmethod
    def _normalize_phone(
        value: str,
    ) -> str | None:
        value = value.strip()
        prefix = "+" if value.startswith("+") else ""
        digits = re.sub(
            r"\D",
            "",
            value,
        )

        if len(digits) < 7:
            return None

        if value.startswith("00") and len(digits) > 10:
            return f"+{digits[2:]}"

        if prefix or len(digits) > 10:
            return f"+{digits}"

        return digits

    @staticmethod
    def _clean_labeled_value(
        value: str,
    ) -> str | None:
        value = _TRAILING_VALUE_LABEL_RE.sub(
            "",
            value,
        )
        value = value.strip(" :-,.;")

        if not value or len(value) > 180:
            return None

        return value

    @staticmethod
    def _clean_address_value(
        value: str,
    ) -> str | None:
        value = value.strip(" ,.;")

        if not value or len(value) > 120:
            return None

        return re.sub(
            r"\s+",
            " ",
            value,
        )

    def _clean_city_value(
        self,
        value: str,
    ) -> str | None:
        tokens: list[str] = []

        for token in value.strip(" ,.;").split():
            normalized = _normalize_search_text(token)

            if normalized in _CITY_STOP_WORDS:
                break

            if any(character.isdigit() for character in token):
                break

            tokens.append(token.strip(" ,.;"))

        city = " ".join(token for token in tokens if token)

        if not city or len(city) > 80:
            return None

        return city


class CompanyWebsiteIdentityExtractor:
    def __init__(
        self,
        page_inspector: WebsitePageInspectorProtocol | None = None,
        *,
        max_pages: int = 6,
        request_timeout: float = 8.0,
    ) -> None:
        self._page_inspector = page_inspector or WebsitePageInspector(
            timeout=request_timeout,
            user_agent="SprawdzeniFachowcy/0.1 (company identity extraction)",
        )
        self._identity_parser = CompanyWebsiteIdentityParser()
        self._max_pages = max_pages

    def extract(
        self,
        candidate_url: str,
    ) -> CompanyWebsiteIdentityExtraction:
        start_hostname = _hostname(candidate_url)

        if start_hostname is None:
            return CompanyWebsiteIdentityExtraction(
                candidate_url=candidate_url,
                website_domain=None,
                inspected_pages=(),
                identity_clues=(),
                errors=("Candidate URL has no hostname",),
            )

        site_hostname = _normalize_hostname(start_hostname)
        base_url = _base_url(candidate_url)

        queue: list[tuple[int, int, str, bool]] = []
        queued: dict[str, int] = {}
        visited: set[str] = set()
        sequence = 0

        sequence = self._enqueue(
            queue,
            queued=queued,
            visited=visited,
            sequence=sequence,
            priority=0,
            url=candidate_url,
            site_hostname=site_hostname,
            is_speculative=False,
        )
        sequence = self._enqueue(
            queue,
            queued=queued,
            visited=visited,
            sequence=sequence,
            priority=10,
            url=base_url,
            site_hostname=site_hostname,
            is_speculative=False,
        )

        for offset, path in enumerate(_IDENTITY_PATHS):
            sequence = self._enqueue(
                queue,
                queued=queued,
                visited=visited,
                sequence=sequence,
                priority=80 + offset,
                url=urljoin(base_url, path),
                site_hostname=site_hostname,
                is_speculative=True,
            )

        clues = [
            CompanyWebsiteIdentityClue(
                field="website_domain",
                value=site_hostname,
                source_url=candidate_url,
                source_kind="input_url",
            )
        ]
        inspected_pages: list[InspectedCompanyWebsiteIdentityPage] = []
        errors: list[str] = []

        while queue and len(inspected_pages) < self._max_pages:
            _priority, _sequence, url, is_speculative = heapq.heappop(queue)
            canonical_url = _canonical_url(url)

            if canonical_url in visited:
                continue

            visited.add(canonical_url)

            try:
                inspection = self._page_inspector.inspect(
                    url,
                    same_site_hostname=site_hostname,
                )
            except MissingWebsitePageError as exc:
                if not is_speculative:
                    errors.append(f"{url}: {exc}")
                continue
            except WebsitePageInspectionError as exc:
                errors.append(f"{url}: {exc}")
                continue

            final_hostname = _hostname(inspection.final_url)

            if final_hostname is None or not _same_site(site_hostname, final_hostname):
                errors.append(f"{url}: final URL leaves the inspected website")
                continue

            inspected_pages.append(
                InspectedCompanyWebsiteIdentityPage(
                    requested_url=inspection.requested_url,
                    final_url=inspection.final_url,
                )
            )
            clues.extend(self._identity_parser.parse(inspection))

            for link in inspection.links:
                link_hostname = _hostname(link.url)

                if link_hostname is None or not _same_site(site_hostname, link_hostname):
                    continue

                link_score = self._identity_link_score(
                    text=link.text,
                    url=link.url,
                    source_region=link.source_region,
                )

                if link_score <= 0:
                    continue

                sequence = self._enqueue(
                    queue,
                    queued=queued,
                    visited=visited,
                    sequence=sequence,
                    priority=max(20, 70 - link_score),
                    url=link.url,
                    site_hostname=site_hostname,
                    is_speculative=False,
                )

        return CompanyWebsiteIdentityExtraction(
            candidate_url=candidate_url,
            website_domain=site_hostname,
            inspected_pages=tuple(inspected_pages),
            identity_clues=self._deduplicate_clues(clues),
            errors=tuple(errors),
        )

    def _identity_link_score(
        self,
        *,
        text: str,
        url: str,
        source_region: str,
    ) -> int:
        parsed = urlsplit(url)
        haystack = _normalize_search_text(f"{text} {parsed.path}")
        score = 0

        if any(token in haystack for token in ("contact", "kontakt", "dane kontaktowe")):
            score += 50

        if any(token in haystack for token in ("about", "about us", "o nas", "firma", "company")):
            score += 40

        if any(
            token in haystack
            for token in (
                "legal",
                "terms",
                "regulamin",
                "privacy",
                "polityka prywatnosci",
                "prywatnosc",
                "impressum",
                "rodo",
                "gdpr",
            )
        ):
            score += 35

        if any(token in haystack for token in ("nip", "regon", "krs", "address", "adres")):
            score += 30

        if source_region == "footer" and score > 0:
            score += 10

        return score

    def _enqueue(
        self,
        queue: list[tuple[int, int, str, bool]],
        *,
        queued: dict[str, int],
        visited: set[str],
        sequence: int,
        priority: int,
        url: str,
        site_hostname: str,
        is_speculative: bool,
    ) -> int:
        hostname = _hostname(url)

        if hostname is None or not _same_site(site_hostname, hostname):
            return sequence

        parsed = urlsplit(url)

        if parsed.scheme.casefold() not in {"http", "https"}:
            return sequence

        canonical_url = _canonical_url(url)

        existing_priority = queued.get(canonical_url)

        if existing_priority is not None and existing_priority <= priority:
            return sequence

        if canonical_url in visited:
            return sequence

        sequence += 1
        queued[canonical_url] = priority

        heapq.heappush(
            queue,
            (
                priority,
                sequence,
                url,
                is_speculative,
            ),
        )

        return sequence

    def _deduplicate_clues(
        self,
        clues: list[CompanyWebsiteIdentityClue],
    ) -> tuple[CompanyWebsiteIdentityClue, ...]:
        result: list[CompanyWebsiteIdentityClue] = []
        seen: set[tuple[str, ...]] = set()

        for clue in clues:
            normalized_value = _normalize_identity_clue_value(clue)

            if not normalized_value:
                continue

            key = _identity_clue_deduplication_key(
                clue,
                normalized_value=normalized_value,
            )

            if key in seen:
                continue

            seen.add(key)
            result.append(
                CompanyWebsiteIdentityClue(
                    field=clue.field,
                    value=normalized_value,
                    source_url=clue.source_url,
                    source_kind=clue.source_kind,
                )
            )

        return tuple(result)


def _normalize_space(
    value: str,
) -> str:
    return re.sub(
        r"\s+",
        " ",
        value,
    ).strip()


def _normalize_search_text(
    value: str,
) -> str:
    value = unicodedata.normalize(
        "NFKD",
        value.casefold(),
    )
    value = "".join(character for character in value if not unicodedata.combining(character))
    value = re.sub(
        r"[^a-z0-9]+",
        " ",
        value,
    )

    return " ".join(value.split())


def _normalize_identity_clue_value(
    clue: CompanyWebsiteIdentityClue,
) -> str:
    normalized_value = _normalize_space(clue.value)

    if clue.field != "phone":
        return normalized_value

    normalized_phone = CompanyWebsiteIdentityParser._normalize_phone(normalized_value)

    return normalized_phone or normalized_value


def _identity_clue_deduplication_key(
    clue: CompanyWebsiteIdentityClue,
    *,
    normalized_value: str,
) -> tuple[str, ...]:
    if clue.field in {
        "display_name",
        "legal_company_name",
        "phone",
    }:
        return (
            clue.field,
            normalized_value.casefold(),
            clue.source_url,
        )

    return (
        clue.field,
        normalized_value.casefold(),
        clue.source_url,
        clue.source_kind,
    )


def _same_site(
    first_hostname: str,
    second_hostname: str,
) -> bool:
    return _normalize_hostname(first_hostname) == _normalize_hostname(second_hostname)


def _hostname(
    url: str,
) -> str | None:
    hostname = urlsplit(url).hostname

    if hostname is None:
        return None

    return hostname.casefold().rstrip(".")


def _normalize_hostname(
    hostname: str,
) -> str:
    return hostname.casefold().rstrip(".").removeprefix("www.")


def _base_url(
    url: str,
) -> str:
    parsed = urlsplit(url)

    return f"{parsed.scheme}://{parsed.netloc}/"


def _canonical_url(
    url: str,
) -> str:
    parsed = urlsplit(url)
    hostname = _normalize_hostname(parsed.hostname or "")
    path = parsed.path.rstrip("/") or "/"

    return f"{parsed.scheme.casefold()}://{hostname}{path}"


def _domain_from_url(
    value: str,
) -> str | None:
    hostname = _hostname(value)

    if hostname is None:
        return None

    return _normalize_hostname(hostname)
