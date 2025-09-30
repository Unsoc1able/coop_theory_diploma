"""Build reusable datasets from ClinicalTrials.gov for the R&D dashboard.

The goal of the script is to provide a reproducible way of collecting aggregated
statistics about clinical trials directly from the public ClinicalTrials.gov
API.  The dashboard contained in ``cooperative_rnd_model_interactive.html``
focuses on counts of late stage trials (phases I-III) for a list of pharma
companies.  The helper below replicates those numbers based on the actual
registry data.

Example usage from the command line::

    $ python data_fetch/build_clinical_trials_dataset.py \
        --sponsor Pfizer --sponsor BIOCAD --max-studies 500 \
        --out data/clinical_trials_by_sponsor.json

The resulting JSON is structured as follows::

    {
        "generated_at": "2024-05-01T12:00:00Z",
        "expr": "Sponsorship filters used in the query",
        "sponsors": [
            {
                "name": "Pfizer",
                "total_trials": 134,
                "phase_counts": {"Phase 1": 34, "Phase 2": 51, ...},
                "status_counts": {"Recruiting": 24, "Completed": 70, ...}
            },
            ...
        ]
    }

The aggregation makes it easy to align the dashboard inputs with the public
registries and can be re-run periodically to refresh the data.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

try:  # pragma: no cover - runtime import resolution helper
    if __package__:
        from .clinical_trials_api import ClinicalTrialsClient
    else:  # When executed as ``python data_fetch/build_clinical_trials_dataset.py``
        from clinical_trials_api import ClinicalTrialsClient  # type: ignore
except ImportError:  # Fallback to path manipulation when packaged import fails
    import sys

    from pathlib import Path as _Path

    sys.path.append(str(_Path(__file__).resolve().parent))
    from clinical_trials_api import ClinicalTrialsClient  # type: ignore

# Fields that we will reuse.  ``Phase`` and ``OverallStatus`` are critical for
# the R&D modelling.  Additional metadata makes the dataset more useful for
# debugging and manual inspection.
FIELDS = [
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
]

# Keywords used by the API when a study does not contain a standard phase entry.
NON_PHASE_VALUES = {
    "EARLY_PHASE1": "Early Phase 1",
    "NA": "Not Applicable",
    "PHASE1_PHASE2": "Phase 1/Phase 2",
    "PHASE2_PHASE3": "Phase 2/Phase 3",
}


def normalise_phase(value: str) -> Sequence[str]:
    """Split compound phase labels into canonical buckets.

    The API uses strings such as ``"Phase 1|Phase 2"`` or ``"Phase 1/Phase 2"``
    to represent studies that span multiple stages.  For the dashboard we are
    primarily interested in the aggregated counts per (I, II, III).  When a
    multi-phase entry is detected we increment counters for each individual
    bucket.  Non-standard values are mapped using :data:`NON_PHASE_VALUES`.
    """

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


def aggregate_trials(studies: Iterable[Dict[str, List[str]]]) -> Dict[str, Counter]:
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


def build_dataset_for_sponsor(
    client: ClinicalTrialsClient,
    sponsor: str,
    *,
    max_studies: int,
    expr_template: str,
    batch_size: int,
) -> Dict[str, object]:
    """Fetch and aggregate studies for a particular sponsor."""

    expr = expr_template.format(sponsor=sponsor)
    studies: List[Dict[str, List[str]]] = []
    for chunk in client.fetch_study_fields(
        expr=expr,
        fields=FIELDS,
        batch_size=batch_size,
        max_rank=max_studies,
    ):
        studies.extend(chunk.studies)
    aggregated = aggregate_trials(studies)

    return {
        "name": sponsor,
        "expr": expr,
        "total_trials": len(studies),
        "phase_counts": dict(aggregated["phase_counts"]),
        "status_counts": dict(aggregated["status_counts"]),
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sponsor",
        action="append",
        help="Repeatable sponsor name filter (LeadSponsorName).",
    )
    parser.add_argument(
        "--expr",
        help=(
            "Custom ClinicalTrials.gov expression. Mutually exclusive with --sponsor."
            " When provided the query will be executed verbatim."
        ),
    )
    parser.add_argument(
        "--max-studies",
        type=int,
        default=1000,
        help="Upper bound for the number of studies retrieved per sponsor.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=200,
        help="Number of studies requested per API call (max 1000).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data/clinical_trials_by_sponsor.json"),
        help="Output path for the dataset (JSON).",
    )
    parser.add_argument(
        "--expr-template",
        default='LEADSPONSOR:"{sponsor}"',
        help="Template used to construct the API expression for each sponsor.",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="Indentation level for the output JSON file.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    client = ClinicalTrialsClient()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    dataset: Dict[str, object] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fields": FIELDS,
        "sponsors": [],
    }

    if args.expr:
        # Single expression mode – fetch everything matching the expression and
        # aggregate the results as a single cohort.
        studies: List[Dict[str, List[str]]] = []
        for chunk in client.fetch_study_fields(
            expr=args.expr,
            fields=FIELDS,
            batch_size=args.batch_size,
            max_rank=args.max_studies,
        ):
            studies.extend(chunk.studies)
        aggregated = aggregate_trials(studies)
        dataset["expr"] = args.expr
        dataset["total_trials"] = len(studies)
        dataset["phase_counts"] = dict(aggregated["phase_counts"])
        dataset["status_counts"] = dict(aggregated["status_counts"])
    else:
        sponsors = args.sponsor or [
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
        ]

        dataset["expr_template"] = args.expr_template
        for sponsor in sponsors:
            sponsor_data = build_dataset_for_sponsor(
                client,
                sponsor,
                max_studies=args.max_studies,
                expr_template=args.expr_template,
                batch_size=args.batch_size,
            )
            dataset["sponsors"].append(sponsor_data)

    with args.out.open("w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=args.indent)

    print(f"Dataset written to {args.out}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
