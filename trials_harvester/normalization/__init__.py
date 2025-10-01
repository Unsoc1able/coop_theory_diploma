"""Normalization registry dispatching per-source logic."""

from __future__ import annotations

from typing import Callable, Dict

from .clinicaltrials_gov import normalize_study as normalize_ctg
from .models import Trial

_NORMALIZERS: Dict[str, Callable[[dict], Trial]] = {
    "clinicaltrials_gov": normalize_ctg,
}


def normalize_record(source: str, record: dict) -> Trial:
    key = source.lower().strip()
    if key not in _NORMALIZERS:
        raise ValueError(f"Unsupported source for normalisation: {source}")
    return _NORMALIZERS[key](record)


__all__ = ["normalize_record", "Trial"]
