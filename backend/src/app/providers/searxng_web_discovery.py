import httpx

from app.providers.web_discovery import (
    WebDiscoveryResult,
)


class SearxngWebDiscoveryProvider:
    def __init__(
        self,
        *,
        base_url: str = "http://searxng:8080",
        timeout: float = 20.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def search(
        self,
        query: str,
        *,
        language: str = "pl",
        limit: int = 10,
    ) -> tuple[WebDiscoveryResult, ...]:
        response = httpx.get(
            f"{self._base_url}/search",
            params={
                "q": query,
                "format": "json",
                "language": language,
                "safesearch": 1,
            },
            timeout=self._timeout,
        )

        response.raise_for_status()

        payload = response.json()

        results: list[WebDiscoveryResult] = []

        for item in payload.get(
            "results",
            [],
        ):
            url = item.get("url")

            if not url:
                continue

            results.append(
                WebDiscoveryResult(
                    title=item.get("title"),
                    url=url,
                    content=item.get("content"),
                    engine=item.get("engine"),
                    score=item.get("score"),
                )
            )

            if len(results) >= limit:
                break

        return tuple(results)
