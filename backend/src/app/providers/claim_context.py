import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, NavigableString, Tag


@dataclass(frozen=True)
class ClaimContextLink:
    text: str
    url: str
    external: bool
    distance: int
    relevance: int


@dataclass(frozen=True)
class ClaimContextImage:
    alt: str | None
    src: str | None
    distance: int
    relevance: int


@dataclass(frozen=True)
class ClaimContext:
    trigger_text: str
    heading: str | None
    nearby_text: str
    links: tuple[ClaimContextLink, ...]
    images: tuple[ClaimContextImage, ...]


class ClaimContextExtractor:
    def extract_best(
        self,
        html: str,
        *,
        source_url: str,
        claim_text: str,
        claimed_entity: str | None,
    ) -> ClaimContext | None:
        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        self._remove_noise(soup)

        normalized_claim = self._normalize_text(claim_text)

        contexts: list[ClaimContext] = []

        for node in soup.find_all(string=True):
            if not isinstance(
                node,
                NavigableString,
            ):
                continue

            node_text = self._normalize_text(str(node))

            if node_text != normalized_claim:
                continue

            parent = node.parent

            if not isinstance(
                parent,
                Tag,
            ):
                continue

            containers = self._find_context_containers(parent)

            for container in containers:
                context = self._build_context(
                    trigger_node=parent,
                    container=container,
                    trigger_text=node_text,
                    source_url=source_url,
                    claimed_entity=(claimed_entity),
                )

                contexts.append(context)

        if not contexts:
            return None

        contexts.sort(key=self._context_sort_key)

        return contexts[0]

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
            ]
        ):
            tag.decompose()

    def _find_context_containers(
        self,
        start: Tag,
    ) -> list[Tag]:
        result: list[Tag] = []
        seen: set[int] = set()

        current: Tag | None = start

        for _ in range(9):
            if current is None:
                break

            identifier = id(current)

            if identifier not in seen:
                text = self._normalize_text(
                    current.get_text(
                        " ",
                        strip=True,
                    )
                )

                if 10 <= len(text) <= 2500:
                    result.append(current)

                    seen.add(identifier)

            parent = current.parent

            if not isinstance(
                parent,
                Tag,
            ):
                break

            current = parent

        return result

    def _build_context(
        self,
        *,
        trigger_node: Tag,
        container: Tag,
        trigger_text: str,
        source_url: str,
        claimed_entity: str | None,
    ) -> ClaimContext:
        nearby_text = self._normalize_text(
            container.get_text(
                " ",
                strip=True,
            )
        )

        if len(nearby_text) > 2000:
            nearby_text = nearby_text[:2000].rstrip()

        heading = self._find_heading(
            trigger_node,
            container,
        )

        links = self._extract_links(
            trigger_node=trigger_node,
            container=container,
            source_url=source_url,
            claimed_entity=(claimed_entity),
        )

        images = self._extract_images(
            trigger_node=trigger_node,
            container=container,
            source_url=source_url,
            claimed_entity=(claimed_entity),
        )

        return ClaimContext(
            trigger_text=trigger_text,
            heading=heading,
            nearby_text=nearby_text,
            links=tuple(links),
            images=tuple(images),
        )

    def _find_heading(
        self,
        trigger_node: Tag,
        container: Tag,
    ) -> str | None:
        heading = container.find(
            [
                "h1",
                "h2",
                "h3",
                "h4",
                "h5",
                "h6",
            ]
        )

        if heading is not None:
            value = self._normalize_text(
                heading.get_text(
                    " ",
                    strip=True,
                )
            )

            if value:
                return value

        previous = trigger_node.find_previous(
            [
                "h1",
                "h2",
                "h3",
                "h4",
                "h5",
                "h6",
            ]
        )

        if previous is None:
            return None

        value = self._normalize_text(
            previous.get_text(
                " ",
                strip=True,
            )
        )

        return value or None

    def _extract_links(
        self,
        *,
        trigger_node: Tag,
        container: Tag,
        source_url: str,
        claimed_entity: str | None,
    ) -> list[ClaimContextLink]:
        source_domain = self._domain(source_url)

        result: list[ClaimContextLink] = []

        for link in container.find_all(
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
                source_url,
                href,
            )

            target_domain = self._domain(absolute_url)

            if target_domain is None:
                continue

            text = self._normalize_text(
                link.get_text(
                    " ",
                    strip=True,
                )
            )

            distance = self._dom_distance(
                trigger_node,
                link,
            )

            relevance = self._link_relevance(
                link_text=text,
                url=absolute_url,
                claimed_entity=(claimed_entity),
            )

            result.append(
                ClaimContextLink(
                    text=text,
                    url=absolute_url,
                    external=(source_domain != target_domain),
                    distance=distance,
                    relevance=relevance,
                )
            )

        result = self._deduplicate_links(result)

        result.sort(
            key=lambda item: (
                -item.relevance,
                not item.external,
                item.distance,
            )
        )

        return result[:12]

    def _extract_images(
        self,
        *,
        trigger_node: Tag,
        container: Tag,
        source_url: str,
        claimed_entity: str | None,
    ) -> list[ClaimContextImage]:
        result: list[ClaimContextImage] = []

        for image in container.find_all("img"):
            raw_src = image.get("src")

            raw_alt = image.get("alt")

            src = (
                urljoin(
                    source_url,
                    raw_src.strip(),
                )
                if isinstance(
                    raw_src,
                    str,
                )
                and raw_src.strip()
                else None
            )

            alt = (
                self._normalize_text(raw_alt)
                if isinstance(
                    raw_alt,
                    str,
                )
                else None
            )

            if not alt and not src:
                continue

            distance = self._dom_distance(
                trigger_node,
                image,
            )

            relevance = self._image_relevance(
                alt=alt,
                src=src,
                claimed_entity=(claimed_entity),
            )

            result.append(
                ClaimContextImage(
                    alt=alt or None,
                    src=src,
                    distance=distance,
                    relevance=relevance,
                )
            )

        result.sort(
            key=lambda item: (
                -item.relevance,
                item.distance,
            )
        )

        return result[:12]

    def _link_relevance(
        self,
        *,
        link_text: str,
        url: str,
        claimed_entity: str | None,
    ) -> int:
        tokens = self._entity_tokens(claimed_entity)

        if not tokens:
            return 0

        parsed = urlsplit(url)

        hostname = parsed.hostname or ""

        haystack = " ".join(
            [
                link_text,
                hostname,
                parsed.path,
            ]
        ).casefold()

        score = 0

        for token in tokens:
            if token in haystack:
                score += 5

        return score

    def _image_relevance(
        self,
        *,
        alt: str | None,
        src: str | None,
        claimed_entity: str | None,
    ) -> int:
        tokens = self._entity_tokens(claimed_entity)

        if not tokens:
            return 0

        haystack = (f"{alt or ''} {src or ''}").casefold()

        score = 0

        for token in tokens:
            if token in haystack:
                score += 5

        return score

    @staticmethod
    def _entity_tokens(
        value: str | None,
    ) -> set[str]:
        if not value:
            return set()

        ignored = {
            "system",
            "systems",
            "group",
            "polska",
            "poland",
            "firma",
        }

        result = {
            token
            for token in re.findall(
                r"[0-9a-ząćęłńóśźż]+",
                value.casefold(),
            )
            if (len(token) >= 3 and token not in ignored)
        }

        return result

    @staticmethod
    def _ancestor_chain(
        node: Tag,
    ) -> list[Tag]:
        result: list[Tag] = []

        current: Tag | None = node

        while current is not None:
            result.append(current)

            parent = current.parent

            if not isinstance(
                parent,
                Tag,
            ):
                break

            current = parent

        return result

    def _dom_distance(
        self,
        first: Tag,
        second: Tag,
    ) -> int:
        if first is second:
            return 0

        first_chain = self._ancestor_chain(first)

        second_chain = self._ancestor_chain(second)

        first_positions = {id(node): index for index, node in enumerate(first_chain)}

        best: int | None = None

        for (
            second_index,
            node,
        ) in enumerate(second_chain):
            first_index = first_positions.get(id(node))

            if first_index is None:
                continue

            distance = first_index + second_index

            if best is None or distance < best:
                best = distance

        return best if best is not None else 999

    @staticmethod
    def _domain(
        url: str,
    ) -> str | None:
        hostname = urlsplit(url).hostname

        if hostname is None:
            return None

        hostname = hostname.casefold().rstrip(".")

        if hostname.startswith("www."):
            hostname = hostname[4:]

        return hostname

    @staticmethod
    def _normalize_text(
        value: str,
    ) -> str:
        return re.sub(
            r"\s+",
            " ",
            value,
        ).strip()

    @staticmethod
    def _deduplicate_links(
        links: list[ClaimContextLink],
    ) -> list[ClaimContextLink]:
        by_url: dict[
            str,
            ClaimContextLink,
        ] = {}

        for link in links:
            existing = by_url.get(link.url)

            if existing is None:
                by_url[link.url] = link
                continue

            if link.relevance > existing.relevance:
                by_url[link.url] = link
                continue

            if link.relevance == existing.relevance and link.distance < existing.distance:
                by_url[link.url] = link

        return list(by_url.values())

    @staticmethod
    def _context_sort_key(
        context: ClaimContext,
    ) -> tuple[
        int,
        int,
        int,
        int,
    ]:
        max_link_relevance = max(
            (link.relevance for link in context.links if link.external),
            default=0,
        )

        max_image_relevance = max(
            (image.relevance for image in context.images),
            default=0,
        )

        #
        # Najważniejsze:
        #
        # 1. kontekst zawierający
        #    relevant external link
        #
        # 2. potem relevant image
        #
        # 3. potem mniejszy tekst
        #
        # Dzięki temu dla BTR większa
        # sekcja z btr.pl wygra z małym
        # divem zawierającym tylko tekst.
        #
        return (
            -max_link_relevance,
            -max_image_relevance,
            len(context.nearby_text),
            len(context.links),
        )
