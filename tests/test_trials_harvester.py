from __future__ import annotations

import json
from pathlib import Path


from trials_harvester.normalization.clinicaltrials_gov import normalize_study
from trials_harvester.normalization.utils import normalize_countries, normalize_phase
from trials_harvester.sources.base import FetchConfig
from trials_harvester.sources.clinicaltrials_gov import ClinicalTrialsGovFetcher


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


def load_fixture(name: str) -> dict:
    with (FIXTURE_DIR / name).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def test_normalize_clinicaltrials_study() -> None:
    study = load_fixture("ctg_study.json")
    trial = normalize_study(study)

    assert trial.source == "clinicaltrials_gov"
    assert trial.source_id == "NCT01234567"
    assert trial.public_title == "Example oncology study"
    assert trial.scientific_title == "Phase 2 Study of Example Drug"
    assert trial.sponsor_primary == "BioPharma"
    assert trial.sponsors_all == ["BioPharma", "CoLab One"]
    assert trial.phase == "II"
    assert trial.overall_status == "recruiting"
    assert trial.study_type == "interventional"
    assert trial.enrollment == 120
    assert trial.centers_count == 2
    assert trial.countries == ["US", "CA"]
    assert trial.conditions == ["Oncology Condition"]
    assert trial.interventions == ["Drug A", "Drug B"]
    assert trial.start_date == "2023-01-01"
    assert trial.primary_completion_date == "2024-03-01"
    assert trial.completion_date == "2024-06-01"
    assert trial.nct_id == "NCT01234567"
    assert trial.eudract_number == "EUCTR2019-012345-67"
    assert trial.isrctn == "ISRCTN12345678"
    assert trial.protocol_id == "ABC-123"
    assert trial.last_updated_date == "2024-02-01"
    assert trial.language == "en"
    assert isinstance(trial.raw_payload, dict)


def test_normalize_phase_variants() -> None:
    assert normalize_phase(["Phase 1/Phase 2"]) == "I/II"
    assert normalize_phase(["Phase 2", "Phase 3"]) == "II/III"
    assert normalize_phase(["Not Applicable"]) == "NA"


def test_normalize_countries_handles_iso_codes() -> None:
    assert normalize_countries(["United States", "ca", "Unknown"])[:2] == ["US", "CA"]


def test_clinicaltrials_fetcher_paginates(monkeypatch) -> None:
    config = FetchConfig(query="oncology", batch_size=2, max_records=3)
    fetcher = ClinicalTrialsGovFetcher(config)

    responses = [
        {
            "FullStudiesResponse": {
                "FullStudies": [
                    {"Study": load_fixture("ctg_study.json")},
                ]
            }
        },
        {"FullStudiesResponse": {"FullStudies": []}},
    ]
    call_index = {"value": 0}

    def fake_request(self, params):  # pragma: no cover - monkeypatched
        idx = call_index["value"]
        call_index["value"] += 1
        return responses[min(idx, len(responses) - 1)]

    monkeypatch.setattr(ClinicalTrialsGovFetcher, "_perform_request", fake_request, raising=False)
    monkeypatch.setattr("trials_harvester.sources.clinicaltrials_gov.time.sleep", lambda _: None)

    results = list(fetcher.fetch())
    assert len(results) == 1
    assert results[0]["StudyType"] == "Interventional"


