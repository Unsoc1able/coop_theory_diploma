from __future__ import annotations

from pathlib import Path

from data_fetch.build_clinical_trials_dataset import (
    DEFAULT_OUTPUT,
    ROOT,
    resolve_output_path,
)


def test_default_output_is_within_repository_root() -> None:
    assert DEFAULT_OUTPUT == ROOT / "data" / "clinical_trials_by_sponsor.json"


def test_resolve_output_path_returns_absolute_for_relative() -> None:
    relative = Path("data/clinical_trials_by_sponsor.json")
    resolved = resolve_output_path(relative)

    assert resolved == (ROOT / relative).resolve()


def test_resolve_output_path_keeps_absolute(tmp_path: Path) -> None:
    absolute = tmp_path / "custom.json"

    assert resolve_output_path(absolute) == absolute
