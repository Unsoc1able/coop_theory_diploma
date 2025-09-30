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
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Dict, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from data.parsers.clinical_trials import (
    ClinicalTrialsBySponsorParser,
    ClinicalTrialsExpressionParser,
    DEFAULT_SPONSORS,
    FIELDS,
)
from data.parsers.clinical_trials_api import ClinicalTrialsClient


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
        "fields": list(FIELDS),
        "sponsors": [],
    }

    if args.expr:
        parser = ClinicalTrialsExpressionParser(
            expr=args.expr,
            client=client,
            fields=FIELDS,
            batch_size=args.batch_size,
            max_studies=args.max_studies,
        )
        record = parser.parse().payload["records"][0]
        dataset.update(record)
    else:
        sponsors = args.sponsor or list(DEFAULT_SPONSORS)
        parser = ClinicalTrialsBySponsorParser(
            sponsors=sponsors,
            expr_template=args.expr_template,
            client=client,
            fields=FIELDS,
            batch_size=args.batch_size,
            max_studies=args.max_studies,
        )
        dataset["expr_template"] = args.expr_template
        dataset["sponsors"] = parser.parse().payload["records"]

    with args.out.open("w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=args.indent)

    print(f"Dataset written to {args.out}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
