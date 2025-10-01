"""Integration-style checks for ClinicalTrials.gov parsers."""

from __future__ import annotations

from typing import Dict, Iterable, Iterator, List, Sequence

import pytest

from data.parsers.clinical_trials import (
    ClinicalTrialsBySponsorParser,
    ClinicalTrialsExpressionParser,
)
from data.parsers.clinical_trials_api import StudyFieldsResponse


class _FakeClinicalTrialsClient:
    def __init__(self, responses_by_expr: Dict[str, Sequence[StudyFieldsResponse]]) -> None:
        self._responses = {expr: list(chunks) for expr, chunks in responses_by_expr.items()}
        self.calls: List[Dict[str, object]] = []

    def fetch_study_fields(
        self,
        *,
        expr: str,
        fields: Iterable[str],
        batch_size: int,
        max_rank: int | None = None,
        **kwargs: object,
    ) -> Iterator[StudyFieldsResponse]:
        self.calls.append(
            {
                "expr": expr,
                "fields": tuple(fields),
                "batch_size": batch_size,
                "max_rank": max_rank,
            }
        )
        yield from self._responses.get(expr, [])


@pytest.fixture()
def fake_study_chunks() -> Dict[str, List[StudyFieldsResponse]]:
    def make_study(
        *,
        phase: str,
        status: str,
        sponsor: str,
        name_suffix: str,
    ) -> Dict[str, List[str]]:
        return {
            "NCTId": [f"NCT-{sponsor}-{name_suffix}"],
            "LeadSponsorName": [sponsor],
            "Phase": [phase],
            "OverallStatus": [status],
        }

    return {
        'AREA[LeadSponsorName]"Pfizer"': [
            StudyFieldsResponse(
                studies=[
                    make_study(phase="Phase 3", status="Recruiting", sponsor="Pfizer", name_suffix="01"),
                    make_study(phase="Phase 2", status="Completed", sponsor="Pfizer", name_suffix="02"),
                ],
                total_studies=2,
                next_rank=None,
            )
        ],
        'AREA[LeadSponsorName]"BIOCAD"': [
            StudyFieldsResponse(
                studies=[
                    make_study(phase="Phase 1", status="Recruiting", sponsor="BIOCAD", name_suffix="11"),
                ],
                total_studies=1,
                next_rank=None,
            )
        ],
        "oncology AND Recruiting": [
            StudyFieldsResponse(
                studies=[
                    make_study(phase="Phase 2", status="Recruiting", sponsor="ACME", name_suffix="100"),
                    make_study(phase="Phase 2", status="Recruiting", sponsor="ACME", name_suffix="101"),
                ],
                total_studies=2,
                next_rank=None,
            )
        ],
    }


def test_clinical_trials_by_sponsor_parser_aggregates_trials(fake_study_chunks: Dict[str, List[StudyFieldsResponse]]) -> None:
    client = _FakeClinicalTrialsClient(fake_study_chunks)
    parser = ClinicalTrialsBySponsorParser(sponsors=["Pfizer", "BIOCAD"], client=client, max_studies=10, batch_size=5)

    result = parser.parse()
    records = result.payload["records"]

    assert len(records) == 2

    pfizer, biocad = records
    assert pfizer["name"] == "Pfizer"
    assert pfizer["expr"] == 'AREA[LeadSponsorName]"Pfizer"'
    assert pfizer["total_trials"] == 2
    assert pfizer["phase_counts"] == {"Phase 3": 1, "Phase 2": 1}
    assert pfizer["status_counts"] == {"Recruiting": 1, "Completed": 1}

    assert biocad["name"] == "BIOCAD"
    assert biocad["total_trials"] == 1
    assert biocad["phase_counts"] == {"Phase 1": 1}
    assert biocad["status_counts"] == {"Recruiting": 1}

    assert len(client.calls) == 2
    assert client.calls[0]["max_rank"] == 10


def test_clinical_trials_expression_parser_uses_provided_expression(
    fake_study_chunks: Dict[str, List[StudyFieldsResponse]]
) -> None:
    client = _FakeClinicalTrialsClient(fake_study_chunks)
    parser = ClinicalTrialsExpressionParser(
        expr="oncology AND Recruiting",
        client=client,
        max_studies=5,
        batch_size=2,
    )

    result = parser.parse()
    records = result.payload["records"]

    assert len(records) == 1
    record = records[0]
    assert record["expr"] == "oncology AND Recruiting"
    assert record["total_trials"] == 2
    assert record["phase_counts"] == {"Phase 2": 2}
    assert record["status_counts"] == {"Recruiting": 2}

    assert len(client.calls) == 1
    assert client.calls[0]["expr"] == "oncology AND Recruiting"
