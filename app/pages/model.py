"""Main modelling page with parameters, portfolios and visualisations."""

from __future__ import annotations

import math
from typing import Dict, List

import dash
from dash import Input, Output, State, callback, ctx, dcc, dash_table, html
import plotly.express as px

from ..data import MIN_TOTAL_PROJECTS, PARAMETER_PRESETS
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

PARAMETER_LOOKUP = {param["field"]: param for param in PARAMETERS}

# Настраиваем форматирование подсказок и подписей под минимум/максимум.

PARAMETER_DESCRIPTIONS: Dict[str, str] = {
    "p1": "Вероятность, что проект в фазе I перейдёт дальше. В расчётах ожидаемых одобрений участвует как часть произведения p1*p2*p3 для проектов в фазе I.",
    "p2": "Вероятность успеха фазы II. Для проектов, стартующих во II фазе, ожидаемые одобрения равны n_II * p2 * p3.",
    "p3": "Вероятность успеха фазы III. Для проектов в фазе III вклад в ожидаемые одобрения - n_III * p3, а также p3 используется при расчёте ожидаемых бюджетов.",
    "C_I": "Базовый бюджет фазы I. Ожидаемая стоимость проекта из фазы I складывается как C_I + p1*C_II + p1*p2*C_III + p1*p2*p3*C_REG.",
    "C_II": "Базовый бюджет фазы II. Ожидаемая стоимость проекта из фазы II: C_II + p2*C_III + p2*p3*C_REG.",
    "C_III": "Базовый бюджет фазы III. Для проектов в фазе III ожидаемая стоимость: C_III + p3*C_REG. В кооперации эта величина уменьшается на заданный процент.",
    "C_REG": "Регистрационные расходы, которые добавляются после успешного завершения фазы III с вероятностью p3 (или ограничением в кооперации).",
    "coop_c3_reduction": "Процентное снижение C_III при кооперации. Итоговая стоимость третьей фазы умножается на (1 - снижение/100).",
    "coop_dp3": "Добавка к вероятности успеха фазы III в кооперации. Значение складывается с p3, но ограничивается верхним порогом.",
    "coop_p3_cap": "Максимально допустимое значение p3 при кооперации после учёта прироста coop_dp3.",
}

PHASE_GRID_ORDER: List[Dict[str, object]] = [
    {"field": "p1", "column": 1, "row": 1},
    {"field": "p2", "column": 2, "row": 1},
    {"field": "p3", "column": 3, "row": 1},
    {"field": "C_I", "column": 1, "row": 2},
    {"field": "C_II", "column": 2, "row": 2},
    {"field": "C_III", "column": 3, "row": 2},
    {"field": "C_REG", "column": 4, "row": 2},
]

COOP_FIELDS: List[str] = ["coop_c3_reduction", "coop_dp3", "coop_p3_cap"]


def _mark_label(param: Dict[str, object], value: float) -> str:
    field = param["field"]
    if field in {"C_I", "C_II", "C_III", "C_REG"}:
        return str(int(round(value)))
    return param["format"].format(value)


def _build_slider_card(
    param: Dict[str, object], *, extra_classes: str = "", style: Dict[str, object] | None = None
):
    field = param["field"]
    slider_id = f"slider-{field}"
    tooltip_target = f"tooltip-target-{field}"
    slider = dcc.Slider(
        id=slider_id,
        min=param["min"],
        max=param["max"],
        step=param["step"],
        marks={
            param["min"]: _mark_label(param, param["min"]),
            param["max"]: _mark_label(param, param["max"]),
        },
        tooltip={"placement": "bottom", "always_visible": True},
    )

    tooltip_text = PARAMETER_DESCRIPTIONS.get(field)
    if tooltip_text:
        label_content = html.Span(
            [
                html.Span(param["label"], className="slider-label-text"),
                html.Span("?", id=tooltip_target, className="info-icon", tabIndex=0),
                html.Span(tooltip_text, className="tooltip-popup"),
            ],
            className="slider-label-wrapper",
        )
        header_children = [label_content]
    else:
        header_children = [html.Span(param["label"], className="slider-label")]

    card_children = [
        html.Div(header_children, className="slider-header"),
        slider,
    ]

    classes = "slider-card"
    if extra_classes:
        classes = f"{classes} {extra_classes}"

    return html.Div(card_children, className=classes, style=style or {})


def _build_placeholder_card(column: int) -> html.Div:
    return html.Div(
        className="slider-card slider-card--ghost",
        style={"gridColumn": str(column), "gridRow": "1"},
        **{"aria-hidden": "true"},
    )


def _filter_small_companies(companies: List[Dict[str, object]] | None) -> List[Dict[str, object]]:
    companies = companies or []
    return [
        company
        for company in companies
        if company["n_I"] + company["n_II"] + company["n_III"] >= MIN_TOTAL_PROJECTS
    ]


PHASE_GRID_COMPONENTS = [_build_placeholder_card(column=4)] + [
    _build_slider_card(
        PARAMETER_LOOKUP[item["field"]],
        style={"gridColumn": str(item["column"]), "gridRow": str(item["row"])},
    )
    for item in PHASE_GRID_ORDER
]

COOP_COMPONENTS = [
    _build_slider_card(PARAMETER_LOOKUP[field])
    for field in COOP_FIELDS
]


layout = html.Div(
    [
        html.Div(
            [
                html.H2("1) Параметры модели"),
                html.P(
                    "Настройте вероятности, бюджеты и параметры кооперации перед расчётами.",
                    className="note",
                ),
                html.Div(
                    [
                        html.Div(PHASE_GRID_COMPONENTS, className="phase-grid"),
                        html.Div(COOP_COMPONENTS, className="controls-row coop-row"),
                    ],
                    className="controls-stack",
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
                html.P(
                    "Редактируйте состав портфелей: меняйте числа проектов, переименовывайте и удаляйте компании.",
                    className="note",
                ),
                dash_table.DataTable(
                    id="companies-table",
                    columns=[
                        {"name": "Компания", "id": "name", "editable": True},
                        {"name": "Фаза I", "id": "n_I", "type": "numeric", "editable": True},
                        {"name": "Фаза II", "id": "n_II", "type": "numeric", "editable": True},
                        {"name": "Фаза III", "id": "n_III", "type": "numeric", "editable": True},
                        {"name": "Ожидаемые одобрения", "id": "approvals", "editable": False},
                        {"name": "Ожидаемый бюджет, млн $", "id": "budget", "editable": False},
                        {"name": "Средняя стоимость за одобрение, млн $", "id": "unit_cost", "editable": False},
                    ],
                    editable=True,
                    row_deletable=True,
                    style_table={"overflowX": "auto"},
                    style_cell={"fontSize": 13},
                    style_header={"fontWeight": "600", "color": "#111827"},
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
            ],
            className="section-card",
            style={"marginTop": "20px"},
        ),
        html.Div(
            [
                html.H2("3) Графики"),
                html.P(
                    "Сравните компании по ожидаемым одобрениям, бюджетам и стоимости одного успеха.",
                    className="note",
                ),
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
                html.P(
                    "Набор ключевых показателей помогает быстро оценить масштаб портфеля.",
                    className="note",
                ),
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
    [Output(f"slider-{param['field']}", "value") for param in PARAMETERS],
    Input("parameters-store", "data"),
)
def sync_sliders(params):
    params = params or {}
    values = []
    for param in PARAMETERS:
        value = params.get(param["field"], param["min"])
        values.append(value)
    return values


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
        cleaned_name = (name or "NewCo").strip() or "NewCo"
        new_entry = {
            "name": cleaned_name,
            "n_I": max(0, int(n_i or 0)),
            "n_II": max(0, int(n_ii or 0)),
            "n_III": max(0, int(n_iii or 0)),
        }
        updated = _filter_small_companies((current or []) + [new_entry])
        return updated, "", None, None, None

    if triggered == "companies-table" and table_data is not None:
        cleaned = []
        for row in table_data:
            cleaned.append(
                {
                    "name": (row.get("name") or "").strip() or "Компания",
                    "n_I": max(0, int(row.get("n_I", 0) or 0)),
                    "n_II": max(0, int(row.get("n_II", 0) or 0)),
                    "n_III": max(0, int(row.get("n_III", 0) or 0)),
                }
            )
        filtered = _filter_small_companies(cleaned)
        if filtered == _filter_small_companies(current):
            return (
                dash.no_update,
                dash.no_update,
                dash.no_update,
                dash.no_update,
                dash.no_update,
            )
        return filtered, dash.no_update, dash.no_update, dash.no_update, dash.no_update

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
    companies = _filter_small_companies(companies)
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
                "budget": int(round(row["budget"])),
                "unit_cost": (
                    int(round(row["unit_cost"]))
                    if not math.isnan(row["unit_cost"])
                    else None
                ),
            }
        )

    figures = []
    for column, title in [
        ("approvals", "Ожидаемые одобрения"),
        ("budget", "Ожидаемый бюджет (млн $)"),
        ("unit_cost", "Средняя стоимость / одобрение (млн $)"),
    ]:
        sorted_rows = sorted(
            metrics,
            key=lambda row: (
                row[column]
                if row[column] is not None and not math.isnan(row[column])
                else float("-inf")
            ),
            reverse=True,
        )
        fig = px.bar(
            sorted_rows,
            x=column,
            y="name",
            orientation="h",
            labels={"x": title, "y": "Компания"},
        )
        fig.update_layout(
            template="plotly_white",
            margin=dict(l=20, r=20, t=50, b=90),
            height=380,
        )
        fig.update_xaxes(title_text=title, automargin=True)
        fig.update_yaxes(title_text="Компания", automargin=True)
        if column == "unit_cost":
            values = [
                row[column]
                for row in sorted_rows
                if row[column] is not None and not math.isnan(row[column])
            ]
            if values:
                upper = max(values)
                lower = 700
                if upper <= lower:
                    upper = lower + 100
                fig.update_xaxes(range=[lower, upper * 1.1])
        figures.append(fig)

    approvals_fmt = f"{approvals_sum:,.2f}".replace(",", " ")
    budget_fmt = f"{int(round(budget_sum)):,}".replace(",", " ")

    return (
        table_data,
        figures[0],
        figures[1],
        figures[2],
        str(len(metrics)),
        approvals_fmt,
        budget_fmt,
    )
