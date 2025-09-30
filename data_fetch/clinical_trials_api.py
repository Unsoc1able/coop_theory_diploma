"""Utilities for interacting with the ClinicalTrials.gov API.

This module exposes thin wrappers above the public REST API provided by
https://clinicaltrials.gov/.  The functions are intentionally lightweight so
that they can be reused from notebooks or from other scripts inside the
project.

The API exposes two main query endpoints:

* ``query/study_fields`` – allows retrieving structured fields for many
  studies at once and is perfect for building aggregated datasets.
* ``query/full_studies`` – returns verbose protocol documents.  Fetching the
  full records is usually unnecessary for dashboard style analytics, therefore
  the helper below focuses on ``study_fields``.

The implementation respects the public rate limit (10 requests per second as of
May 2024).  Batching is performed automatically using the ``min_rnk``/``max_rnk``
parameters provided by the API.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, Iterable, Iterator, List, Optional

import requests

BASE_URL = "https://clinicaltrials.gov/api/query/study_fields"
# The public documentation suggests keeping requests below 10 per second.
REQUEST_DELAY = 0.12


class ClinicalTrialsAPIError(RuntimeError):
    """Raised when ClinicalTrials.gov returns an error response."""


@dataclass
class StudyFieldsResponse:
    """Container holding the raw payload returned by ``study_fields``."""

    studies: List[Dict[str, List[str]]]
    total_studies: int
    next_rank: Optional[int]


class ClinicalTrialsClient:
    """Client for the ClinicalTrials.gov ``study_fields`` endpoint.

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
        """Stream batched ``study_fields`` responses.

        Parameters
        ----------
        expr:
            ClinicalTrials.gov search expression.  Example: ``"COVID-19"`` or
            ``"AREA[LocationCountry] Russia"``.
        fields:
            Sequence of field names to request.
        min_rank:
            Starting index (1-based) of the query window.
        max_rank:
            Upper bound of the query window.  ``None`` means "fetch everything"
            for the given expression.
        batch_size:
            Number of records returned in a single response.  The API accepts a
            maximum of 1_000 rows per call, however smaller batches make it
            easier to stay within the public rate limit.
        fmt:
            Response format.  ``json`` is recommended for downstream parsing.

        Yields
        ------
        :class:`StudyFieldsResponse`
            Each item contains the list of studies, the total number of studies
            matching the expression, and the ``min_rnk`` value to use in the
            next iteration.  Iteration stops automatically once all studies have
            been retrieved.
        """

        current = min_rank
        while True:
            if max_rank is not None and current > max_rank:
                break

            window_max = current + batch_size - 1
            if max_rank is not None:
                window_max = min(window_max, max_rank)

            params = {
                "expr": expr,
                "fields": ",".join(fields),
                "min_rnk": current,
                "max_rnk": window_max,
                "fmt": fmt,
            }

            resp = self.session.get(self.base_url, params=params, timeout=30)
            if resp.status_code != 200:
                raise ClinicalTrialsAPIError(
                    f"ClinicalTrials.gov returned HTTP {resp.status_code}: {resp.text[:200]}"
                )

            payload: Dict[str, Dict[str, object]] = resp.json()
            data = payload.get("StudyFieldsResponse")
            if not data or "StudyFields" not in data:
                raise ClinicalTrialsAPIError(
                    "Unexpected payload structure received from ClinicalTrials.gov"
                )

            studies = data.get("StudyFields", [])
            total_studies = int(data.get("NStudiesFound", 0))
            fetched = len(studies)
            next_rank = current + fetched if fetched else None

            yield StudyFieldsResponse(
                studies=studies,
                total_studies=total_studies,
                next_rank=next_rank,
            )

            if fetched == 0:
                break
            if max_rank is not None and next_rank is not None and next_rank > max_rank:
                break
            if next_rank is None or next_rank > total_studies:
                break

            current = next_rank
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
