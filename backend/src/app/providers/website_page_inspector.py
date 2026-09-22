import codecs
import ipaddress
import re
import socket
import unicodedata
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup, Tag

WebsitePageLinkRegion = Literal[
    "page",
    "footer",
]


class WebsitePageInspectionError(Exception):
    pass


class UnsafeWebsitePageUrlError(WebsitePageInspectionError):
    pass


class OffsiteWebsitePageRedirectError(WebsitePageInspectionError):
    pass


class MissingWebsitePageError(WebsitePageInspectionError):
    def __init__(
        self,
        status_code: int,
    ) -> None:
        self.status_code = status_code
        super().__init__("Could not fetch website page")


@dataclass(frozen=True)
class WebsitePageLink:
    text: str
    url: str
    source_region: WebsitePageLinkRegion = "page"


@dataclass(frozen=True)
class WebsitePageInspection:
    requested_url: str
    final_url: str

    title: str | None
    description: str | None
    visible_text: str
    html: str

    links: tuple[WebsitePageLink, ...]


class WebsitePageInspector:
    _MAX_BODY_BYTES = 1_500_000
    _MAX_TEXT_LENGTH = 8_000
    _MAX_LINKS = 100
    _MAX_REDIRECTS = 5
    _FALLBACK_ENCODINGS = (
        "utf-8",
        "windows-1252",
        "iso-8859-1",
    )
    _CHARSET_RE = re.compile(
        r"(?:^|[;\s])charset\s*=\s*(?P<value>\"[^\"]+\"|'[^']+'|[^;\s/>]+)",
        re.IGNORECASE,
    )
    _HTML_META_RE = re.compile(
        r"<meta\b[^>]*>",
        re.IGNORECASE,
    )
    _MOJIBAKE_MARKER_RE = re.compile(r"(?:\u00c3.|\u00c2.|\u00e2.{0,2}|\u00c5.|\u00c4.)")

    def __init__(
        self,
        *,
        timeout: float = 12.0,
        user_agent: str = "SprawdzeniFachowcy/0.1 (website page inspection)",
    ) -> None:
        self._timeout = timeout
        self._user_agent = user_agent

    def inspect(
        self,
        url: str,
        *,
        same_site_hostname: str | None = None,
    ) -> WebsitePageInspection:
        self._ensure_safe_url(url)

        try:
            with httpx.Client(
                timeout=self._timeout,
                follow_redirects=False,
                headers={
                    "User-Agent": self._user_agent,
                    "Accept": "text/html,application/xhtml+xml",
                },
            ) as client:
                response = self._get_with_safe_redirects(
                    client,
                    url,
                    same_site_hostname=same_site_hostname,
                )

        except UnsafeWebsitePageUrlError:
            raise

        except WebsitePageInspectionError:
            raise

        except httpx.HTTPError as exc:
            raise WebsitePageInspectionError("Could not fetch website page") from exc

        content_type_header = response.headers.get("content-type", "")
        content_type = content_type_header.split(";")[0].strip().casefold()

        if content_type not in {
            "text/html",
            "application/xhtml+xml",
        }:
            raise WebsitePageInspectionError("Website page is not an HTML page")

        body = response.content

        if len(body) > self._MAX_BODY_BYTES:
            raise WebsitePageInspectionError("Website page HTML is too large")

        html = self._decode_html(
            body,
            content_type_header=content_type_header,
        )

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        self._remove_noise(soup)

        title = self._extract_title(soup)

        description = self._extract_description(soup)

        visible_text = self._extract_visible_text(soup)

        links = self._extract_links(
            soup,
            base_url=str(response.url),
        )

        return WebsitePageInspection(
            requested_url=url,
            final_url=str(response.url),
            title=title,
            description=description,
            visible_text=visible_text,
            html=html,
            links=tuple(links),
        )

    def _get_with_safe_redirects(
        self,
        client: httpx.Client,
        url: str,
        *,
        same_site_hostname: str | None,
    ) -> httpx.Response:
        current_url = url

        for _ in range(self._MAX_REDIRECTS + 1):
            self._ensure_safe_url(current_url)

            if same_site_hostname is not None and not self._same_site_url(
                same_site_hostname,
                current_url,
            ):
                raise OffsiteWebsitePageRedirectError("Redirect leaves the inspected website")

            response = client.get(current_url)

            if not response.is_redirect:
                if response.status_code in {
                    404,
                    410,
                }:
                    raise MissingWebsitePageError(response.status_code)

                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    raise WebsitePageInspectionError("Could not fetch website page") from exc

                return response

            location = response.headers.get("location")

            if not location:
                raise WebsitePageInspectionError("Redirect response has no Location header")

            current_url = urljoin(
                current_url,
                location,
            )

        raise WebsitePageInspectionError("Too many redirects")

    def _ensure_safe_url(
        self,
        url: str,
    ) -> None:
        parsed = urlsplit(url)

        if parsed.scheme not in {
            "http",
            "https",
        }:
            raise UnsafeWebsitePageUrlError("Only HTTP and HTTPS URLs are allowed")

        hostname = parsed.hostname

        if hostname is None:
            raise UnsafeWebsitePageUrlError("URL has no hostname")

        hostname = hostname.casefold().rstrip(".")

        if hostname in {
            "localhost",
            "localhost.localdomain",
        }:
            raise UnsafeWebsitePageUrlError("Local addresses are not allowed")

        try:
            addresses = socket.getaddrinfo(
                hostname,
                parsed.port or (443 if parsed.scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            )

        except socket.gaierror as exc:
            raise WebsitePageInspectionError("Could not resolve website page hostname") from exc

        if not addresses:
            raise WebsitePageInspectionError("Website page hostname resolved to no addresses")

        for address in addresses:
            raw_ip = address[4][0]

            ip = ipaddress.ip_address(raw_ip)

            if self._is_unsafe_ip(ip):
                raise UnsafeWebsitePageUrlError(
                    "Website page resolves to a private or unsafe address"
                )

    @staticmethod
    def _is_unsafe_ip(
        ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
    ) -> bool:
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        )

    @staticmethod
    def _remove_noise(
        soup: BeautifulSoup,
    ) -> None:
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

    def _extract_title(
        self,
        soup: BeautifulSoup,
    ) -> str | None:
        if soup.title is None:
            return None

        value = self._normalize_text(
            soup.title.get_text(
                " ",
                strip=True,
            )
        )

        return value or None

    def _extract_description(
        self,
        soup: BeautifulSoup,
    ) -> str | None:
        meta = soup.find(
            "meta",
            attrs={
                "name": re.compile(
                    r"^description$",
                    re.IGNORECASE,
                )
            },
        )

        if not isinstance(
            meta,
            Tag,
        ):
            return None

        content = meta.get("content")

        if not isinstance(
            content,
            str,
        ):
            return None

        value = self._normalize_text(content)

        return value or None

    def _extract_visible_text(
        self,
        soup: BeautifulSoup,
    ) -> str:
        body = soup.body or soup

        text = self._normalize_text(
            body.get_text(
                " ",
                strip=True,
            )
        )

        if len(text) > self._MAX_TEXT_LENGTH:
            text = text[: self._MAX_TEXT_LENGTH].rstrip()

        return text

    def _extract_links(
        self,
        soup: BeautifulSoup,
        *,
        base_url: str,
    ) -> list[WebsitePageLink]:
        result: list[WebsitePageLink] = []

        seen: set[str] = set()

        for link in soup.find_all(
            "a",
            href=True,
        ):
            href = link.get("href")

            if not isinstance(
                href,
                str,
            ):
                continue

            href = href.strip()

            if not href:
                continue

            if href.startswith(
                (
                    "#",
                    "javascript:",
                    "mailto:",
                    "tel:",
                )
            ):
                continue

            absolute_url = urljoin(
                base_url,
                href,
            )

            if absolute_url in seen:
                continue

            parsed = urlsplit(absolute_url)

            if parsed.scheme not in {
                "http",
                "https",
            }:
                continue

            text = self._normalize_text(
                link.get_text(
                    " ",
                    strip=True,
                )
            )

            source_region: WebsitePageLinkRegion = (
                "footer" if link.find_parent("footer") is not None else "page"
            )

            seen.add(absolute_url)

            result.append(
                WebsitePageLink(
                    text=text,
                    url=absolute_url,
                    source_region=source_region,
                )
            )

            if len(result) >= self._MAX_LINKS:
                break

        return result

    @classmethod
    def _decode_html(
        cls,
        body: bytes,
        *,
        content_type_header: str,
    ) -> str:
        candidates = cls._encoding_candidates(
            body,
            content_type_header=content_type_header,
        )
        decoded_candidates: list[tuple[int, int, str]] = []

        for index, encoding in enumerate(candidates):
            try:
                decoded = body.decode(
                    encoding,
                    errors="strict",
                )
                replacement_count = 0
            except UnicodeDecodeError:
                decoded = body.decode(
                    encoding,
                    errors="replace",
                )
                replacement_count = decoded.count("\ufffd")

            decoded_candidates.append(
                (
                    cls._decoded_text_penalty(
                        decoded,
                        replacement_count=replacement_count,
                    ),
                    index,
                    decoded,
                )
            )

        return min(decoded_candidates)[2]

    @classmethod
    def _encoding_candidates(
        cls,
        body: bytes,
        *,
        content_type_header: str,
    ) -> list[str]:
        candidates: list[str] = []

        for encoding in (
            cls._charset_from_content_type(content_type_header),
            cls._charset_from_html_meta(body),
            *cls._FALLBACK_ENCODINGS,
        ):
            normalized = cls._normalize_encoding(encoding)

            if normalized and normalized not in candidates:
                candidates.append(normalized)

        return candidates or ["utf-8"]

    @classmethod
    def _charset_from_content_type(
        cls,
        content_type: str | None,
    ) -> str | None:
        if not content_type:
            return None

        match = cls._CHARSET_RE.search(content_type)

        if match is None:
            return None

        return match.group("value").strip().strip("\"'")

    @classmethod
    def _charset_from_html_meta(
        cls,
        body: bytes,
    ) -> str | None:
        head = body[:4096].decode(
            "ascii",
            errors="ignore",
        )

        for meta in cls._HTML_META_RE.findall(head):
            charset = cls._charset_from_content_type(meta)

            if charset:
                return charset

        return None

    @staticmethod
    def _normalize_encoding(
        encoding: str | None,
    ) -> str | None:
        if encoding is None:
            return None

        try:
            return codecs.lookup(encoding.strip()).name
        except LookupError:
            return None

    @classmethod
    def _decoded_text_penalty(
        cls,
        value: str,
        *,
        replacement_count: int,
    ) -> int:
        mojibake_count = len(cls._MOJIBAKE_MARKER_RE.findall(value))
        control_count = sum(
            1
            for character in value
            if unicodedata.category(character) == "Cc" and character not in "\n\r\t"
        )

        return (replacement_count * 100) + (mojibake_count * 10) + control_count

    @classmethod
    def _same_site_url(
        cls,
        expected_hostname: str,
        url: str,
    ) -> bool:
        hostname = urlsplit(url).hostname

        if hostname is None:
            return False

        return cls._normalize_hostname(hostname) == cls._normalize_hostname(expected_hostname)

    @staticmethod
    def _normalize_hostname(
        hostname: str,
    ) -> str:
        return hostname.casefold().rstrip(".").removeprefix("www.")

    @staticmethod
    def _normalize_text(
        value: str,
    ) -> str:
        return re.sub(
            r"\s+",
            " ",
            value,
        ).strip()
