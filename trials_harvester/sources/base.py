"""Base classes for registry fetchers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, Iterator, Optional


@dataclass
class FetchConfig:
    """Common configuration options shared by all fetchers."""

    query: Optional[str] = None
    since: Optional[str] = None
    until: Optional[str] = None
    countries: Optional[Iterable[str]] = None
    sponsors: Optional[Iterable[str]] = None
    phases: Optional[Iterable[str]] = None
    statuses: Optional[Iterable[str]] = None
    batch_size: int = 100
    max_records: Optional[int] = None


class BaseFetcher:
    """Abstract fetcher returning raw registry records."""

    source: str = ""

    def __init__(self, config: FetchConfig) -> None:
        self.config = config

    # pragma: no cover - to be implemented by subclasses
    def fetch(self) -> Iterator[Dict[str, object]]:  # type: ignore[override]
        raise NotImplementedError

    @staticmethod
    def parse_date(value: str | None) -> datetime | None:
        """Parse an ISO-like date string into :class:`datetime`."""

        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None


__all__ = ["BaseFetcher", "FetchConfig"]
