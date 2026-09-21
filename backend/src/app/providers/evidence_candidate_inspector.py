import ipaddress
import re
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup, Tag


class EvidenceCandidateInspectionError(Exception):
    pass


class UnsafeEvidenceCandidateUrlError(EvidenceCandidateInspectionError):
    pass


@dataclass(frozen=True)
class EvidenceCandidateLink:
    text: str
    url: str


@dataclass(frozen=True)
class EvidenceCandidateInspection:
    requested_url: str
    final_url: str

    title: str | None
    description: str | None
    visible_text: str

    links: tuple[EvidenceCandidateLink, ...]


class EvidenceCandidateInspector:
    _MAX_BODY_BYTES = 1_500_000
    _MAX_TEXT_LENGTH = 8_000
    _MAX_LINKS = 100
    _MAX_REDIRECTS = 5

    def __init__(
        self,
        *,
        timeout: float = 12.0,
    ) -> None:
        self._timeout = timeout

    def inspect(
        self,
        url: str,
    ) -> EvidenceCandidateInspection:
        self._ensure_safe_url(url)

        try:
            with httpx.Client(
                timeout=self._timeout,
                follow_redirects=False,
                headers={
                    "User-Agent": ("SprawdzeniFachowcy/0.1 (evidence inspection)"),
                    "Accept": ("text/html,application/xhtml+xml"),
                },
            ) as client:
                response = self._get_with_safe_redirects(
                    client,
                    url,
                )

        except UnsafeEvidenceCandidateUrlError:
            raise

        except httpx.HTTPError as exc:
            raise EvidenceCandidateInspectionError("Could not fetch evidence candidate") from exc

        content_type = response.headers.get("content-type", "").split(";")[0].strip().casefold()

        if content_type not in {
            "text/html",
            "application/xhtml+xml",
        }:
            raise EvidenceCandidateInspectionError("Evidence candidate is not an HTML page")

        body = response.content

        if len(body) > self._MAX_BODY_BYTES:
            raise EvidenceCandidateInspectionError("Evidence candidate HTML is too large")

        html = response.text

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

        return EvidenceCandidateInspection(
            requested_url=url,
            final_url=str(response.url),
            title=title,
            description=description,
            visible_text=visible_text,
            links=tuple(links),
        )

    def _get_with_safe_redirects(
        self,
        client: httpx.Client,
        url: str,
    ) -> httpx.Response:
        current_url = url

        for _ in range(self._MAX_REDIRECTS + 1):
            self._ensure_safe_url(current_url)

            response = client.get(current_url)

            if not response.is_redirect:
                response.raise_for_status()
                return response

            location = response.headers.get("location")

            if not location:
                raise EvidenceCandidateInspectionError("Redirect response has no Location header")

            current_url = urljoin(
                current_url,
                location,
            )

        raise EvidenceCandidateInspectionError("Too many redirects")

    def _ensure_safe_url(
        self,
        url: str,
    ) -> None:
        parsed = urlsplit(url)

        if parsed.scheme not in {
            "http",
            "https",
        }:
            raise UnsafeEvidenceCandidateUrlError("Only HTTP and HTTPS URLs are allowed")

        hostname = parsed.hostname

        if hostname is None:
            raise UnsafeEvidenceCandidateUrlError("URL has no hostname")

        hostname = hostname.casefold().rstrip(".")

        if hostname in {
            "localhost",
            "localhost.localdomain",
        }:
            raise UnsafeEvidenceCandidateUrlError("Local addresses are not allowed")

        try:
            addresses = socket.getaddrinfo(
                hostname,
                parsed.port or (443 if parsed.scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            )

        except socket.gaierror as exc:
            raise EvidenceCandidateInspectionError(
                "Could not resolve evidence candidate hostname"
            ) from exc

        if not addresses:
            raise EvidenceCandidateInspectionError(
                "Evidence candidate hostname resolved to no addresses"
            )

        for address in addresses:
            raw_ip = address[4][0]

            ip = ipaddress.ip_address(raw_ip)

            if self._is_unsafe_ip(ip):
                raise UnsafeEvidenceCandidateUrlError(
                    "Evidence candidate resolves to a private or unsafe address"
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
    ) -> list[EvidenceCandidateLink]:
        result: list[EvidenceCandidateLink] = []

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

            seen.add(absolute_url)

            result.append(
                EvidenceCandidateLink(
                    text=text,
                    url=absolute_url,
                )
            )

            if len(result) >= self._MAX_LINKS:
                break

        return result

    @staticmethod
    def _normalize_text(
        value: str,
    ) -> str:
        return re.sub(
            r"\s+",
            " ",
            value,
        ).strip()
