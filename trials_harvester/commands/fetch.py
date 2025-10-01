"""Implementation of the :code:`fetch` CLI command."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

try:
    from tqdm import tqdm
except ImportError:  # pragma: no cover - optional dependency
    def tqdm(iterable, **kwargs):
        return iterable

from ..sources import create_fetcher


def _split_csv(value: str | None) -> list[str] | None:
    if value is None:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def run(args: Sequence[str] | object) -> None:
    """Execute the fetch command using the parsed ``argparse`` namespace."""

    output: Path = args.out
    output.parent.mkdir(parents=True, exist_ok=True)

    phase_filters = _split_csv(getattr(args, "phase", None))
    status_filters = _split_csv(getattr(args, "status", None))

    fetcher = create_fetcher(
        source=getattr(args, "source"),
        query=getattr(args, "query", None),
        since=getattr(args, "since", None),
        until=getattr(args, "until", None),
        countries=getattr(args, "country", None),
        sponsors=getattr(args, "sponsor", None),
        phases=phase_filters,
        statuses=status_filters,
        batch_size=getattr(args, "batch_size", 100),
        max_records=getattr(args, "max_records", None),
    )

    count = 0
    with output.open("w", encoding="utf-8") as fh:
        for record in tqdm(fetcher.fetch(), desc=f"Fetching {fetcher.source}"):
            payload = {
                "source": fetcher.source,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "record": record,
            }
            fh.write(json.dumps(payload, ensure_ascii=False))
            fh.write("\n")
            count += 1

    print(f"Fetched {count} records from {fetcher.source} -> {output}")


__all__ = ["run"]
