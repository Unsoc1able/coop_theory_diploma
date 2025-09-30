"""Base utilities for future data parsers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable


@dataclass
class ParserResult:
    """Normalized representation of parsed data."""

    source: str
    payload: Dict[str, Any]


class BaseParser:
    """Skeleton parser providing a simple interface for extensions."""

    source: str = ""

    def fetch(self) -> Iterable[Dict[str, Any]]:
        """Fetch raw data. Subclasses should override."""
        raise NotImplementedError

    def parse(self) -> ParserResult:
        """Parse and normalize raw data."""
        records = list(self.fetch())
        return ParserResult(source=self.source, payload={"records": records})
