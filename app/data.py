"""Datasets, presets and helpers used by the dashboard."""

from __future__ import annotations

import json

import os
from pathlib import Path
from typing import Any, Iterable, List, Mapping, Sequence

DATASET_ENV_VAR = "CLINICAL_TRIALS_DATASET_PATH"
DEFAULT_DATASET_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "clinical_trials_by_sponsor.json"
)
DATASET_PATH = DEFAULT_DATASET_PATH


MIN_TOTAL_PROJECTS = 20


SYNTHETIC_COMPANIES: List[dict] = [
    {"name": "Pfizer", "n_I": 45, "n_II": 28, "n_III": 37},
    {"name": "BIOCAD", "n_I": 15, "n_II": 9, "n_III": 18},
    {"name": "Generium", "n_I": 7, "n_II": 6, "n_III": 9},
    {"name": "R-Pharm", "n_I": 11, "n_II": 8, "n_III": 12},
    {"name": "Pharmstandard", "n_I": 9, "n_II": 7, "n_III": 10},
    {"name": "Geropharm", "n_I": 5, "n_II": 4, "n_III": 6},
    {"name": "Petrovax", "n_I": 6, "n_II": 5, "n_III": 7},
    {"name": "Valenta", "n_I": 5, "n_II": 4, "n_III": 6},
    {"name": "Nanolek", "n_I": 6, "n_II": 5, "n_III": 6},
    {"name": "ChemRar", "n_I": 7, "n_II": 6, "n_III": 5},
]
# Исходные синтетические данные, использовавшиеся на раннем этапе разработки.

# Порог отсечения портфелей с малым числом проектов по всем фазам.


INITIAL_PARAMETERS = {
    "p1": 0.47,
    "p2": 0.28,
    "p3": 0.55,
    "C_I": 25,
    "C_II": 60,
    "C_III": 350,
    "C_REG": 3,
    "coop_c3_reduction": 20,
    "coop_dp3": 0.05,
    "coop_p3_cap": 0.70,
}

PARAMETER_PRESETS = {
    "avg": INITIAL_PARAMETERS.copy(),
    "ru": {
        "p1": 0.47,
        "p2": 0.30,
        "p3": 0.58,
        "C_I": 20,
        "C_II": 50,
        "C_III": 230,
        "C_REG": 2,
        "coop_c3_reduction": 30,
        "coop_dp3": 0.06,
        "coop_p3_cap": 0.80,
    },
}


def _safe_int(value: Any) -> int:
    """Best-effort conversion of heterogeneous count values to ``int``."""

    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            try:
                return int(float(value))
            except ValueError:
                return 0
    return 0


def _phase_counts(record: Mapping[str, Any]) -> Mapping[str, Any]:
    counts = record.get("phase_counts", {})
    if isinstance(counts, Mapping):
        return counts
    return {}


def _normalise_timeline(raw: Mapping[str, Any] | None) -> Mapping[int, Mapping[str, int]]:
    """Return a cleaned timeline keyed by integer year."""

    if not isinstance(raw, Mapping):
        return {}

    timeline: dict[int, dict[str, int]] = {}
    for year, payload in raw.items():
        try:
            year_int = int(year)
        except (TypeError, ValueError):
            continue

        if not isinstance(payload, Mapping):
            continue

        timeline[year_int] = {
            "started": _safe_int(payload.get("started", 0)),
            "completed": _safe_int(payload.get("completed", 0)),
        }

    return timeline


def _company_from_record(record: Mapping[str, Any]) -> dict:
    counts = _phase_counts(record)
    return {
        "name": str(record.get("name", "")),
        "n_I": _safe_int(counts.get("Phase 1", 0)),
        "n_II": _safe_int(counts.get("Phase 2", 0)),
        "n_III": _safe_int(counts.get("Phase 3", 0)),
    }


def _normalise_company(record: Mapping[str, Any]) -> dict:
    data = {
        "name": str(record.get("name", "")),
        "n_I": _safe_int(record.get("n_I", 0)),
        "n_II": _safe_int(record.get("n_II", 0)),
        "n_III": _safe_int(record.get("n_III", 0)),
        "phase_counts": dict(_phase_counts(record)),
    }
    if isinstance(record.get("condition_counts"), Mapping):
        data["condition_counts"] = dict(record.get("condition_counts", {}))
    if isinstance(record.get("status_counts"), Mapping):
        data["status_counts"] = dict(record.get("status_counts", {}))
    if "successes" in record:
        data["successes"] = _safe_int(record.get("successes", 0))
    if "total_trials" in record:
        data["total_trials"] = _safe_int(record.get("total_trials", 0))
    timeline = _normalise_timeline(record.get("status_timeline"))
    if timeline:
        data["status_timeline"] = timeline
    if not data["name"]:
        raise ValueError("Company records must contain a non-empty name")
    return data


def _iter_company_records(dataset: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    companies = dataset.get("companies")
    if isinstance(companies, Sequence):
        for record in companies:
            if isinstance(record, Mapping):
                yield record
        return

    sponsors = dataset.get("sponsors")
    if isinstance(sponsors, Sequence):
        for record in sponsors:
            if isinstance(record, Mapping):
                yield _company_from_record(record)



def _resolve_dataset_path(dataset_path: Path | None = None) -> Path:
    if dataset_path is not None:
        return Path(dataset_path)

    env_value = os.getenv(DATASET_ENV_VAR)
    if env_value:
        return Path(env_value).expanduser()

    return DEFAULT_DATASET_PATH

def _filter_small_portfolios(companies: List[dict]) -> List[dict]:
    """Remove companies with too few projects across all phases."""

    return [
        company
        for company in companies
        if company["n_I"] + company["n_II"] + company["n_III"] >= MIN_TOTAL_PROJECTS
    ]


def load_companies(dataset_path: Path | None = None) -> List[dict]:
    """Load the latest clinical trials dataset for the dashboard.

    The helper looks for ``clinical_trials_by_sponsor.json`` generated by
    ``data_fetch/build_clinical_trials_dataset.py``. If the file is missing or
    contains invalid data we fall back to the bundled synthetic numbers so that
    the app remains usable offline.
    """


    path = _resolve_dataset_path(dataset_path)

    if path.is_file():
        try:
            dataset = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return SYNTHETIC_COMPANIES

        if isinstance(dataset, Mapping):
            companies: List[dict] = []
            for record in _iter_company_records(dataset):
                try:
                    companies.append(_normalise_company(record))
                except ValueError:
                    continue
            filtered = _filter_small_portfolios(companies)
            if filtered:
                return filtered
            if companies:
                return companies

    return SYNTHETIC_COMPANIES


__all__ = [
    "DATASET_ENV_VAR",
    "DEFAULT_DATASET_PATH",
    "DATASET_PATH",
    "MIN_TOTAL_PROJECTS",
    "SYNTHETIC_COMPANIES",
    "INITIAL_PARAMETERS",
    "PARAMETER_PRESETS",
    "load_companies",
]
