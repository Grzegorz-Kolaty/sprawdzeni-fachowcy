from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class WebDiscoveryResult:
    title: str | None
    url: str
    content: str | None
    engine: str | None
    score: float | None


class WebDiscoveryProvider(Protocol):
    def search(
        self,
        query: str,
        *,
        language: str = "pl",
        limit: int = 10,
    ) -> tuple[WebDiscoveryResult, ...]: ...
