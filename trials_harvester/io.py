"""Utility helpers for reading and writing datasets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, Iterator

import pandas as pd


def iter_raw_payloads(paths: Iterable[str | Path]) -> Iterator[Dict[str, object]]:
    for path_like in paths:
        path = Path(path_like)
        if not path.exists():
            raise FileNotFoundError(path)
        suffix = path.suffix.lower()
        if suffix == ".jsonl":
            with path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    yield json.loads(line)
        elif suffix == ".json":
            with path.open("r", encoding="utf-8") as fh:
                payload = json.load(fh)
            if isinstance(payload, list):
                for item in payload:
                    if isinstance(item, dict):
                        yield item
            elif isinstance(payload, dict):
                if "records" in payload and isinstance(payload["records"], list):
                    for item in payload["records"]:
                        if isinstance(item, dict):
                            yield item
                else:
                    yield payload
            else:
                raise ValueError(f"Unsupported JSON structure in {path}")
        else:
            raise ValueError(f"Unsupported input format: {path}")


def write_dataframe(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        df.to_parquet(path, index=False)
    elif suffix == ".csv":
        df.to_csv(path, index=False)
    elif suffix == ".jsonl":
        with path.open("w", encoding="utf-8") as fh:
            for record in df.to_dict(orient="records"):
                fh.write(json.dumps(record, ensure_ascii=False))
                fh.write("\n")
    else:
        raise ValueError(f"Unsupported output format: {path}")


def read_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix == ".jsonl":
        return pd.read_json(path, lines=True)
    raise ValueError(f"Unsupported input format: {path}")


__all__ = ["iter_raw_payloads", "read_table", "write_dataframe"]
