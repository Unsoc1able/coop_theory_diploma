"""Domain logic for the cooperative R&D model."""

from __future__ import annotations

import itertools
import math
import random
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence

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


@dataclass
class CoreViolation:
    """Detailed information about the core deficit of a coalition."""

    mask: int
    coalition: List[str]
    v_s: float
    phi_s: float
    deficit: float
    deficit_share: float
    size: int
    violation: bool
    marginals: Dict[str, float]


@dataclass
class CoreCheckResult:
    """Container with diagnostics of the core conditions."""

    efficient: bool
    total_phi: float
    grand_value: float
    coalitions: List[CoreViolation]
    sampled: bool = False


def _popcount(mask: int) -> int:
    count = 0
    while mask:
        mask &= mask - 1
        count += 1
    return count


def _collect_masks(
    n: int,
    *,
    r_max: Optional[int] = None,
    sample: Optional[int] = None,
) -> List[int]:
    """Return the masks that should be evaluated for the core check."""

    grand_mask = (1 << n) - 1
    masks: List[int] = []
    if sample and sample > 0:
        rng = random.Random(42)
        seen = {0, grand_mask}
        # Draw unique masks until either we exhaust the space or reach sample.
        while len(masks) < sample and len(seen) < (1 << n):
            mask = rng.randrange(1, grand_mask)
            if mask in seen:
                continue
            seen.add(mask)
            if r_max:
                size = _popcount(mask)
                if not (size <= r_max or size >= n - r_max):
                    continue
            masks.append(mask)
        return masks

    for mask in range(1, grand_mask):
        if r_max:
            size = _popcount(mask)
            if not (size <= r_max or size >= n - r_max):
                continue
        masks.append(mask)
    return masks


def core_diagnostics(
    phi: Dict[str, float],
    players: Sequence[str],
    companies: Sequence[Company],
    params: Parameters,
    *,
    eps_abs: float = 1e-6,
    eps_rel: float = 1e-9,
    r_max: Optional[int] = None,
    sample: Optional[int] = None,
) -> CoreCheckResult:
    """Evaluate core conditions and return detailed diagnostics."""

    players = list(players)
    n = len(players)
    if n == 0:
        return CoreCheckResult(True, 0.0, 0.0, [], sampled=False)

    index_of = {player: idx for idx, player in enumerate(players)}
    grand_mask = (1 << n) - 1
    v_cache: Dict[int, float] = {}

    def mask_to_players(mask: int) -> List[str]:
        return [player for player in players if mask >> index_of[player] & 1]

    def value_of(mask: int) -> float:
        if mask in v_cache:
            return v_cache[mask]
        if mask == 0:
            v_cache[mask] = 0.0
            return 0.0
        subset = mask_to_players(mask)
        val = coalition_savings(subset, companies, params)
        v_cache[mask] = val
        return val

    total_phi = sum(phi.get(player, 0.0) for player in players)
    grand_value = value_of(grand_mask)
    scale = max(1.0, abs(grand_value))
    eff_tol = max(eps_abs * scale, eps_rel * scale)
    efficient = abs(total_phi - grand_value) <= eff_tol

    coalitions: List[CoreViolation] = []
    sampled = False
    masks = _collect_masks(n, r_max=r_max, sample=sample)
    if sample:
        sampled = True

    for mask in masks:
        coalition_players = mask_to_players(mask)
        size = len(coalition_players)
        if size == 0 or size == n:
            continue
        v_s = value_of(mask)
        phi_s = sum(phi.get(player, 0.0) for player in coalition_players)
        tol = max(eps_abs * max(1.0, abs(v_s)), eps_rel * max(1.0, abs(v_s)))
        deficit = v_s - phi_s
        violation = deficit > tol
        denominator = max(1e-9, abs(v_s))
        deficit_share = deficit / denominator

        marginals: Dict[str, float] = {}
        if violation:
            for player in coalition_players:
                idx = index_of[player]
                without_mask = mask & ~(1 << idx)
                v_without = value_of(without_mask)
                marginal = (v_s - v_without) - phi.get(player, 0.0)
                marginals[player] = marginal

        coalitions.append(
            CoreViolation(
                mask=mask,
                coalition=coalition_players,
                v_s=v_s,
                phi_s=phi_s,
                deficit=deficit,
                deficit_share=deficit_share,
                size=size,
                violation=violation,
                marginals=marginals,
            )
        )

    coalitions.sort(key=lambda item: item.deficit, reverse=True)
    return CoreCheckResult(
        efficient=efficient,
        total_phi=total_phi,
        grand_value=grand_value,
        coalitions=coalitions,
        sampled=sampled,
    )


def core_check(
    phi: Dict[str, float],
    players: Sequence[str],
    companies: Sequence[Company],
    params: Parameters,
) -> bool:
    """Return True if the Shapley point lies in the core."""

    result = core_diagnostics(phi, players, companies, params)
    return result.efficient and not any(v.violation for v in result.coalitions)
