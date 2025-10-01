"""Cooperation analysis page with Shapley value computation."""

from __future__ import annotations

from typing import List

import dash
from dash import Input, Output, State, callback, dcc, dash_table, html

from ..logic import coalition_savings, core_check, expected_budget, shapley_values


dash.register_page(__name__, path="/coop", name="Кооперация и Шепли")


layout = html.Div(
    [
        html.Div(
            [
                html.H2("Кооперация и распределение экономии"),
                html.P(
                    "На этой странице оцениваем экономию большой коалиции и распределение по Шепли.",
                    className="note",
                ),
                html.Div(
                    [
                        dcc.Dropdown(id="coop-selection", multi=True, className="flex-grow"),
                        html.Button(
                            "Рассчитать",
                            id="btn-calc-coop",
                            className="nav-link",
                            n_clicks=0,
                        ),
                    ],
                    className="flex-row",
                ),
                html.Div(id="coop-summary", className="coop-summary", style={"marginTop": "12px"}),
                dash_table.DataTable(
                    id="coop-table",
                    columns=[
                        {"name": "Игрок", "id": "player"},
                        {"name": "Solo бюджет, млн $", "id": "solo"},
                        {"name": "Доля по Шепли, млн $", "id": "shapley"},
                        {"name": "Новый бюджет, млн $", "id": "new_budget"},
                    ],
                    style_cell={"fontSize": 13},
                    style_header={"fontWeight": "600", "color": "#111827"},
                    style_table={"marginTop": "12px"},
                ),
            ],
            className="section-card",
        ),
    ]
)


@callback(
    Output("coop-selection", "options"),
    Input("companies-store", "data"),
)
def populate_options(companies):
    return [
        {"label": company["name"], "value": company["name"]}
        for company in (companies or [])
    ]


@callback(
    Output("coop-table", "data"),
    Output("coop-summary", "children"),
    Input("btn-calc-coop", "n_clicks"),
    State("coop-selection", "value"),
    State("companies-store", "data"),
    State("parameters-store", "data"),
    prevent_initial_call=True,
)
def compute_cooperation(_, selected, companies, params):
    selected = selected or []
    companies = companies or []
    params = params or {}

    if len(selected) < 2 or len(selected) > 7:
        return [], html.Span(
            "Выберите от 2 до 7 компаний для расчёта Шепли (n! растёт быстро).",
            className="warn",
        )

    phi = shapley_values(selected, companies, params)
    savings = coalition_savings(selected, companies, params)
    is_core = core_check(phi, selected, companies, params)

    rows: List[dict] = []
    for player in selected:
        company = next((row for row in companies if row["name"] == player), None)
        if not company:
            continue
        solo_budget = expected_budget(company, params)
        share = phi.get(player, 0.0)
        rows.append(
            {
                "player": player,
                "solo": int(round(solo_budget)),
                "shapley": int(round(share)),
                "new_budget": int(round(solo_budget - share)),
            }
        )

    summary = html.Span(
        [
            f"Экономия большой коалиции v(N): {int(round(savings)):,} млн $. ".replace(",", " "),
            html.Span(
                "Шепли в ядре" if is_core else "Шепли вне ядра",
                className="ok" if is_core else "warn",
            ),
        ]
    )

    return rows, summary
