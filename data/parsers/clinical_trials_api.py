"""Utilities for interacting with the ClinicalTrials.gov API.

This module exposes thin wrappers above the ClinicalTrials.gov Data API.
The helper targets the ``study-fields`` endpoint which provides structured
summaries for groups of studies.  The functions are intentionally lightweight so
that they can be reused from notebooks or from other scripts inside the
project.

The implementation respects the public rate limit (10 requests per second as of
May 2024).  Batching is performed automatically using the cursor-based
pagination provided by the Data API.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, Iterable, Iterator, List, Optional, Sequence

import requests

BASE_URL = "https://clinicaltrials.gov/data-api/api/study-fields"
# The public documentation suggests keeping requests below 10 per second.
REQUEST_DELAY = 0.12


class ClinicalTrialsAPIError(RuntimeError):
    """Raised when ClinicalTrials.gov returns an error response."""


@dataclass
class StudyFieldsResponse:
    """Container holding the normalised payload returned by the Data API."""

    studies: List[Dict[str, List[str]]]
    total_studies: int
    next_rank: Optional[int]
    next_page_token: Optional[str] = None


class ClinicalTrialsClient:
    """Client for the ClinicalTrials.gov ``study-fields`` Data API endpoint.

    Parameters
    ----------
    session:
        Optional :class:`requests.Session` that will be reused between calls.
    base_url:
        Alternative URL of the API (kept primarily for testing).
    request_delay:
        Artificial pause between requests so that we respect the public rate
        limit.  The default value (0.12s) keeps us well below 10 requests per
        second.
    """

    def __init__(
        self,
        session: Optional[requests.Session] = None,
        *,
        base_url: str = BASE_URL,
        request_delay: float = REQUEST_DELAY,
    ) -> None:
        self.session = session or requests.Session()
        self.base_url = base_url.rstrip("/")
        self.request_delay = request_delay

    def _build_params(
        self,
        *,
        expr: str,
        fields: Iterable[str],
        fmt: str,
        page_size: int,
        page_token: Optional[str],
    ) -> Dict[str, object]:
        params: Dict[str, object] = {
            "format": fmt,
            "pageSize": page_size,
        }
        if expr:
            params["query.term"] = expr

        normalised_fields = self._normalise_fields(fields)
        if normalised_fields:
            params["fields"] = ",".join(normalised_fields)

        if page_token:
            params["pageToken"] = page_token

        return params

    @staticmethod
    def _normalise_fields(fields: Iterable[str]) -> List[str]:
        unique: Dict[str, None] = {}
        for field in fields:
            if not field:
                continue
            unique[str(field)] = None
        return list(unique.keys())

    def _parse_response(self, payload: Dict[str, object]) -> StudyFieldsResponse:
        if not isinstance(payload, dict):
            raise ClinicalTrialsAPIError("Malformed response received from ClinicalTrials.gov")

        studies_raw = payload.get("studies")
        if not isinstance(studies_raw, list):
            raise ClinicalTrialsAPIError("Unexpected response shape: missing 'studies'")

        studies: List[Dict[str, List[str]]] = [self._coerce_fields(entry) for entry in studies_raw]

        total_studies = self._extract_int(payload, ["totalCount", "count", "totalStudies", "total"])
        if total_studies is None:
            total_studies = len(studies)

        next_page_token = payload.get("nextPageToken")
        if not isinstance(next_page_token, str):
            next_page_token = None

        next_rank: Optional[int] = None
        if next_page_token is not None:
            try:
                next_rank = int(next_page_token)
            except ValueError:
                next_rank = None

        return StudyFieldsResponse(
            studies=studies,
            total_studies=total_studies,
            next_rank=next_rank,
            next_page_token=next_page_token,
        )

    def _coerce_fields(self, entry: object) -> Dict[str, List[str]]:
        if not isinstance(entry, dict):
            return {}

        if "fields" in entry and isinstance(entry["fields"], dict):
            data = entry["fields"]
        else:
            data = entry

        if not isinstance(data, dict):
            return {}

        result: Dict[str, List[str]] = {}
        for key, value in data.items():
            if isinstance(value, list):
                str_values = [str(item) for item in value]
            elif value is None:
                str_values = []
            else:
                str_values = [str(value)]
            result[str(key)] = str_values
        return result

    @staticmethod
    def _extract_int(payload: Dict[str, object], keys: Sequence[str]) -> Optional[int]:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, int):
                return value
            if isinstance(value, str):
                try:
                    return int(value)
                except ValueError:
                    continue
        return None

    def fetch_study_fields(
        self,
        *,
        expr: str,
        fields: Iterable[str],
        min_rank: int = 1,
        max_rank: Optional[int] = None,
        batch_size: int = 100,
        fmt: str = "json",
    ) -> Iterator[StudyFieldsResponse]:
        """Stream batched ``study_fields`` responses."""
        target_min = max(1, min_rank)
        current_rank = 1
        remaining: Optional[int] = None
        if max_rank is not None:
            remaining = max(max_rank - target_min + 1, 0)
            if remaining == 0:
                return

        page_token: Optional[str] = None

        while True:
            if remaining is not None and remaining <= 0:
                break

            page_size = batch_size
            if remaining is not None and current_rank >= target_min and remaining < batch_size:
                page_size = max(1, remaining)

            params = self._build_params(
                expr=expr,
                fields=fields,
                fmt=fmt,
                page_size=page_size,
                page_token=page_token,
            )

            resp = self.session.get(self.base_url, params=params, timeout=30)
            if resp.status_code != 200:
                raise ClinicalTrialsAPIError(
                    f"ClinicalTrials.gov returned HTTP {resp.status_code}: {resp.text[:200]}"
                )

            chunk = self._parse_response(resp.json())

            studies = chunk.studies

            if not studies:
                break

            if current_rank < target_min:
                skip = min(target_min - current_rank, len(studies))
                studies = studies[skip:]
                current_rank += skip

            if remaining is not None:
                studies = studies[:remaining]

            fetched = len(studies)

            if not fetched:
                page_token = chunk.next_page_token
                if not page_token:
                    break
                time.sleep(self.request_delay)
                continue

            next_rank = current_rank + fetched
            yield StudyFieldsResponse(
                studies=studies,
                total_studies=chunk.total_studies,
                next_rank=next_rank if next_rank <= chunk.total_studies else None,
                next_page_token=chunk.next_page_token,
            )

            current_rank = next_rank
            if remaining is not None:
                remaining -= fetched
            if remaining is not None and remaining <= 0:
                break

            page_token = chunk.next_page_token
            if not page_token:
                break

            time.sleep(self.request_delay)

    def fetch_all_study_fields(
        self,
        *,
        expr: str,
        fields: Iterable[str],
        batch_size: int = 100,
    ) -> List[Dict[str, List[str]]]:
        """Convenience helper that materialises the generator into a list."""

        studies: List[Dict[str, List[str]]] = []
        for chunk in self.fetch_study_fields(
            expr=expr,
            fields=fields,
            batch_size=batch_size,
        ):
            studies.extend(chunk.studies)
        return studies


__all__ = [
    "ClinicalTrialsClient",
    "ClinicalTrialsAPIError",
    "StudyFieldsResponse",
]
