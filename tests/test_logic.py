"""Unit tests for the cooperative R&D logic functions."""

from app.logic import (
    coalition_savings,
    compute_company_metrics,
    core_check,
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


def test_shapley_sums_to_savings():
    params = sample_params()
    companies = sample_companies()
    players = [c["name"] for c in companies]
    phi = shapley_values(players, companies, params)
    savings = coalition_savings(players, companies, params)
    assert round(sum(phi.values()), 6) == round(savings, 6)
    assert core_check(phi, players, companies, params)
