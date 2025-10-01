"""High level parsers for ClinicalTrials.gov datasets."""

from __future__ import annotations

from collections import Counter
from typing import Dict, Iterable, Iterator, List, Sequence

from .base import BaseParser
from .clinical_trials_api import ClinicalTrialsClient

# Fields that we will reuse. ``Phase`` and ``OverallStatus`` are critical for
# the R&D modelling. Additional metadata makes the dataset more useful for
# debugging and manual inspection.
FIELDS: Sequence[str] = (
    "NCTId",
    "LeadSponsorName",
    "CollaboratorName",
    "Phase",
    "OverallStatus",
    "StudyType",
    "Condition",
    "EnrollmentCount",
    "StartDate",
    "PrimaryCompletionDate",
    "LastUpdatePostDate",
)

DEFAULT_SPONSORS: Sequence[str] = (
    "Pfizer",
    "BIOCAD",
    "Generium",
    "R-Pharm",
    "Pharmstandard",
    "Geropharm",
    "Petrovax",
    "Valenta",
    "Nanolek",
    "ChemRar",
    "AstraZeneca",
    "Novartis",
    "Johnson & Johnson",
    "Roche",
    "Sanofi",
    "Bayer",
    "AbbVie",
    "Gilead",
    "Moderna",
    "Takeda",
)

# Keywords used by the API when a study does not contain a standard phase entry.
NON_PHASE_VALUES = {
    "EARLY_PHASE1": "Early Phase 1",
    "NA": "Not Applicable",
    "PHASE1_PHASE2": "Phase 1/Phase 2",
    "PHASE2_PHASE3": "Phase 2/Phase 3",
}


def normalise_phase(value: str) -> Sequence[str]:
    """Split compound phase labels into canonical buckets."""

    value = value.strip()
    if not value:
        return ()

    replacements = {
        "EARLY PHASE 1": "Early Phase 1",
        "PHASE 1/PHASE 2": "Phase 1/Phase 2",
        "PHASE 2/PHASE 3": "Phase 2/Phase 3",
    }
    value = replacements.get(value.upper(), value)
    if value.upper() in NON_PHASE_VALUES:
        return (NON_PHASE_VALUES[value.upper()],)

    separators = ["/", "|", ","]
    for sep in separators:
        if sep in value:
            return tuple(part.strip() for part in value.split(sep) if part.strip())
    return (value,)


def aggregate_trials(studies: Iterable[Dict[str, List[str]]]) -> Dict[str, Counter[str]]:
    """Aggregate per-phase and per-status statistics for the studies list."""

    phase_counter: Counter[str] = Counter()
    status_counter: Counter[str] = Counter()

    for study in studies:
        phase_values = study.get("Phase", [])
        if phase_values:
            for label in normalise_phase(phase_values[0]):
                phase_counter[label] += 1

        status_values = study.get("OverallStatus", [])
        if status_values:
            status_counter[status_values[0]] += 1

    return {
        "phase_counts": phase_counter,
        "status_counts": status_counter,
    }


class _ClinicalTrialsBaseParser(BaseParser):
    """Common configuration shared by ClinicalTrials.gov parsers."""

    def __init__(
        self,
        *,
        client: ClinicalTrialsClient | None = None,
        fields: Sequence[str] = FIELDS,
        batch_size: int = 200,
        max_studies: int | None = 1000,
    ) -> None:
        self.client = client or ClinicalTrialsClient()
        self.fields = tuple(fields)
        self.batch_size = batch_size
        self.max_studies = max_studies

    def _collect_studies(self, expr: str) -> List[Dict[str, List[str]]]:
        """Fetch study records for the provided expression."""

        studies: List[Dict[str, List[str]]] = []
        fetch_kwargs = {}
        if self.max_studies is not None:
            fetch_kwargs["max_rank"] = self.max_studies

        for chunk in self.client.fetch_study_fields(
            expr=expr,
            fields=self.fields,
            batch_size=self.batch_size,
            **fetch_kwargs,
        ):
            studies.extend(chunk.studies)
        return studies

    @staticmethod
    def _format_aggregated(
        *,
        expr: str,
        studies: List[Dict[str, List[str]]],
    ) -> Dict[str, object]:
        aggregated = aggregate_trials(studies)
        return {
            "expr": expr,
            "total_trials": len(studies),
            "phase_counts": dict(aggregated["phase_counts"]),
            "status_counts": dict(aggregated["status_counts"]),
        }


class ClinicalTrialsBySponsorParser(_ClinicalTrialsBaseParser):
    """Parser that aggregates trial statistics per sponsor."""

    source = "clinical_trials_by_sponsor"

    def __init__(
        self,
        sponsors: Sequence[str] | None = None,
        *,
        expr_template: str = 'AREA[LeadSponsorName]"{sponsor}"',
        client: ClinicalTrialsClient | None = None,
        fields: Sequence[str] = FIELDS,
        batch_size: int = 200,
        max_studies: int | None = 1000,
    ) -> None:
        super().__init__(
            client=client,
            fields=fields,
            batch_size=batch_size,
            max_studies=max_studies,
        )
        self.expr_template = expr_template
        self.sponsors = tuple(sponsors or DEFAULT_SPONSORS)

    def fetch(self) -> Iterator[Dict[str, object]]:
        for sponsor in self.sponsors:
            expr = self.expr_template.format(sponsor=sponsor)
            studies = self._collect_studies(expr)
            payload = self._format_aggregated(expr=expr, studies=studies)
            payload["name"] = sponsor
            yield payload


class ClinicalTrialsExpressionParser(_ClinicalTrialsBaseParser):
    """Parser that aggregates statistics for an arbitrary expression."""

    source = "clinical_trials_expression"

    def __init__(
        self,
        expr: str,
        *,
        client: ClinicalTrialsClient | None = None,
        fields: Sequence[str] = FIELDS,
        batch_size: int = 200,
        max_studies: int | None = 1000,
    ) -> None:
        if not expr:
            raise ValueError("ClinicalTrialsExpressionParser requires a non-empty expression")

        super().__init__(
            client=client,
            fields=fields,
            batch_size=batch_size,
            max_studies=max_studies,
        )
        self.expr = expr

    def fetch(self) -> Iterator[Dict[str, object]]:
        studies = self._collect_studies(self.expr)
        yield self._format_aggregated(expr=self.expr, studies=studies)


__all__ = [
    "ClinicalTrialsBySponsorParser",
    "ClinicalTrialsExpressionParser",
    "DEFAULT_SPONSORS",
    "FIELDS",
    "aggregate_trials",
    "normalise_phase",
]
