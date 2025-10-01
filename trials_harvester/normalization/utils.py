"""Helper functions shared by normalisers."""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, List, Optional

try:  # pragma: no cover - optional dependency
    import pycountry
except ImportError:  # pragma: no cover - optional dependency
    pycountry = None

from dateutil import parser as date_parser

_FALLBACK_COUNTRIES = {
    "UNITED STATES": "US",
    "UNITED STATES OF AMERICA": "US",
    "USA": "US",
    "U.S.": "US",
    "CANADA": "CA",
    "RUSSIA": "RU",
    "RUSSIAN FEDERATION": "RU",
    "PEOPLES REPUBLIC OF CHINA": "CN",
    "CHINA": "CN",
    "GERMANY": "DE",
    "FRANCE": "FR",
    "UNITED KINGDOM": "GB",
}


def parse_date(value: Optional[str]) -> Optional[str]:
    """Return a normalised ISO date string."""

    if not value:
        return None
    try:
        dt = date_parser.parse(value, default=datetime(1900, 1, 1))
    except (ValueError, TypeError):
        return None
    return dt.strftime("%Y-%m-%d")


_PHASE_PRIORITY = {"I": 1, "II": 2, "III": 3, "IV": 4, "NA": 99}
_PHASE_MAP = {
    "PHASE 1": ["I"],
    "EARLY PHASE 1": ["I"],
    "PHASE 2": ["II"],
    "PHASE 3": ["III"],
    "PHASE 4": ["IV"],
    "PHASE 1/PHASE 2": ["I", "II"],
    "PHASE 2/PHASE 3": ["II", "III"],
    "PHASE 3/PHASE 4": ["III", "IV"],
    "NOT APPLICABLE": ["NA"],
    "NA": ["NA"],
    "N/A": ["NA"],
}


def normalize_phase(phases: Iterable[str] | None) -> Optional[str]:
    if not phases:
        return None

    buckets: List[str] = []
    for raw in phases:
        value = str(raw).strip()
        if not value:
            continue
        upper = value.upper()
        mapped = _PHASE_MAP.get(upper)
        if mapped:
            buckets.extend(mapped)
            continue
        if "/" in value:
            sub = normalize_phase(value.split("/"))
            if sub:
                buckets.extend(sub.split("/"))
            continue
        buckets.append(value)

    if not buckets:
        return None

    deduped: List[str] = []
    for item in buckets:
        if item not in deduped:
            deduped.append(item)

    deduped.sort(key=lambda x: _PHASE_PRIORITY.get(x, 50))
    return "/".join(deduped)


_STATUS_MAP = {
    "NOT YET RECRUITING": "not_yet_recruiting",
    "RECRUITING": "recruiting",
    "ENROLLING BY INVITATION": "recruiting",
    "ACTIVE, NOT RECRUITING": "active",
    "COMPLETED": "completed",
    "SUSPENDED": "suspended",
    "TERMINATED": "terminated",
    "WITHDRAWN": "terminated",
    "UNKNOWN STATUS": "unknown",
    "NO LONGER AVAILABLE": "terminated",
    "AVAILABLE": "active",
}


def normalize_status(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return _STATUS_MAP.get(value.upper(), value.lower())


def normalize_study_type(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    stripped = value.strip()
    return stripped.lower() if stripped else None


def normalize_countries(values: Iterable[str] | None) -> List[str]:
    if not values:
        return []

    countries: List[str] = []
    for raw in values:
        item = str(raw).strip()
        if not item:
            continue
        code = None
        upper = item.upper()
        if pycountry is not None:  # pragma: no cover - depends on optional package
            try:
                country = pycountry.countries.lookup(item)
            except LookupError:
                country = None
            if country is not None:
                code = country.alpha_2.upper()
        if code is None:
            code = _FALLBACK_COUNTRIES.get(upper)
        if code is None and len(item) == 2:
            code = upper
        if code:
            countries.append(code)
    deduped: List[str] = []
    for code in countries:
        if code not in deduped:
            deduped.append(code)
    return deduped


__all__ = [
    "normalize_countries",
    "normalize_phase",
    "normalize_status",
    "normalize_study_type",
    "parse_date",
]
