"""Data structures describing the unified trial schema."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional


@dataclass
class Trial:
    source: str
    source_id: str
    public_title: Optional[str] = None
    scientific_title: Optional[str] = None
    sponsor_primary: Optional[str] = None
    sponsors_all: List[str] = field(default_factory=list)
    phase: Optional[str] = None
    overall_status: Optional[str] = None
    study_type: Optional[str] = None
    enrollment: Optional[int] = None
    centers_count: Optional[int] = None
    countries: List[str] = field(default_factory=list)
    conditions: List[str] = field(default_factory=list)
    interventions: List[str] = field(default_factory=list)
    start_date: Optional[str] = None
    primary_completion_date: Optional[str] = None
    completion_date: Optional[str] = None
    nct_id: Optional[str] = None
    eudract_number: Optional[str] = None
    isrctn: Optional[str] = None
    protocol_id: Optional[str] = None
    last_updated_date: Optional[str] = None
    language: Optional[str] = None
    raw_payload: Dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


__all__ = ["Trial"]
