"""Unit tests for the cooperative R&D logic functions."""

import math

from app.logic import (
    coalition_savings,
    compute_company_metrics,
    core_check,
    cost_per_project,
    expected_approvals,
    expected_budget,
    shapley_values,
)


def sample_params():
    return {
        "p1": 0.5,
        "p2": 0.4,
        "p3": 0.6,
        "C_I": 10,
        "C_II": 25,
        "C_III": 100,
        "C_REG": 5,
        "coop_c3_reduction": 20,
        "coop_dp3": 0.05,
        "coop_p3_cap": 0.8,
    }


def sample_zero_effect_params():
    params = sample_params()
    params.update({"coop_dp3": 0.0, "coop_p3_cap": 1.0, "coop_c3_reduction": 0.0})
    return params


def sample_companies():
    return [
        {"name": "A", "n_I": 4, "n_II": 3, "n_III": 2},
        {"name": "B", "n_I": 2, "n_II": 1, "n_III": 1},
    ]


def test_expected_values():
    params = sample_params()
    company = sample_companies()[0]
    approvals = expected_approvals(company, params)
    budget = expected_budget(company, params)

    assert round(approvals, 4) == 2.4
    assert round(budget, 2) == 577.00


def test_metrics_consistency():
    params = sample_params()
    companies = sample_companies()
    metrics = compute_company_metrics(companies, params)
    assert len(metrics) == len(companies)
    assert metrics[0]["name"] == "A"
    assert metrics[1]["approvals"] > 0


def test_cost_per_project_matches_manual_formula():
    params = sample_params()
    p1, p2, p3 = params["p1"], params["p2"], params["p3"]
    c_i, c_ii, c_iii, c_reg = (
        params["C_I"],
        params["C_II"],
        params["C_III"],
        params["C_REG"],
    )

    manual_i = c_i + p1 * c_ii + (p1 * p2) * c_iii + (p1 * p2 * p3) * c_reg
    manual_ii = c_ii + p2 * c_iii + (p2 * p3) * c_reg
    manual_iii = c_iii + p3 * c_reg

    assert math.isclose(cost_per_project("I", params), manual_i, rel_tol=0, abs_tol=1e-12)
    assert math.isclose(cost_per_project("II", params), manual_ii, rel_tol=0, abs_tol=1e-12)
    assert math.isclose(cost_per_project("III", params), manual_iii, rel_tol=0, abs_tol=1e-12)


def test_expected_approvals_manual_computation():
    params = sample_params()
    company = {"name": "Solo", "n_I": 2, "n_II": 1, "n_III": 1}
    approvals = expected_approvals(company, params)
    manual = (
        2 * (params["p1"] * params["p2"] * params["p3"])
        + 1 * (params["p2"] * params["p3"])
        + 1 * params["p3"]
    )
    assert math.isclose(approvals, manual, rel_tol=0, abs_tol=1e-12)


def test_coalition_savings_zero_when_no_effects():
    params = sample_zero_effect_params()
    companies = sample_companies()
    players = [c["name"] for c in companies]

    solo = sum(expected_budget(c, params) for c in companies)
    coop_budget = expected_budget(
        {"name": "coalition", "n_I": 6, "n_II": 4, "n_III": 3},
        params,
    )

    assert math.isclose(coalition_savings(players, companies, params), 0.0, abs_tol=1e-9)
    assert math.isclose(solo, coop_budget, abs_tol=1e-9)


def test_shapley_values_efficiency_and_symmetry():
    params = sample_params()
    companies = [
        {"name": "A", "n_I": 3, "n_II": 2, "n_III": 1},
        {"name": "B", "n_I": 3, "n_II": 2, "n_III": 1},
    ]
    players = [c["name"] for c in companies]

    phi = shapley_values(players, companies, params)
    grand = coalition_savings(players, companies, params)

    assert math.isclose(sum(phi.values()), grand, rel_tol=1e-9, abs_tol=1e-9)
    assert math.isclose(phi["A"], phi["B"], rel_tol=1e-7, abs_tol=1e-7)


def test_shapley_values_zero_savings():
    params = sample_zero_effect_params()
    companies = sample_companies()
    players = [c["name"] for c in companies]

    phi = shapley_values(players, companies, params)
    assert all(math.isclose(value, 0.0, abs_tol=1e-12) for value in phi.values())
    assert core_check(phi, players, companies, params)


def test_shapley_sums_to_savings():
    params = sample_params()
    companies = sample_companies()
    players = [c["name"] for c in companies]
    phi = shapley_values(players, companies, params)
    savings = coalition_savings(players, companies, params)
    assert round(sum(phi.values()), 6) == round(savings, 6)
    assert core_check(phi, players, companies, params)
