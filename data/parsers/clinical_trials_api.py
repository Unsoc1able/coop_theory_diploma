"""Utilities for interacting with the ClinicalTrials.gov API.

This module exposes thin wrappers above the ClinicalTrials.gov Data API.
The helper targets the v2 ``/studies`` endpoint which provides structured
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
import re
from typing import Dict, Iterable, Iterator, List, Optional, Sequence

import requests

# The modern v2 ClinicalTrials.gov API groups study metadata under the
# ``/api/v2/studies`` endpoint.  It replaces the legacy ``study_fields`` query
# API that became unreliable in mid-2024.
BASE_URL = "https://clinicaltrials.gov/api/v2/studies"
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
    """Client for the ClinicalTrials.gov ``/api/v2/studies`` Data API endpoint.

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
            params["query.term"] = self._translate_legacy_expression(expr)

        normalised_fields = self._normalise_fields(fields)
        if normalised_fields:
            params["fields"] = ",".join(normalised_fields)

        if page_token:
            params["pageToken"] = page_token
        else:
            # ``countTotal`` is only honoured on the first request; subsequent
            # calls reuse the ``pageToken`` supplied by the API.
            params["countTotal"] = "true"

        return params

    @staticmethod
    def _normalise_fields(fields: Iterable[str]) -> List[str]:
        unique: Dict[str, None] = {}
        for field in fields:
            if not field:
                continue
            unique[str(field)] = None
        return list(unique.keys())

    @staticmethod
    def _translate_legacy_expression(expr: str) -> str:
        pattern = re.compile(r"LEADSPONSOR\s*:\s*(\"[^\"]+\"|[^\s()]+)", re.IGNORECASE)

        def repl(match: re.Match[str]) -> str:
            raw = match.group(1)
            if raw.startswith('"') and raw.endswith('"'):
                inner = raw[1:-1]
                quoted = f'"{inner}"'
            else:
                inner = raw
                quoted = f'"{inner}"' if any(ch.isspace() for ch in inner) else inner
            return f'AREA[LeadSponsorName]{quoted}'

        return pattern.sub(repl, expr)

    def _parse_response(
        self,
        payload: Dict[str, object],
        *,
        fields: Sequence[str],
    ) -> StudyFieldsResponse:
        if not isinstance(payload, dict):
            raise ClinicalTrialsAPIError("Malformed response received from ClinicalTrials.gov")

        studies_raw = payload.get("studies")
        if not isinstance(studies_raw, list):
            raise ClinicalTrialsAPIError("Unexpected response shape: missing 'studies'")

        requested_fields = tuple(fields)
        studies: List[Dict[str, List[str]]] = []
        for entry in studies_raw:
            studies.append(self._convert_study(entry, requested_fields))

        total_studies = self._extract_int(payload, ["totalCount", "count", "totalStudies", "total"])
        if total_studies is None:
            total_studies = len(studies)

        next_page_token = payload.get("nextPageToken")
        if not isinstance(next_page_token, str):
            next_page_token = None

        return StudyFieldsResponse(
            studies=studies,
            total_studies=total_studies,
            next_rank=None,
            next_page_token=next_page_token,
        )

    def _convert_study(
        self,
        entry: object,
        fields: Sequence[str],
    ) -> Dict[str, List[str]]:
        if not isinstance(entry, dict):
            return {}

        if "fields" in entry and isinstance(entry["fields"], dict):
            return self._coerce_fields(entry["fields"])

        if "protocolSection" in entry and isinstance(entry["protocolSection"], dict):
            return self._extract_from_protocol(entry["protocolSection"], fields)

        return self._coerce_fields(entry)

    def _extract_from_protocol(
        self,
        protocol_section: Dict[str, object],
        fields: Sequence[str],
    ) -> Dict[str, List[str]]:
        result: Dict[str, List[str]] = {}
        for field in fields:
            if field == "NCTId":
                values = self._extract_nct_id(protocol_section)
            elif field == "LeadSponsorName":
                values = self._extract_lead_sponsor(protocol_section)
            elif field == "CollaboratorName":
                values = self._extract_collaborators(protocol_section)
            elif field == "Phase":
                values = self._extract_phase(protocol_section)
            elif field == "OverallStatus":
                values = self._extract_overall_status(protocol_section)
            elif field == "StudyType":
                values = self._extract_study_type(protocol_section)
            elif field == "Condition":
                values = self._extract_conditions(protocol_section)
            elif field == "EnrollmentCount":
                values = self._extract_enrollment(protocol_section)
            elif field == "StartDate":
                values = self._extract_start_date(protocol_section)
            elif field == "PrimaryCompletionDate":
                values = self._extract_primary_completion_date(protocol_section)
            elif field == "LastUpdatePostDate":
                values = self._extract_last_update_post_date(protocol_section)
            else:
                values = []

            result[field] = [str(value) for value in values if value is not None and value != ""]
        return result

    @staticmethod
    def _extract_lead_sponsor(protocol_section: Dict[str, object]) -> List[str]:
        sponsor_module = protocol_section.get("sponsorCollaboratorsModule")
        if isinstance(sponsor_module, dict):
            lead = sponsor_module.get("leadSponsor")
            if isinstance(lead, dict):
                name = lead.get("name")
                if isinstance(name, str):
                    return [name]
        return []

    @staticmethod
    def _extract_collaborators(protocol_section: Dict[str, object]) -> List[str]:
        sponsor_module = protocol_section.get("sponsorCollaboratorsModule")
        collaborators: List[str] = []
        if isinstance(sponsor_module, dict):
            raw_collaborators = sponsor_module.get("collaborators")
            if isinstance(raw_collaborators, list):
                for item in raw_collaborators:
                    if isinstance(item, dict):
                        name = item.get("name")
                        if isinstance(name, str):
                            collaborators.append(name)
        return collaborators

    @classmethod
    def _extract_phase(cls, protocol_section: Dict[str, object]) -> List[str]:
        design_module = protocol_section.get("designModule")
        if isinstance(design_module, dict):
            phases = design_module.get("phases")
            if isinstance(phases, list):
                return [cls._normalise_phase_label(phase) for phase in phases if isinstance(phase, str)]
        return []

    @staticmethod
    def _extract_overall_status(protocol_section: Dict[str, object]) -> List[str]:
        status_module = protocol_section.get("statusModule")
        if isinstance(status_module, dict):
            value = status_module.get("overallStatus")
            if isinstance(value, str):
                return [value.replace("_", " ").title()]
        return []

    @staticmethod
    def _extract_study_type(protocol_section: Dict[str, object]) -> List[str]:
        design_module = protocol_section.get("designModule")
        if isinstance(design_module, dict):
            value = design_module.get("studyType")
            if isinstance(value, str):
                return [value.replace("_", " ").title()]
        return []

    @staticmethod
    def _extract_conditions(protocol_section: Dict[str, object]) -> List[str]:
        conditions_module = protocol_section.get("conditionsModule")
        if isinstance(conditions_module, dict):
            conditions = conditions_module.get("conditions")
            if isinstance(conditions, list):
                return [condition for condition in conditions if isinstance(condition, str)]
        return []

    @staticmethod
    def _extract_enrollment(protocol_section: Dict[str, object]) -> List[str]:
        design_module = protocol_section.get("designModule")
        if isinstance(design_module, dict):
            enrollment = design_module.get("enrollmentInfo")
            if isinstance(enrollment, dict):
                count = enrollment.get("count")
                if isinstance(count, (int, float, str)):
                    return [str(count)]
        return []

    @classmethod
    def _extract_nct_id(cls, protocol_section: Dict[str, object]) -> List[str]:
        identification_module = protocol_section.get("identificationModule")
        if isinstance(identification_module, dict):
            value = identification_module.get("nctId")
            if isinstance(value, str):
                return [value]
        return []

    @staticmethod
    def _extract_date_field(protocol_section: Dict[str, object], key: str) -> List[str]:
        status_module = protocol_section.get("statusModule")
        if isinstance(status_module, dict):
            struct = status_module.get(key)
            if isinstance(struct, dict):
                date_value = struct.get("date")
                if isinstance(date_value, str):
                    return [date_value]
        return []

    @classmethod
    def _extract_start_date(cls, protocol_section: Dict[str, object]) -> List[str]:
        return cls._extract_date_field(protocol_section, "startDateStruct")

    @classmethod
    def _extract_primary_completion_date(cls, protocol_section: Dict[str, object]) -> List[str]:
        return cls._extract_date_field(protocol_section, "primaryCompletionDateStruct")

    @classmethod
    def _extract_last_update_post_date(cls, protocol_section: Dict[str, object]) -> List[str]:
        return cls._extract_date_field(protocol_section, "lastUpdatePostDateStruct")

    @staticmethod
    def _normalise_phase_label(value: str) -> str:
        label_map = {
            "EARLY_PHASE1": "Early Phase 1",
            "PHASE1": "Phase 1",
            "PHASE2": "Phase 2",
            "PHASE3": "Phase 3",
            "PHASE4": "Phase 4",
            "NA": "Not Applicable",
            "PHASE1_PHASE2": "Phase 1/Phase 2",
            "PHASE2_PHASE3": "Phase 2/Phase 3",
        }
        value = value.strip().upper()
        if not value:
            return ""
        return label_map.get(value, value.replace("_", " ").title())

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
        field_list = tuple(fields)
        target_min = max(1, min_rank)
        current_rank = 1
        remaining: Optional[int] = None
        if max_rank is not None:
            remaining = max(max_rank - target_min + 1, 0)
            if remaining == 0:
                return

        page_token: Optional[str] = None
        overall_total: Optional[int] = None

        while True:
            if remaining is not None and remaining <= 0:
                break

            page_size = batch_size
            if remaining is not None and current_rank >= target_min and remaining < batch_size:
                page_size = max(1, remaining)

            params = self._build_params(
                expr=expr,
                fields=field_list,
                fmt=fmt,
                page_size=page_size,
                page_token=page_token,
            )

            resp = self.session.get(self.base_url, params=params, timeout=30)
            if resp.status_code != 200:
                raise ClinicalTrialsAPIError(
                    f"ClinicalTrials.gov returned HTTP {resp.status_code}: {resp.text[:200]}"
                )

            chunk = self._parse_response(resp.json(), fields=field_list)

            if overall_total is None and chunk.total_studies:
                overall_total = chunk.total_studies
            elif overall_total is not None and chunk.total_studies > overall_total:
                overall_total = chunk.total_studies

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
                total_studies=overall_total or chunk.total_studies,
                next_rank=(
                    next_rank
                    if (overall_total or chunk.total_studies) >= next_rank
                    else None
                ),
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
