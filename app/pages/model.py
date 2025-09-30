"""Main modelling page with parameters, portfolios and visualisations."""

from __future__ import annotations

import math
from typing import Dict, List

from dash import Input, Output, State, callback, ctx, dcc, html
import dash_table
import plotly.express as px

from ..data import PARAMETER_PRESETS
from ..logic import compute_company_metrics


dash.register_page(__name__, path="/", name="Модель и портфели")

PARAMETERS: List[Dict[str, object]] = [
    {
        "field": "p1",
        "label": "Вероятность успеха фазы I",
        "min": 0,
        "max": 1,
        "step": 0.01,
        "format": "{:.2f}",
    },
    {
        "field": "p2",
        "label": "Вероятность успеха фазы II",
        "min": 0,
        "max": 1,
        "step": 0.01,
        "format": "{:.2f}",
    },
    {
        "field": "p3",
        "label": "Вероятность успеха фазы III",
        "min": 0,
        "max": 1,
        "step": 0.01,
        "format": "{:.2f}",
    },
    {
        "field": "C_I",
        "label": "Стоимость фазы I (млн $)",
        "min": 0,
        "max": 100,
        "step": 1,
        "format": "{:.0f} млн $",
    },
    {
        "field": "C_II",
        "label": "Стоимость фазы II (млн $)",
        "min": 0,
        "max": 200,
        "step": 1,
        "format": "{:.0f} млн $",
    },
    {
        "field": "C_III",
        "label": "Стоимость фазы III (млн $)",
        "min": 0,
        "max": 800,
        "step": 5,
        "format": "{:.0f} млн $",
    },
    {
        "field": "C_REG",
        "label": "Регистрация (млн $)",
        "min": 0,
        "max": 20,
        "step": 1,
        "format": "{:.0f} млн $",
    },
    {
        "field": "coop_c3_reduction",
        "label": "Кооперация: снижение CIII (%)",
        "min": 0,
        "max": 60,
        "step": 1,
        "format": "{:.0f}%",
    },
    {
        "field": "coop_dp3",
        "label": "Кооперация: прирост p3",
        "min": 0,
        "max": 0.2,
        "step": 0.01,
        "format": "{:.2f}",
    },
    {
        "field": "coop_p3_cap",
        "label": "Ограничение p3 в кооперации (max)",
        "min": 0.5,
        "max": 0.95,
        "step": 0.01,
        "format": "{:.2f}",
    },
]


layout = html.Div(
    [
        html.Div(
            [
                html.H2("1) Параметры модели"),
                html.Div(
                    [
                        html.Div(
                            [
                                html.Label(param["label"]),
                                dcc.Slider(
                                    id=f"slider-{param['field']}",
                                    min=param["min"],
                                    max=param["max"],
                                    step=param["step"],
                                ),
                                html.Div(id=f"display-{param['field']}", className="note"),
                            ],
                            className="section-card",
                        )
                        for param in PARAMETERS
                    ],
                    className="controls-grid",
                ),
                html.Div(
                    [
                        html.Button(
                            "Заполнить параметрами из базы (средние оценки)",
                            id="btn-fill-avg",
                            className="nav-link",
                            n_clicks=0,
                        ),
                        html.Button(
                            "Российские ориентиры (дешевле фаза III)",
                            id="btn-fill-ru",
                            className="nav-link",
                            n_clicks=0,
                        ),
                    ],
                    className="flex-row",
                    style={"marginTop": "12px"},
                ),
                html.P(
                    "Перетаскивайте ползунки — таблица и графики пересчитываются мгновенно.",
                    className="note small",
                ),
            ],
            className="section-card",
        ),
        html.Div(
            [
                html.H2("2) Компании и портфели"),
                dash_table.DataTable(
                    id="companies-table",
                    columns=[
                        {"name": "Компания", "id": "name", "presentation": "markdown", "editable": False},
                        {"name": "Фаза I", "id": "n_I", "type": "numeric", "editable": True},
                        {"name": "Фаза II", "id": "n_II", "type": "numeric", "editable": True},
                        {"name": "Фаза III", "id": "n_III", "type": "numeric", "editable": True},
                        {"name": "Ожидаемые одобрения", "id": "approvals", "editable": False},
                        {"name": "Ожидаемый бюджет, млн $", "id": "budget", "editable": False},
                        {"name": "Средняя стоимость за одобрение, млн $", "id": "unit_cost", "editable": False},
                    ],
                    editable=True,
                    style_table={"overflowX": "auto"},
                    style_cell={"fontSize": 13},
                    style_header={"fontWeight": "600"},
                ),
                html.Div(
                    [
                        dcc.Input(
                            id="input-name",
                            placeholder="Новая компания",
                        ),
                        dcc.Input(
                            id="input-nI",
                            type="number",
                            min=0,
                            placeholder="I",
                        ),
                        dcc.Input(
                            id="input-nII",
                            type="number",
                            min=0,
                            placeholder="II",
                        ),
                        dcc.Input(
                            id="input-nIII",
                            type="number",
                            min=0,
                            placeholder="III",
                        ),
                        html.Button("Добавить", id="btn-add-company", className="nav-link", n_clicks=0),
                    ],
                    className="flex-row",
                    style={"marginTop": "12px"},
                ),
                html.P(
                    "Начальный набор: Pfizer, BIOCAD, Generium, R-Pharm, Pharmstandard, Geropharm, Petrovax, Valenta, Nanolek, ChemRar.",
                    className="note small",
                ),
            ],
            className="section-card",
            style={"marginTop": "20px"},
        ),
        html.Div(
            [
                html.H2("3) Графики"),
                html.Div(
                    [
                        dcc.Graph(id="graph-approvals"),
                        dcc.Graph(id="graph-budget"),
                        dcc.Graph(id="graph-unit"),
                    ],
                    className="graph-grid",
                ),
            ],
            className="section-card",
            style={"marginTop": "20px"},
        ),
        html.Div(
            [
                html.H2("4) Краткие выводы"),
                html.Div(
                    [
                        html.Div(
                            [
                                html.Div("Всего компаний", className="note small"),
                                html.Div(id="kpi-companies", className="value"),
                            ],
                            className="kpi",
                        ),
                        html.Div(
                            [
                                html.Div("Σ ожидаемых одобрений", className="note small"),
                                html.Div(id="kpi-approvals", className="value"),
                            ],
                            className="kpi",
                        ),
                        html.Div(
                            [
                                html.Div("Σ бюджета (млн $)", className="note small"),
                                html.Div(id="kpi-budget", className="value"),
                            ],
                            className="kpi",
                        ),
                    ],
                    className="kpi-grid",
                ),
            ],
            className="section-card",
            style={"marginTop": "20px"},
        ),
    ]
)


@callback(
    Output("parameters-store", "data"),
    [
        Input(f"slider-{param['field']}", "value")
        for param in PARAMETERS
    ]
    + [Input("btn-fill-avg", "n_clicks"), Input("btn-fill-ru", "n_clicks")],
    State("parameters-store", "data"),
)
def update_parameters(*args):
    slider_values = args[: len(PARAMETERS)]
    current = args[-1] if args else {}

    triggered = ctx.triggered_id

    if triggered == "btn-fill-avg":
        return PARAMETER_PRESETS["avg"].copy()
    if triggered == "btn-fill-ru":
        return PARAMETER_PRESETS["ru"].copy()

    params = current.copy() if isinstance(current, dict) else {}
    for param, value in zip(PARAMETERS, slider_values):
        if value is not None:
            params[param["field"]] = float(value)
    return params


@callback(
    [Output(f"slider-{param['field']}", "value") for param in PARAMETERS]
    + [Output(f"display-{param['field']}", "children") for param in PARAMETERS],
    Input("parameters-store", "data"),
)
def sync_sliders(params):
    params = params or {}
    values = []
    displays = []
    for param in PARAMETERS:
        value = params.get(param["field"], param["min"])
        values.append(value)
        displays.append(param["format"].format(value))
    return values + displays


@callback(
    Output("companies-store", "data"),
    Output("input-name", "value"),
    Output("input-nI", "value"),
    Output("input-nII", "value"),
    Output("input-nIII", "value"),
    Input("companies-table", "data"),
    Input("btn-add-company", "n_clicks"),
    State("input-name", "value"),
    State("input-nI", "value"),
    State("input-nII", "value"),
    State("input-nIII", "value"),
    State("companies-store", "data"),
    prevent_initial_call=True,
)
def update_companies(table_data, add_clicks, name, n_i, n_ii, n_iii, current):
    triggered = ctx.triggered_id

    if triggered == "btn-add-company":
        new_entry = {
            "name": name.strip() if name else "NewCo",
            "n_I": max(0, int(n_i or 0)),
            "n_II": max(0, int(n_ii or 0)),
            "n_III": max(0, int(n_iii or 0)),
        }
        updated = (current or []) + [new_entry]
        return updated, "", None, None, None

    if triggered == "companies-table" and table_data is not None:
        cleaned = []
        for row in table_data:
            cleaned.append(
                {
                    "name": row.get("name", ""),
                    "n_I": max(0, int(row.get("n_I", 0) or 0)),
                    "n_II": max(0, int(row.get("n_II", 0) or 0)),
                    "n_III": max(0, int(row.get("n_III", 0) or 0)),
                }
            )
        return cleaned, dash.no_update, dash.no_update, dash.no_update, dash.no_update

    return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update


@callback(
    Output("companies-table", "data"),
    Output("graph-approvals", "figure"),
    Output("graph-budget", "figure"),
    Output("graph-unit", "figure"),
    Output("kpi-companies", "children"),
    Output("kpi-approvals", "children"),
    Output("kpi-budget", "children"),
    Input("companies-store", "data"),
    Input("parameters-store", "data"),
)
def refresh_metrics(companies, params):
    companies = companies or []
    params = params or {}
    metrics = compute_company_metrics(companies, params)

    table_data = []
    approvals_sum = 0.0
    budget_sum = 0.0

    for row in metrics:
        approvals_sum += row["approvals"]
        budget_sum += row["budget"]
        table_data.append(
            {
                **row,
                "approvals": round(row["approvals"], 2),
                "budget": round(row["budget"], 2),
                "unit_cost": round(row["unit_cost"], 2) if not math.isnan(row["unit_cost"]) else None,
            }
        )

    figures = []
    for column, title in [
        ("approvals", "Ожидаемые одобрения"),
        ("budget", "Ожидаемый бюджет (млн $)"),
        ("unit_cost", "Средняя стоимость / одобрение (млн $)"),
    ]:
        fig = px.bar(
            metrics,
            x=column,
            y="name",
            orientation="h",
            labels={"x": title, "y": "Компания"},
        )
        fig.update_layout(margin=dict(l=10, r=10, t=30, b=10), height=320)
        figures.append(fig)

    approvals_fmt = f"{approvals_sum:,.2f}".replace(",", " ")
    budget_fmt = f"{budget_sum:,.2f}".replace(",", " ")

    return (
        table_data,
        figures[0],
        figures[1],
        figures[2],
        str(len(metrics)),
        approvals_fmt,
        budget_fmt,
    )
