"""Implementation of the :code:`dedupe` CLI command."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import pandas as pd
from difflib import SequenceMatcher

from ..io import read_table, write_dataframe


def _fuzzy_score(left: str, right: str) -> int:
    if not left and not right:
        return 100
    return int(SequenceMatcher(None, left, right).ratio() * 100)


def _fuzzy_collapse(df: pd.DataFrame, threshold: int) -> pd.DataFrame:
    if "public_title" not in df.columns:
        return df

    dropped: set[int] = set()
    kept: list[tuple[int, pd.Series]] = []

    for idx, row in df.iterrows():
        if idx in dropped:
            continue
        title = row.get("public_title") or ""
        sponsor = row.get("sponsor_primary") or ""
        start_date = row.get("start_date") or ""
        start_year = start_date[:4]

        matched = False
        for keep_idx, keep_row in kept:
            if sponsor and sponsor == keep_row.get("sponsor_primary"):
                other_title = keep_row.get("public_title") or ""
                other_year = (keep_row.get("start_date") or "")[:4]
                score = _fuzzy_score(title, other_title)
                if score >= threshold and (not start_year or start_year == other_year):
                    dropped.add(idx)
                    matched = True
                    break
        if not matched:
            kept.append((idx, row))

    if not dropped:
        return df
    return df.drop(index=list(dropped))


def run(args: Sequence[str] | object) -> None:
    input_path: Path = args.input_path
    output_path: Path = args.out
    columns = [col.strip() for col in getattr(args, "by").split(",") if col.strip()]
    if not columns:
        raise ValueError("--by must contain at least one column")

    df = read_table(input_path)
    initial = len(df)
    df = df.drop_duplicates(subset=columns, keep="first")

    if getattr(args, "fuzzy_title"):
        df = _fuzzy_collapse(df, threshold=int(getattr(args, "fuzzy_threshold")))

    write_dataframe(df, output_path)
    print(f"Deduplicated {initial} -> {len(df)} records written to {output_path}")


__all__ = ["run"]
