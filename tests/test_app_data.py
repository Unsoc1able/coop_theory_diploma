from __future__ import annotations

import json
from pathlib import Path

from app.data import (
    DATASET_ENV_VAR,
    SYNTHETIC_COMPANIES,
    load_companies,
)


def test_load_companies_returns_synthetic_when_missing(tmp_path: Path) -> None:
    dataset_path = tmp_path / "clinical_trials_by_sponsor.json"
    result = load_companies(dataset_path)
    assert result == SYNTHETIC_COMPANIES


def test_load_companies_reads_companies_block(tmp_path: Path) -> None:
    dataset_path = tmp_path / "clinical_trials_by_sponsor.json"
    payload = {
        "companies": [
            {"name": "Test", "n_I": "10", "n_II": 5.0, "n_III": "7"},
        ]
    }
    dataset_path.write_text(json.dumps(payload), encoding="utf-8")

    result = load_companies(dataset_path)

    assert result == [{"name": "Test", "n_I": 10, "n_II": 5, "n_III": 7}]


def test_load_companies_aggregates_from_sponsors(tmp_path: Path) -> None:
    dataset_path = tmp_path / "clinical_trials_by_sponsor.json"
    payload = {
        "sponsors": [
            {
                "name": "Example Pharma",
                "phase_counts": {
                    "Phase 1": 3,
                    "Phase 2": "4",
                    "Phase 3": "5",
                },
            }
        ]
    }
    dataset_path.write_text(json.dumps(payload), encoding="utf-8")

    result = load_companies(dataset_path)

    assert result == [{"name": "Example Pharma", "n_I": 3, "n_II": 4, "n_III": 5}]


def test_load_companies_uses_environment_override(tmp_path: Path, monkeypatch) -> None:
    dataset_path = tmp_path / "clinical_trials_by_sponsor.json"
    payload = {"companies": [{"name": "Env Corp", "n_I": 1, "n_II": 2, "n_III": 3}]}
    dataset_path.write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setenv(DATASET_ENV_VAR, str(dataset_path))

    result = load_companies()

    assert result == [{"name": "Env Corp", "n_I": 1, "n_II": 2, "n_III": 3}]
