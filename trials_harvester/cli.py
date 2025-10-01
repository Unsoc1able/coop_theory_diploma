"""Command line interface for :mod:`trials_harvester`."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from . import __version__
from .commands.dedupe import run as run_dedupe
from .commands.fetch import run as run_fetch
from .commands.normalize import run as run_normalize


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trials_harvester",
        description=(
            "Utilities for downloading, normalising and deduplicating clinical "
            "trial registries."
        ),
    )
    parser.add_argument(
        "--version", action="version", version=f"trials_harvester {__version__}"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch_parser = subparsers.add_parser(
        "fetch",
        help="Download raw data from a registry and persist it as JSON Lines.",
    )
    fetch_parser.add_argument(
        "--source",
        required=True,
        help="Registry identifier (e.g. clinicaltrials).",
    )
    fetch_parser.add_argument(
        "--query",
        help="Free-form query expression understood by the registry.",
    )
    fetch_parser.add_argument(
        "--since",
        help="Optional lower bound for the last update date (YYYY-MM-DD).",
    )
    fetch_parser.add_argument(
        "--until",
        help="Optional upper bound for the last update date (YYYY-MM-DD).",
    )
    fetch_parser.add_argument(
        "--country",
        action="append",
        help="Country filter (repeatable).",
    )
    fetch_parser.add_argument(
        "--sponsor",
        action="append",
        help="Sponsor filter (repeatable).",
    )
    fetch_parser.add_argument(
        "--phase",
        help="Phase filter expressed as comma separated values (e.g. I,II,III).",
    )
    fetch_parser.add_argument(
        "--status",
        help="Recruitment status filter expressed as comma separated values.",
    )
    fetch_parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of records to request per API call (if supported).",
    )
    fetch_parser.add_argument(
        "--max-records",
        type=int,
        help="Maximum number of records to retrieve.",
    )
    fetch_parser.add_argument(
        "--out",
        required=True,
        type=Path,
        help="Destination file for the raw JSON Lines payload.",
    )

    normalize_parser = subparsers.add_parser(
        "normalize",
        help="Convert raw payloads into the unified Trial schema.",
    )
    normalize_parser.add_argument(
        "--in",
        dest="inputs",
        nargs="+",
        required=True,
        help="Input files containing raw payloads (JSON or JSONL).",
    )
    normalize_parser.add_argument(
        "--out",
        required=True,
        type=Path,
        help="Destination file for the normalised dataset (CSV or Parquet).",
    )

    dedupe_parser = subparsers.add_parser(
        "dedupe",
        help="Deduplicate normalised tables using strict and fuzzy strategies.",
    )
    dedupe_parser.add_argument(
        "--in",
        dest="input_path",
        required=True,
        type=Path,
        help="Input CSV/Parquet file produced by the normaliser.",
    )
    dedupe_parser.add_argument(
        "--by",
        required=True,
        help="Comma separated list of columns used for strict deduplication.",
    )
    dedupe_parser.add_argument(
        "--out",
        required=True,
        type=Path,
        help="Destination path for the deduplicated dataset.",
    )
    dedupe_parser.add_argument(
        "--fuzzy-title",
        action="store_true",
        help=(
            "Enable fuzzy matching on public titles to collapse additional "
            "duplicates."
        ),
    )
    dedupe_parser.add_argument(
        "--fuzzy-threshold",
        type=int,
        default=92,
        help="Similarity threshold (0-100) for fuzzy title matching.",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "fetch":
        run_fetch(args)
    elif args.command == "normalize":
        run_normalize(args)
    elif args.command == "dedupe":
        run_dedupe(args)
    else:  # pragma: no cover - safeguard
        parser.error(f"Unknown command: {args.command}")
    return 0


__all__ = ["build_parser", "main"]
