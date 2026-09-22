from dataclasses import dataclass

from app.providers.website_page_inspector import (
    UnsafeWebsitePageUrlError,
    WebsitePageInspectionError,
    WebsitePageInspector,
)


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
    def __init__(
        self,
        *,
        timeout: float = 12.0,
    ) -> None:
        self._page_inspector = WebsitePageInspector(
            timeout=timeout,
            user_agent="SprawdzeniFachowcy/0.1 (evidence inspection)",
        )

    def inspect(
        self,
        url: str,
    ) -> EvidenceCandidateInspection:
        try:
            page = self._page_inspector.inspect(url)

        except UnsafeWebsitePageUrlError as exc:
            raise UnsafeEvidenceCandidateUrlError(str(exc)) from exc

        except WebsitePageInspectionError as exc:
            raise EvidenceCandidateInspectionError(str(exc)) from exc

        return EvidenceCandidateInspection(
            requested_url=page.requested_url,
            final_url=page.final_url,
            title=page.title,
            description=page.description,
            visible_text=page.visible_text,
            links=tuple(
                EvidenceCandidateLink(
                    text=link.text,
                    url=link.url,
                )
                for link in page.links
            ),
        )
