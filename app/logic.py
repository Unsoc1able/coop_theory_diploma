"""Domain logic for the cooperative R&D model."""

from __future__ import annotations

import itertools
import math
from typing import Dict, Iterable, List, Sequence

Company = Dict[str, float]
Parameters = Dict[str, float]


def expected_approvals(company: Company, params: Parameters) -> float:
    """Return expected approvals for a company."""
    p1, p2, p3 = params["p1"], params["p2"], params["p3"]
    return (
        company["n_I"] * (p1 * p2 * p3)
        + company["n_II"] * (p2 * p3)
        + company["n_III"] * p3
    )


def cost_per_project(phase: str, params: Parameters) -> float:
    """Expected cost of advancing a single project from a phase."""
    p1, p2, p3 = params["p1"], params["p2"], params["p3"]
    c_i, c_ii, c_iii, c_reg = (
        params["C_I"],
        params["C_II"],
        params["C_III"],
        params["C_REG"],
    )

    if phase == "I":
        return c_i + p1 * c_ii + (p1 * p2) * c_iii + (p1 * p2 * p3) * c_reg
    if phase == "II":
        return c_ii + p2 * c_iii + (p2 * p3) * c_reg
    if phase == "III":
        return c_iii + p3 * c_reg
    raise ValueError(f"Unsupported phase: {phase}")


def expected_budget(company: Company, params: Parameters) -> float:
    """Return expected budget for a company's portfolio."""
    return (
        company["n_I"] * cost_per_project("I", params)
        + company["n_II"] * cost_per_project("II", params)
        + company["n_III"] * cost_per_project("III", params)
    )


def compute_company_metrics(
    companies: Sequence[Company], params: Parameters
) -> List[Dict[str, float]]:
    """Compute derived metrics for each company."""
    rows: List[Dict[str, float]] = []
    for company in companies:
        approvals = expected_approvals(company, params)
        budget = expected_budget(company, params)
        unit_cost = budget / approvals if approvals else math.nan
        rows.append(
            {
                "name": company["name"],
                "n_I": company["n_I"],
                "n_II": company["n_II"],
                "n_III": company["n_III"],
                "approvals": approvals,
                "budget": budget,
                "unit_cost": unit_cost,
            }
        )
    return rows


def _coalition_totals(
    players: Iterable[str], companies: Sequence[Company]
) -> Company:
    totals = {"name": "coalition", "n_I": 0.0, "n_II": 0.0, "n_III": 0.0}
    for player in players:
        company = next((c for c in companies if c["name"] == player), None)
        if company:
            totals["n_I"] += company["n_I"]
            totals["n_II"] += company["n_II"]
            totals["n_III"] += company["n_III"]
    return totals


def _effective_parameters(params: Parameters) -> Parameters:
    p3_eff = min(
        params["coop_p3_cap"],
        params["p3"] + params["coop_dp3"],
    )
    c3_eff = params["C_III"] * (1 - params["coop_c3_reduction"] / 100)
    coop_params = params.copy()
    coop_params["p3"] = p3_eff
    coop_params["C_III"] = c3_eff
    return coop_params


def coalition_savings(
    players: Iterable[str],
    companies: Sequence[Company],
    params: Parameters,
) -> float:
    """Return savings (solo budget - cooperative budget) for a coalition."""
    players = list(players)
    if not players:
        return 0.0
    solo = sum(
        expected_budget(company, params)
        for company in companies
        if company["name"] in players
    )
    coop_company = _coalition_totals(players, companies)
    coop_budget = expected_budget(coop_company, _effective_parameters(params))
    return solo - coop_budget


def shapley_values(
    players: Sequence[str],
    companies: Sequence[Company],
    params: Parameters,
) -> Dict[str, float]:
    """Compute Shapley values for a set of players."""
    players = list(players)
    n = len(players)
    if n == 0:
        return {}
    phi = {player: 0.0 for player in players}
    for order in itertools.permutations(players):
        coalition: List[str] = []
        for player in order:
            before = coalition_savings(coalition, companies, params)
            coalition.append(player)
            after = coalition_savings(coalition, companies, params)
            phi[player] += after - before
    denom = math.factorial(n)
    for player in phi:
        phi[player] /= denom
    return phi


def core_check(
    phi: Dict[str, float],
    players: Sequence[str],
    companies: Sequence[Company],
    params: Parameters,
) -> bool:
    """Return True if the Shapley point lies in the core."""
    players = list(players)
    grand = coalition_savings(players, companies, params)
    if not math.isclose(sum(phi.values()), grand, rel_tol=1e-6, abs_tol=1e-6):
        return False
    for r in range(1, len(players)):
        for subset in itertools.combinations(players, r):
            lhs = sum(phi[player] for player in subset)
            rhs = coalition_savings(subset, companies, params)
            if lhs + 1e-9 < rhs:
                return False
    return True
