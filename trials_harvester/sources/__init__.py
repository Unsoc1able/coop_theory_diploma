"""Source registry for fetcher implementations."""

from __future__ import annotations

from typing import Iterable, Optional, Type

from .base import BaseFetcher, FetchConfig
from .clinicaltrials_gov import ClinicalTrialsGovFetcher

_FETCHER_ALIASES: dict[str, Type[BaseFetcher]] = {
    "clinicaltrials": ClinicalTrialsGovFetcher,
    "clinicaltrials_gov": ClinicalTrialsGovFetcher,
    "ctg": ClinicalTrialsGovFetcher,
}


def _normalise_iterable(values: Optional[Iterable[str]]) -> Optional[tuple[str, ...]]:
    if values is None:
        return None
    return tuple(v for v in values if v)


def create_fetcher(
    *,
    source: str,
    query: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    countries: Optional[Iterable[str]] = None,
    sponsors: Optional[Iterable[str]] = None,
    phases: Optional[Iterable[str]] = None,
    statuses: Optional[Iterable[str]] = None,
    batch_size: int = 100,
    max_records: Optional[int] = None,
) -> BaseFetcher:
    """Instantiate a fetcher for ``source`` using the provided configuration."""

    key = source.lower().strip()
    if key not in _FETCHER_ALIASES:
        raise ValueError(f"Unsupported source: {source}")

    fetcher_cls = _FETCHER_ALIASES[key]
    config = FetchConfig(
        query=query,
        since=since,
        until=until,
        countries=_normalise_iterable(countries),
        sponsors=_normalise_iterable(sponsors),
        phases=_normalise_iterable(phases),
        statuses=_normalise_iterable(statuses),
        batch_size=batch_size,
        max_records=max_records,
    )
    return fetcher_cls(config)


__all__ = ["BaseFetcher", "FetchConfig", "create_fetcher"]
