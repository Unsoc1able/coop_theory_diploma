"""Tests for the ClinicalTrials.gov Data API client."""

from __future__ import annotations

import json
from typing import Dict, List, Sequence

import pytest

from data.parsers.clinical_trials_api import ClinicalTrialsAPIError, ClinicalTrialsClient


class _DummyResponse:
    def __init__(self, payload: Dict[str, object], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self) -> Dict[str, object]:
        return self._payload


class _DummySession:
    def __init__(self, responses: Sequence[_DummyResponse]) -> None:
        self._responses = list(responses)
        self.calls: List[Dict[str, object]] = []

    def get(self, url: str, *, params: Dict[str, object], timeout: int) -> _DummyResponse:
        if not self._responses:
            raise AssertionError("Unexpected request: no responses queued")
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        return self._responses.pop(0)


def test_fetch_study_fields_streams_pages() -> None:
    session = _DummySession(
        responses=[
            _DummyResponse(
                {
                    "studies": [
                        {"fields": {"NCTId": ["NCT0001"], "Phase": "Phase 1"}},
                        {"fields": {"NCTId": ["NCT0002"], "Phase": ["Phase 2"]}},
                    ],
                    "totalCount": 3,
                    "nextPageToken": "3",
                }
            ),
            _DummyResponse(
                {
                    "studies": [
                        {"fields": {"NCTId": ["NCT0003"], "Phase": ["Phase 3"]}},
                    ],
                    "totalCount": 3,
                }
            ),
        ]
    )

    client = ClinicalTrialsClient(session=session, request_delay=0.0)

    results = list(
        client.fetch_study_fields(
            expr="HEART ATTACK",
            fields=["NCTId", "Phase"],
            batch_size=2,
        )
    )

    assert len(results) == 2
    first, second = results

    assert first.studies[0]["NCTId"] == ["NCT0001"]
    assert first.studies[1]["Phase"] == ["Phase 2"]
    assert first.total_studies == 3
    assert first.next_rank == 3
    assert first.next_page_token == "3"

    assert second.studies[0]["NCTId"] == ["NCT0003"]
    assert second.total_studies == 3
    assert second.next_rank is None

    assert session.calls[0]["url"].endswith("/study-fields")
    assert session.calls[0]["params"] == {
        "format": "json",
        "pageSize": 2,
        "query.term": "HEART ATTACK",
        "fields": "NCTId,Phase",
    }
    assert session.calls[1]["params"]["pageToken"] == "3"


def test_fetch_study_fields_honours_min_and_max_ranks() -> None:
    session = _DummySession(
        responses=[
            _DummyResponse(
                {
                    "studies": [
                        {"fields": {"NCTId": ["NCT1000"]}},
                        {"fields": {"NCTId": ["NCT1001"]}},
                        {"fields": {"NCTId": ["NCT1002"]}},
                    ],
                    "totalCount": 4,
                    "nextPageToken": "4",
                }
            ),
            _DummyResponse(
                {
                    "studies": [
                        {"fields": {"NCTId": ["NCT1003"]}},
                    ],
                    "totalCount": 4,
                }
            ),
        ]
    )

    client = ClinicalTrialsClient(session=session, request_delay=0.0)
    chunks = list(
        client.fetch_study_fields(
            expr="CANCER",
            fields=["NCTId"],
            min_rank=2,
            max_rank=3,
            batch_size=3,
        )
    )

    assert len(chunks) == 1
    chunk = chunks[0]
    assert [study["NCTId"][0] for study in chunk.studies] == ["NCT1001", "NCT1002"]
    assert chunk.next_rank == 4


def test_fetch_study_fields_raises_for_http_errors() -> None:
    session = _DummySession(
        responses=[
            _DummyResponse({"error": "not found"}, status_code=404),
        ]
    )

    client = ClinicalTrialsClient(session=session, request_delay=0.0)

    with pytest.raises(ClinicalTrialsAPIError):
        next(
            client.fetch_study_fields(
                expr="UNKNOWN",
                fields=["NCTId"],
            )
        )
