"""Implementation of the :code:`normalize` CLI command."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import pandas as pd

from ..io import iter_raw_payloads, write_dataframe
from ..normalization import Trial, normalize_record


def run(args: Sequence[str] | object) -> None:
    output: Path = args.out
    inputs = getattr(args, "inputs")
    records: list[dict] = []
    errors = 0

    for payload in iter_raw_payloads(inputs):
        source = payload.get("source") if isinstance(payload, dict) else None
        record = payload.get("record") if isinstance(payload, dict) else None
        if isinstance(record, dict) and isinstance(source, str):
            raw = record
            raw_source = source
        elif isinstance(payload, dict):
            raw = payload
            raw_source = source or payload.get("source")
        else:
            continue

        if not isinstance(raw_source, str):
            raise ValueError("Input payload is missing the 'source' key")

        try:
            trial: Trial = normalize_record(raw_source, raw)
        except ValueError as exc:
            errors += 1
            print(f"Skipping record due to error: {exc}")
            continue
        records.append(trial.to_dict())

    df = pd.DataFrame(records)
    write_dataframe(df, output)

    print(
        f"Normalised {len(records)} records from {len(inputs)} files -> {output}"
    )
    if errors:
        print(f"Encountered {errors} records with validation errors")


__all__ = ["run"]
