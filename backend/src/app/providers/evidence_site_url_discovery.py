import heapq
import ipaddress
import re
import socket
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urljoin, urlsplit

import httpx

_POLISH_TRANSLATION = str.maketrans(
    {
        "ł": "l",
        "Ł": "L",
    }
)

SitemapEntryType = Literal[
    "url",
    "sitemap",
]

_IGNORED_RESOURCE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".svg",
    ".ico",
    ".avif",
    ".bmp",
    ".mp4",
    ".webm",
    ".mov",
    ".mp3",
    ".wav",
    ".ogg",
    ".css",
    ".js",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
}


@dataclass(frozen=True)
class ScoredEvidenceSiteUrl:
    url: str
    score: int
    matched_tokens: tuple[str, ...]


@dataclass(frozen=True)
class EvidenceSiteUrlDiscovery:
    candidates: tuple[ScoredEvidenceSiteUrl, ...]

    scanned_locations: int

    errors: tuple[str, ...]


class EvidenceSiteUrlDiscoveryProvider:
    _MAX_SITEMAPS = 5
    _MAX_LOCATIONS_SCANNED = 10_000
    _MAX_CANDIDATES = 30
    _MAX_SITEMAP_BYTES = 5_000_000
    _MAX_ROBOTS_BYTES = 256_000
    _MAX_REDIRECTS = 5

    @classmethod
    def _is_candidate_resource(
        cls,
        url: str,
    ) -> bool:
        path = urlsplit(url).path.casefold()

        return not any(path.endswith(extension) for extension in _IGNORED_RESOURCE_EXTENSIONS)

    def discover(
        self,
        start_url: str,
        *,
        claim_text: str,
        claimed_entity: str | None,
    ) -> EvidenceSiteUrlDiscovery:
        start_host = self._hostname(start_url)

        if start_host is None:
            return EvidenceSiteUrlDiscovery(
                candidates=(),
                scanned_locations=0,
                errors=("Start URL has no hostname",),
            )

        query_tokens = self._build_query_tokens(
            claim_text=claim_text,
            claimed_entity=claimed_entity,
        )

        base_url = self._base_url(start_url)

        sitemap_urls = self._discover_sitemap_urls(base_url)

        sitemap_queue = list(sitemap_urls)

        seen_sitemaps: set[str] = set()
        seen_pages: set[str] = set()

        #
        # Min-heap:
        #
        # przechowujemy WYŁĄCZNIE
        # 30 najlepszych URL-i.
        #
        candidate_heap: list[
            tuple[
                int,
                int,
                str,
                tuple[str, ...],
            ]
        ] = []

        sequence = 0
        scanned_locations = 0

        errors: list[str] = []

        while (
            sitemap_queue
            and len(seen_sitemaps) < self._MAX_SITEMAPS
            and scanned_locations < self._MAX_LOCATIONS_SCANNED
        ):
            sitemap_url = sitemap_queue.pop(0)

            canonical_sitemap = self._canonical_url(sitemap_url)

            if canonical_sitemap in seen_sitemaps:
                continue

            seen_sitemaps.add(canonical_sitemap)

            try:
                entries = self._stream_sitemap_entries(sitemap_url)

                for (
                    entry_type,
                    location,
                ) in entries:
                    if scanned_locations >= self._MAX_LOCATIONS_SCANNED:
                        break

                    hostname = self._hostname(location)

                    if hostname is None:
                        continue

                    if not self._same_site(
                        start_host,
                        hostname,
                    ):
                        continue

                    if entry_type == "sitemap":
                        canonical_child = self._canonical_url(location)

                        if canonical_child not in seen_sitemaps:
                            sitemap_queue.append(location)

                        continue

                    scanned_locations += 1

                    if not self._is_candidate_resource(location):
                        continue

                    canonical_page = self._canonical_url(location)

                    if canonical_page in seen_pages:
                        continue

                    seen_pages.add(canonical_page)

                    (
                        score,
                        matched_tokens,
                    ) = self._url_score(
                        location,
                        query_tokens=(query_tokens),
                    )

                    if score <= 0:
                        continue

                    sequence += 1

                    candidate = (
                        score,
                        sequence,
                        location,
                        matched_tokens,
                    )

                    if len(candidate_heap) < self._MAX_CANDIDATES:
                        heapq.heappush(
                            candidate_heap,
                            candidate,
                        )

                    elif score > candidate_heap[0][0]:
                        heapq.heapreplace(
                            candidate_heap,
                            candidate,
                        )

            except Exception as exc:
                errors.append(f"{sitemap_url}: {exc}")

        ranked = sorted(
            candidate_heap,
            key=lambda item: (
                -item[0],
                item[1],
            ),
        )

        candidates = tuple(
            ScoredEvidenceSiteUrl(
                url=url,
                score=score,
                matched_tokens=(matched_tokens),
            )
            for (
                score,
                _sequence,
                url,
                matched_tokens,
            ) in ranked
        )

        return EvidenceSiteUrlDiscovery(
            candidates=candidates,
            scanned_locations=(scanned_locations),
            errors=tuple(errors),
        )

    def _discover_sitemap_urls(
        self,
        base_url: str,
    ) -> list[str]:
        result: list[str] = []

        robots_url = urljoin(
            base_url,
            "/robots.txt",
        )

        try:
            robots = self._fetch_small_text(
                robots_url,
                max_bytes=(self._MAX_ROBOTS_BYTES),
            )

            for line in robots.splitlines():
                (
                    key,
                    separator,
                    value,
                ) = line.partition(":")

                if not separator:
                    continue

                if key.strip().casefold() != "sitemap":
                    continue

                sitemap_url = value.strip()

                if sitemap_url:
                    result.append(sitemap_url)

        except Exception:
            pass

        #
        # Standardowe fallbacki.
        #
        result.extend(
            [
                urljoin(
                    base_url,
                    "/sitemap.xml",
                ),
                urljoin(
                    base_url,
                    "/sitemap_index.xml",
                ),
            ]
        )

        deduplicated: list[str] = []
        seen: set[str] = set()

        for url in result:
            canonical = self._canonical_url(url)

            if canonical in seen:
                continue

            seen.add(canonical)

            deduplicated.append(url)

        return deduplicated

    def _stream_sitemap_entries(
        self,
        url: str,
    ):
        current_url = url

        for _ in range(self._MAX_REDIRECTS + 1):
            self._validate_public_url(current_url)

            with httpx.Client(
                timeout=20.0,
                follow_redirects=False,
                headers={"User-Agent": ("SprawdzeniFachowcy/0.1 (sitemap discovery)")},
            ) as client:
                with client.stream(
                    "GET",
                    current_url,
                ) as response:
                    if response.status_code in {
                        301,
                        302,
                        303,
                        307,
                        308,
                    }:
                        location = response.headers.get("location")

                        if not location:
                            raise RuntimeError("Redirect without Location")

                        current_url = urljoin(
                            current_url,
                            location,
                        )

                        continue

                    response.raise_for_status()

                    parser = ET.XMLPullParser(
                        events=(
                            "start",
                            "end",
                        )
                    )

                    root_type: SitemapEntryType | None = None

                    bytes_read = 0

                    for chunk in response.iter_bytes():
                        bytes_read += len(chunk)

                        if bytes_read > self._MAX_SITEMAP_BYTES:
                            raise RuntimeError("Sitemap scan byte limit exceeded")

                        parser.feed(chunk)

                        for (
                            event,
                            element,
                        ) in parser.read_events():
                            tag = self._local_xml_name(element.tag)

                            if event == "start" and root_type is None:
                                if tag == "sitemapindex":
                                    root_type = "sitemap"

                                elif tag == "urlset":
                                    root_type = "url"

                                continue

                            if event != "end" or tag != "loc":
                                continue

                            value = (element.text or "").strip()

                            element.clear()

                            if not value:
                                continue

                            yield (
                                root_type or "url",
                                value,
                            )

                    return

        raise RuntimeError("Too many redirects")

    def _fetch_small_text(
        self,
        url: str,
        *,
        max_bytes: int,
    ) -> str:
        current_url = url

        for _ in range(self._MAX_REDIRECTS + 1):
            self._validate_public_url(current_url)

            with httpx.Client(
                timeout=10.0,
                follow_redirects=False,
                headers={"User-Agent": ("SprawdzeniFachowcy/0.1 (site discovery)")},
            ) as client:
                with client.stream(
                    "GET",
                    current_url,
                ) as response:
                    if response.status_code in {
                        301,
                        302,
                        303,
                        307,
                        308,
                    }:
                        location = response.headers.get("location")

                        if not location:
                            raise RuntimeError("Redirect without Location")

                        current_url = urljoin(
                            current_url,
                            location,
                        )

                        continue

                    response.raise_for_status()

                    body = bytearray()

                    for chunk in response.iter_bytes():
                        body.extend(chunk)

                        if len(body) > max_bytes:
                            raise RuntimeError("Response body too large")

                    encoding = response.encoding or "utf-8"

                    return body.decode(
                        encoding,
                        errors="replace",
                    )

        raise RuntimeError("Too many redirects")

    def _url_score(
        self,
        url: str,
        *,
        query_tokens: set[str],
    ) -> tuple[
        int,
        tuple[str, ...],
    ]:
        parsed = urlsplit(url)

        url_tokens = self._tokens(parsed.path)

        matched = {
            query_token
            for query_token in query_tokens
            if any(
                self._tokens_related(
                    query_token,
                    url_token,
                )
                for url_token in url_tokens
            )
        }

        if not matched:
            return 0, ()

        #
        # Każdy semantycznie pasujący
        # token daje 10 punktów.
        #
        score = len(matched) * 10

        return (
            score,
            tuple(sorted(matched)),
        )

    def _build_query_tokens(
        self,
        *,
        claim_text: str,
        claimed_entity: str | None,
    ) -> set[str]:
        ignored = {
            "firma",
            "jest",
            "jestesmy",
            "posiada",
            "mamy",
            "nasz",
            "nasza",
            "system",
            "systems",
            "the",
            "and",
            "with",
        }

        result = self._tokens(claim_text)

        if claimed_entity:
            result |= self._tokens(claimed_entity)

        return {token for token in result if token not in ignored}

    def _tokens(
        self,
        value: str,
    ) -> set[str]:
        normalized = self._normalize_text(value)

        return {
            token
            for token in re.findall(
                r"[a-z0-9]+",
                normalized,
            )
            if len(token) >= 3
        }

    @staticmethod
    def _tokens_related(
        first: str,
        second: str,
    ) -> bool:
        if first == second:
            return True

        shorter_length = min(
            len(first),
            len(second),
        )

        #
        # BTR, PSD itd. muszą
        # pasować dokładnie.
        #
        if shorter_length < 7:
            return False

        common_prefix_length = 0

        for left, right in zip(
            first,
            second,
            strict=False,
        ):
            if left != right:
                break

            common_prefix_length += 1

        return common_prefix_length >= 7

    def _validate_public_url(
        self,
        url: str,
    ) -> None:
        parsed = urlsplit(url)

        if parsed.scheme not in {
            "http",
            "https",
        }:
            raise RuntimeError("Unsupported URL scheme")

        hostname = parsed.hostname

        if hostname is None:
            raise RuntimeError("URL has no hostname")

        try:
            addresses = socket.getaddrinfo(
                hostname,
                parsed.port or (443 if parsed.scheme == "https" else 80),
                type=(socket.SOCK_STREAM),
            )

        except socket.gaierror as exc:
            raise RuntimeError("Could not resolve hostname") from exc

        if not addresses:
            raise RuntimeError("Hostname has no addresses")

        for address in addresses:
            ip = ipaddress.ip_address(address[4][0])

            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
                or ip.is_unspecified
            ):
                raise RuntimeError("Unsafe hostname address")

    @staticmethod
    def _local_xml_name(
        tag: str,
    ) -> str:
        return tag.rsplit(
            "}",
            1,
        )[-1].casefold()

    @staticmethod
    def _base_url(
        url: str,
    ) -> str:
        parsed = urlsplit(url)

        return f"{parsed.scheme}://{parsed.netloc}/"

    @staticmethod
    def _hostname(
        url: str,
    ) -> str | None:
        hostname = urlsplit(url).hostname

        if hostname is None:
            return None

        return hostname.casefold().rstrip(".").removeprefix("www.")

    @staticmethod
    def _same_site(
        first: str,
        second: str,
    ) -> bool:
        first = first.casefold().removeprefix("www.")

        second = second.casefold().removeprefix("www.")

        return first == second or first.endswith(f".{second}") or second.endswith(f".{first}")

    @staticmethod
    def _canonical_url(
        url: str,
    ) -> str:
        parsed = urlsplit(url)

        hostname = (parsed.hostname or "").casefold()

        if hostname.startswith("www."):
            hostname = hostname[4:]

        path = parsed.path.rstrip("/") or "/"

        return f"{parsed.scheme.casefold()}://{hostname}{path}"

    @staticmethod
    def _normalize_text(
        value: str,
    ) -> str:
        value = value.translate(_POLISH_TRANSLATION)

        value = value.casefold()

        value = unicodedata.normalize(
            "NFKD",
            value,
        )

        value = "".join(character for character in value if not unicodedata.combining(character))

        value = re.sub(
            r"[^a-z0-9]+",
            " ",
            value,
        )

        return re.sub(
            r"\s+",
            " ",
            value,
        ).strip()
