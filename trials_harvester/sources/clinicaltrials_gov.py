"""Fetcher implementation for ClinicalTrials.gov."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterator, Optional

import requests

from .. import __version__
from .base import BaseFetcher, FetchConfig

BASE_URL = "https://clinicaltrials.gov/api/query/full_studies"
USER_AGENT = f"trials-harvester/{__version__}"
REQUEST_DELAY = 0.5
TRANSIENT_STATUS = {429, 500, 502, 503, 504}


class ClinicalTrialsTemporaryError(RuntimeError):
    """Raised when the API signals a transient problem."""


@dataclass
class _RequestParams:
    expr: str
    min_rank: int
    max_rank: int


class ClinicalTrialsGovFetcher(BaseFetcher):
    """Stream :mod:`clinicaltrials.gov` studies via the public API."""

    source = "clinicaltrials_gov"

    def __init__(
        self,
        config: FetchConfig,
        *,
        session: Optional[requests.Session] = None,
        request_delay: float = REQUEST_DELAY,
        max_attempts: int = 5,
    ) -> None:
        super().__init__(config)
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", USER_AGENT)
        self.request_delay = request_delay
        self.max_attempts = max(1, max_attempts)

    def _build_expression(self) -> str:
        parts: list[str] = []
        if self.config.query:
            parts.append(f"({self.config.query})")

        if self.config.sponsors:
            sponsor_clause = " OR ".join(
                f'LEADSPONSOR:"{s}"' for s in self.config.sponsors
            )
            parts.append(f"({sponsor_clause})")

        if self.config.countries:
            country_clause = " OR ".join(
                f'AREA[LocationCountry] {country}' for country in self.config.countries
            )
            parts.append(f"({country_clause})")

        if self.config.phases:
            phase_clause = " OR ".join(
                f'PHASE:"{phase}"' for phase in self.config.phases
            )
            parts.append(f"({phase_clause})")

        if self.config.statuses:
            status_clause = " OR ".join(
                f'OVERALLSTATUS:"{status}"' for status in self.config.statuses
            )
            parts.append(f"({status_clause})")

        if not parts:
            raise ValueError(
                "At least one of --query/--sponsor/--country/--phase/--status must be provided"
            )

        return " AND ".join(parts)

    def _filter_by_date(self, study: Dict[str, object]) -> bool:
        since = self.parse_date(self.config.since)
        until = self.parse_date(self.config.until)
        protocol = study.get("ProtocolSection", {}) if isinstance(study, dict) else {}
        status_module = protocol.get("StatusModule", {}) if isinstance(protocol, dict) else {}
        last_update = None
        if isinstance(status_module, dict):
            struct = status_module.get("LastUpdatePostDateStruct")
            if isinstance(struct, dict):
                last_update = struct.get("LastUpdatePostDate")
            if last_update is None:
                last_update = status_module.get("LastUpdatePostDate")
        parsed = None
        if isinstance(last_update, str):
            for fmt in ("%B %Y", "%B %d, %Y"):
                try:
                    parsed = datetime.strptime(last_update, fmt)
                    break
                except ValueError:
                    continue
            if parsed is None:
                try:
                    parsed = datetime.fromisoformat(last_update)
                except ValueError:
                    parsed = None
        if since and parsed and parsed < since:
            return False
        if until and parsed and parsed > until:
            return False
        return True

    def _build_params(self, min_rank: int, max_rank: int) -> _RequestParams:
        expr = self._build_expression()
        return _RequestParams(expr=expr, min_rank=min_rank, max_rank=max_rank)

    def _perform_request(self, params: _RequestParams) -> Dict[str, object]:
        attempt = 0
        delay = 1.0
        while True:
            attempt += 1
            try:
                response = self.session.get(
                    BASE_URL,
                    params={
                        "expr": params.expr,
                        "min_rnk": params.min_rank,
                        "max_rnk": params.max_rank,
                        "fmt": "json",
                    },
                    timeout=60,
                )
            except requests.RequestException as exc:  # pragma: no cover - network error
                if attempt >= self.max_attempts:
                    raise ClinicalTrialsTemporaryError(str(exc)) from exc
                time.sleep(min(60.0, delay))
                delay *= 2
                continue

            if response.status_code in TRANSIENT_STATUS:
                if attempt >= self.max_attempts:
                    raise ClinicalTrialsTemporaryError(
                        f"ClinicalTrials.gov returned {response.status_code}: {response.text[:200]}"
                    )
                time.sleep(min(60.0, delay))
                delay *= 2
                continue

            response.raise_for_status()
            return response.json()

    def fetch(self) -> Iterator[Dict[str, object]]:
        min_rank = 1
        max_records = self.config.max_records
        batch_size = max(1, self.config.batch_size)

        while True:
            upper = min_rank + batch_size - 1
            if max_records is not None:
                upper = min(upper, max_records)

            params = self._build_params(min_rank, upper)
            payload = self._perform_request(params)
            data = payload.get("FullStudiesResponse", {})
            studies = []
            if isinstance(data, dict):
                studies = data.get("FullStudies", [])  # type: ignore[assignment]
            if not studies:
                break

            fetched = 0
            for wrapper in studies:
                study = wrapper.get("Study") if isinstance(wrapper, dict) else None
                if isinstance(study, dict) and self._filter_by_date(study):
                    yield study
                    fetched += 1

            if fetched == 0:
                break

            min_rank += batch_size
            if max_records is not None and min_rank > max_records:
                break

            time.sleep(self.request_delay)


__all__ = ["ClinicalTrialsGovFetcher"]
