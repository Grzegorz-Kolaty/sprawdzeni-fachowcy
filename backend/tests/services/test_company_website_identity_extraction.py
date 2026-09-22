from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from app.providers.website_page_inspector import (
    MissingWebsitePageError,
    WebsitePageInspection,
    WebsitePageInspectionError,
    WebsitePageLink,
)
from app.services.company_website_identity_extraction import (
    CompanyWebsiteIdentityExtraction,
    CompanyWebsiteIdentityExtractor,
)


class FakeWebsitePageInspector:
    def __init__(
        self,
        pages: dict[str, WebsitePageInspection],
        *,
        errors: dict[str, WebsitePageInspectionError] | None = None,
    ) -> None:
        self.pages = {self._canonical_url(url): page for url, page in pages.items()}
        self.errors = {self._canonical_url(url): error for url, error in (errors or {}).items()}
        self.calls: list[tuple[str, str | None]] = []

    def inspect(
        self,
        url: str,
        *,
        same_site_hostname: str | None = None,
    ) -> WebsitePageInspection:
        self.calls.append(
            (
                url,
                same_site_hostname,
            )
        )

        canonical_url = self._canonical_url(url)
        error = self.errors.get(canonical_url)

        if error is not None:
            raise error

        page = self.pages.get(canonical_url)

        if page is None:
            raise WebsitePageInspectionError("fake page not found")

        return page

    @staticmethod
    def _canonical_url(
        url: str,
    ) -> str:
        parsed = urlsplit(url)
        hostname = (parsed.hostname or "").casefold().rstrip(".").removeprefix("www.")
        path = parsed.path.rstrip("/") or "/"

        return f"{parsed.scheme.casefold()}://{hostname}{path}"


def _page(
    url: str,
    html: str,
    *,
    links: tuple[WebsitePageLink, ...] = (),
    title: str | None = None,
) -> WebsitePageInspection:
    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    return WebsitePageInspection(
        requested_url=url,
        final_url=url,
        title=title if title is not None else _title_from_soup(soup),
        description=None,
        visible_text=soup.get_text(" ", strip=True),
        html=html,
        links=links,
    )


def _title_from_soup(
    soup: BeautifulSoup,
) -> str | None:
    if soup.title is None:
        return None

    title = soup.title.get_text(" ", strip=True)

    return title or None


def _extract(
    pages: dict[str, WebsitePageInspection],
    *,
    candidate_url: str = "https://example.test/",
    max_pages: int = 1,
) -> CompanyWebsiteIdentityExtraction:
    inspector = FakeWebsitePageInspector(pages)
    extractor = CompanyWebsiteIdentityExtractor(
        inspector,
        max_pages=max_pages,
    )

    return extractor.extract(candidate_url)


def _values(
    result: CompanyWebsiteIdentityExtraction,
    field: str,
) -> list[str]:
    return [clue.value for clue in result.identity_clues if clue.field == field]


def _clues(
    result: CompanyWebsiteIdentityExtraction,
    field: str,
):
    return [clue for clue in result.identity_clues if clue.field == field]


def test_extracts_nip_from_visible_page_text() -> None:
    result = _extract(
        {
            "https://example.test/": _page(
                "https://example.test/",
                "<html><body>Dane firmy: NIP: 123-456-78-90</body></html>",
            )
        }
    )

    assert "1234567890" in _values(result, "nip")


def test_extracts_regon_and_krs_from_visible_page_text() -> None:
    result = _extract(
        {
            "https://example.test/": _page(
                "https://example.test/",
                "<html><body>REGON 123456789 KRS 0000123456</body></html>",
            )
        }
    )

    assert "123456789" in _values(result, "regon")
    assert "0000123456" in _values(result, "krs")


def test_extracts_email_and_phone_from_text_and_links() -> None:
    result = _extract(
        {
            "https://example.test/": _page(
                "https://example.test/",
                """
                <html><body>
                  Email: biuro@example.test
                  Telefon: +48 123 456 789
                  <a href="mailto:kontakt@example.test">mail</a>
                  <a href="tel:+48987654321">phone</a>
                </body></html>
                """,
            )
        }
    )

    assert "biuro@example.test" in _values(result, "email")
    assert "kontakt@example.test" in _values(result, "email")
    assert "+48123456789" in _values(result, "phone")
    assert "+48987654321" in _values(result, "phone")


def test_canonicalizes_phone_numbers_before_deduplication() -> None:
    result = _extract(
        {
            "https://example.test/": _page(
                "https://example.test/",
                """
                <html><body>
                  Telefon: 48 502 634 501
                  <a href="tel:+48502634501">phone</a>
                </body></html>
                """,
            )
        }
    )

    phone_clues = _clues(result, "phone")

    assert [clue.value for clue in phone_clues] == ["+48502634501"]
    assert phone_clues[0].source_kind == "page_text"


def test_extracts_address_parts_from_visible_page_text() -> None:
    result = _extract(
        {
            "https://example.test/": _page(
                "https://example.test/",
                "<html><body>Adres: ul. Kwiatowa 12, 00-001 Warszawa</body></html>",
            )
        }
    )

    assert "ul. Kwiatowa 12" in _values(result, "street_address")
    assert "00-001" in _values(result, "postal_code")
    assert "Warszawa" in _values(result, "city")


def test_extracts_identity_clues_from_json_ld_organization() -> None:
    result = _extract(
        {
            "https://example.test/": _page(
                "https://example.test/",
                """
                <html><head>
                  <script type="application/ld+json">
                    {
                      "@context": "https://schema.org",
                      "@type": "Organization",
                      "name": "Example Trading",
                      "legalName": "Example Legal Sp. z o.o.",
                      "taxID": "PL1234567890",
                      "email": "office@example.test",
                      "telephone": "+48 111 222 333",
                      "url": "https://www.example.test/",
                      "address": {
                        "@type": "PostalAddress",
                        "streetAddress": "ul. Prosta 5",
                        "postalCode": "00-002",
                        "addressLocality": "Krakow"
                      }
                    }
                  </script>
                </head><body></body></html>
                """,
            )
        }
    )

    assert "Example Trading" in _values(result, "display_name")
    assert "Example Legal Sp. z o.o." in _values(result, "legal_company_name")
    assert "1234567890" in _values(result, "nip")
    assert "office@example.test" in _values(result, "email")
    assert "+48111222333" in _values(result, "phone")
    assert "example.test" in _values(result, "website_domain")
    assert "ul. Prosta 5" in _values(result, "street_address")
    assert "00-002" in _values(result, "postal_code")
    assert "Krakow" in _values(result, "city")
    assert all(clue.source_kind == "json_ld" for clue in _clues(result, "legal_company_name"))


def test_discovers_and_inspects_same_site_identity_pages() -> None:
    inspector = FakeWebsitePageInspector(
        {
            "https://example.test/": _page(
                "https://example.test/",
                "<html><body>Home</body></html>",
                links=(
                    WebsitePageLink(
                        text="Kontakt",
                        url="https://example.test/kontakt",
                        source_region="footer",
                    ),
                ),
            ),
            "https://example.test/kontakt": _page(
                "https://example.test/kontakt",
                "<html><body>NIP 1234567890</body></html>",
            ),
        }
    )
    extractor = CompanyWebsiteIdentityExtractor(
        inspector,
        max_pages=2,
    )

    result = extractor.extract("https://example.test/")

    assert [url for url, _hostname in inspector.calls] == [
        "https://example.test/",
        "https://example.test/kontakt",
    ]
    assert "1234567890" in _values(result, "nip")


def test_expected_missing_speculative_pages_are_not_reported_as_errors() -> None:
    inspector = FakeWebsitePageInspector(
        {
            "https://example.test/": _page(
                "https://example.test/",
                "<html><body>Home</body></html>",
            ),
            "https://example.test/about": _page(
                "https://example.test/about",
                "<html><body>NIP 1234567890</body></html>",
            ),
        },
        errors={
            "https://example.test/contact": MissingWebsitePageError(404),
            "https://example.test/kontakt": WebsitePageInspectionError("timed out"),
        },
    )
    extractor = CompanyWebsiteIdentityExtractor(
        inspector,
        max_pages=2,
    )

    result = extractor.extract("https://example.test/")

    assert result.errors == ("https://example.test/kontakt: timed out",)
    assert "1234567890" in _values(result, "nip")


def test_external_links_are_not_crawled() -> None:
    inspector = FakeWebsitePageInspector(
        {
            "https://example.test/": _page(
                "https://example.test/",
                "<html><body>Home</body></html>",
                links=(
                    WebsitePageLink(
                        text="Kontakt",
                        url="https://external.test/contact",
                        source_region="footer",
                    ),
                ),
            ),
            "https://example.test/contact": _page(
                "https://example.test/contact",
                "<html><body>No identity here</body></html>",
            ),
        }
    )
    extractor = CompanyWebsiteIdentityExtractor(
        inspector,
        max_pages=2,
    )

    extractor.extract("https://example.test/")

    assert "https://external.test/contact" not in [url for url, _hostname in inspector.calls]


def test_duplicate_pages_are_not_inspected_twice() -> None:
    inspector = FakeWebsitePageInspector(
        {
            "https://example.test/": _page(
                "https://example.test/",
                "<html><body>Home</body></html>",
                links=(
                    WebsitePageLink(
                        text="Kontakt",
                        url="https://example.test/kontakt",
                    ),
                    WebsitePageLink(
                        text="Kontakt duplicate",
                        url="https://www.example.test/kontakt?from=footer#top",
                    ),
                ),
            ),
            "https://example.test/kontakt": _page(
                "https://example.test/kontakt",
                "<html><body>Email: kontakt@example.test</body></html>",
            ),
        }
    )
    extractor = CompanyWebsiteIdentityExtractor(
        inspector,
        max_pages=3,
    )

    extractor.extract("https://example.test/")

    inspected_contact_urls = [
        url for url, _hostname in inspector.calls if urlsplit(url).path.rstrip("/") == "/kontakt"
    ]

    assert inspected_contact_urls == ["https://example.test/kontakt"]


def test_malformed_or_missing_identity_data_does_not_crash() -> None:
    result = _extract(
        {
            "https://example.test/": _page(
                "https://example.test/",
                """
                <html><head>
                  <script type="application/ld+json">{ malformed json</script>
                </head><body>No identifiers here</body></html>
                """,
            )
        }
    )

    assert result.inspected_pages
    assert _values(result, "nip") == []


def test_generic_page_title_is_distinguished_from_stronger_name_sources() -> None:
    result = _extract(
        {
            "https://example.test/": _page(
                "https://example.test/",
                """
                <html>
                  <head>
                    <title>Cheap roof repair and service in Harbor</title>
                    <script type="application/ld+json">
                      {
                        "@context": "https://schema.org",
                        "@type": "LocalBusiness",
                        "name": "Example Roofing"
                      }
                    </script>
                  </head>
                  <body>Firma: Example Roofing LLC</body>
                </html>
                """,
            )
        }
    )

    display_clues = _clues(result, "display_name")

    assert [(clue.value, clue.source_kind) for clue in display_clues] == [
        ("Example Roofing", "json_ld"),
        ("Cheap roof repair and service in Harbor", "html_title"),
    ]
    assert [(clue.value, clue.source_kind) for clue in _clues(result, "legal_company_name")] == [
        ("Example Roofing LLC", "page_text")
    ]


def test_extracted_values_retain_source_provenance() -> None:
    result = _extract(
        {
            "https://example.test/": _page(
                "https://example.test/",
                "<html><body>NIP 1234567890</body></html>",
            )
        }
    )

    nip_clue = _clues(result, "nip")[0]

    assert nip_clue.value == "1234567890"
    assert nip_clue.source_url == "https://example.test/"
    assert nip_clue.source_kind == "page_text"


def test_identity_extraction_has_no_database_dependency_or_persistence() -> None:
    inspector = FakeWebsitePageInspector(
        {
            "https://example.test/": _page(
                "https://example.test/",
                "<html><body>NIP 1234567890</body></html>",
            )
        }
    )
    extractor = CompanyWebsiteIdentityExtractor(
        inspector,
        max_pages=1,
    )

    result = extractor.extract("https://example.test/")

    assert "1234567890" in _values(result, "nip")
    assert not hasattr(extractor, "_db")
    assert not hasattr(inspector, "_db")
