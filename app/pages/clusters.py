"""Кластеризация портфелей по похожим метрикам."""

from __future__ import annotations

import json
import math
from typing import Dict, Iterable, List, Mapping, Sequence, TypedDict

import dash
from dash import Input, Output, State, callback, dcc, dash_table, html
import plotly.express as px

from ..data import MIN_TOTAL_PROJECTS
from ..logic import compute_company_metrics


dash.register_page(__name__, path="/clusters", name="Кластеры по схожести")


class ThresholdSpec(TypedDict):
    field: str
    label: str
    minimum: float
    maximum: float
    step: float
    format: str


THRESHOLDS: Sequence[ThresholdSpec] = (
    {
        "field": "approvals_tol",
        "label": "Допустимая разница по одобрениям",
        "minimum": 0.0,
        "maximum": 8.0,
        "step": 0.1,
        "format": "{:.1f}",
    },
    {
        "field": "budget_tol",
        "label": "Допустимая разница по бюджетам (млн $)",
        "minimum": 0,
        "maximum": 600,
        "step": 10,
        "format": "{:.0f}",
    },
    {
        "field": "unit_cost_tol",
        "label": "Разница по стоимости одного одобрения (млн $)",
        "minimum": 0,
        "maximum": 400,
        "step": 10,
        "format": "{:.0f}",
    },
)


def _filter_small_companies(companies: Iterable[Mapping[str, object]] | None) -> List[Dict[str, float]]:
    companies = list(companies or [])
    filtered: List[Dict[str, float]] = []
    for company in companies:
        total = float(company.get("n_I", 0)) + float(company.get("n_II", 0)) + float(company.get("n_III", 0))
        if total >= MIN_TOTAL_PROJECTS:
            filtered.append(
                {
                    "name": str(company.get("name", "")),
                    "n_I": float(company.get("n_I", 0)),
                    "n_II": float(company.get("n_II", 0)),
                    "n_III": float(company.get("n_III", 0)),
                }
            )
    return filtered


def _build_slider(threshold: ThresholdSpec) -> html.Div:
    slider_id = f"cluster-{threshold['field']}"
    marks = {
        threshold["minimum"]: threshold["format"].format(threshold["minimum"]),
        threshold["maximum"]: threshold["format"].format(threshold["maximum"]),
    }
    return html.Div(
        [
            html.Div(threshold["label"], className="slider-label"),
            dcc.Slider(
                id=slider_id,
                min=threshold["minimum"],
                max=threshold["maximum"],
                step=threshold["step"],
                marks=marks,
                tooltip={"placement": "bottom", "always_visible": True},
            ),
        ],
        className="slider-card",
    )


def _default_thresholds() -> Dict[str, float]:
    values: Dict[str, float] = {}
    for threshold in THRESHOLDS:
        midpoint = (threshold["minimum"] + threshold["maximum"]) / 2
        values[threshold["field"]] = round(midpoint, 2)
    return values


def _is_unit_cost_valid(a: Mapping[str, float], b: Mapping[str, float]) -> bool:
    return math.isfinite(a.get("unit_cost", math.nan)) and math.isfinite(b.get("unit_cost", math.nan))


def _is_similar(a: Mapping[str, float], b: Mapping[str, float], thresholds: Mapping[str, float]) -> bool:
    if abs(a.get("approvals", 0.0) - b.get("approvals", 0.0)) > thresholds.get("approvals_tol", 0.0):
        return False
    if abs(a.get("budget", 0.0) - b.get("budget", 0.0)) > thresholds.get("budget_tol", 0.0):
        return False
    if _is_unit_cost_valid(a, b):
        return abs(a.get("unit_cost", 0.0) - b.get("unit_cost", 0.0)) <= thresholds.get("unit_cost_tol", 0.0)
    return True


def _build_union_find(names: Sequence[str]):
    parent = {name: name for name in names}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str):
        root_a, root_b = find(a), find(b)
        if root_a != root_b:
            parent[root_b] = root_a

    return parent, find, union


def _cluster_metrics(metrics: Sequence[Mapping[str, float]], thresholds: Mapping[str, float]):
    parent, find, union = _build_union_find([item["name"] for item in metrics])
    pair_rows: List[Dict[str, object]] = []

    for i, left in enumerate(metrics):
        for right in metrics[i + 1 :]:
            similar = _is_similar(left, right, thresholds)
            diff_approvals = abs(left.get("approvals", 0.0) - right.get("approvals", 0.0))
            diff_budget = abs(left.get("budget", 0.0) - right.get("budget", 0.0))
            unit_cost_left = left.get("unit_cost", math.nan)
            unit_cost_right = right.get("unit_cost", math.nan)
            if math.isfinite(unit_cost_left) and math.isfinite(unit_cost_right):
                diff_unit = abs(unit_cost_left - unit_cost_right)
            else:
                diff_unit = math.nan

            pair_rows.append(
                {
                    "pair": f"{left['name']} / {right['name']}",
                    "diff_approvals": round(diff_approvals, 2),
                    "diff_budget": round(diff_budget, 2),
                    "diff_unit_cost": None if math.isnan(diff_unit) else round(diff_unit, 2),
                    "similar": "Да" if similar else "Нет",
                }
            )

            if similar:
                union(left["name"], right["name"])

    clusters: Dict[str, List[str]] = {}
    for name in parent:
        root = find(name)
        clusters.setdefault(root, []).append(name)

    ordered_clusters = [sorted(names) for names in clusters.values()]
    ordered_clusters.sort(key=lambda item: (-len(item), item[0] if item else ""))

    cluster_lookup: Dict[str, str] = {}
    for idx, names in enumerate(ordered_clusters, start=1):
        label = f"Кластер {idx}"
        for name in names:
            cluster_lookup[name] = label

    return ordered_clusters, pair_rows, cluster_lookup


layout = html.Div(
    [
        dcc.Store(id="cluster-thresholds-store", data=_default_thresholds()),
        dcc.Download(id="cluster-download"),
        html.Div(
            [
                html.H2("Схожесть портфелей и кластеризация"),
                html.P(
                    "Подберите пороги схожести по ключевым метрикам и изучите, как компании объединяются в кластеры.",
                    className="note",
                ),
                dcc.Tabs(
                    id="cluster-tabs",
                    value="thresholds",
                    children=[
                        dcc.Tab(
                            label="Пороговые значения",
                            value="thresholds",
                            children=[
                                html.Div(
                                    [
                                        html.Div(
                                            [_build_slider(threshold) for threshold in THRESHOLDS],
                                            className="controls-stack",
                                        ),
                                        html.Div(
                                            [
                                                html.Button(
                                                    "Сбросить к рекомендуемым",
                                                    id="btn-reset-thresholds",
                                                    className="nav-link",
                                                    n_clicks=0,
                                                ),
                                                html.Button(
                                                    "Выгрузить параметры для парсера",
                                                    id="btn-download-thresholds",
                                                    className="nav-link",
                                                    n_clicks=0,
                                                ),
                                            ],
                                            className="flex-row",
                                            style={"marginTop": "12px", "gap": "12px", "flexWrap": "wrap"},
                                        ),
                                        html.P(
                                            "Настройки порогов можно выгрузить и передать в парсер для офлайн-оценки схожести.",
                                            className="note small",
                                            style={"marginTop": "6px"},
                                        ),
                                    ],
                                    className="section-card",
                                ),
                            ],
                        ),
                        dcc.Tab(
                            label="Результаты и визуализация",
                            value="results",
                            children=[
                                html.Div(
                                    [
                                        html.Div(id="cluster-summary", className="coop-summary"),
                                        html.Div(id="cluster-list", className="note", style={"marginTop": "12px"}),
                                        dash_table.DataTable(
                                            id="cluster-pairs",
                                            columns=[
                                                {"name": "Пара", "id": "pair"},
                                                {"name": "Δ одобрения", "id": "diff_approvals"},
                                                {"name": "Δ бюджет", "id": "diff_budget"},
                                                {"name": "Δ стоимость/одобр.", "id": "diff_unit_cost"},
                                                {"name": "Схожи?", "id": "similar"},
                                            ],
                                            style_cell={"fontSize": 13},
                                            style_header={"fontWeight": "600", "color": "#111827"},
                                            style_table={"marginTop": "12px"},
                                            page_size=15,
                                        ),
                                        dcc.Graph(id="cluster-graph", style={"marginTop": "18px"}),
                                    ],
                                    className="section-card",
                                ),
                            ],
                        ),
                    ],
                    className="coop-tabs",
                ),
            ],
            className="section-card",
        ),
    ]
)


@callback(
    Output("cluster-thresholds-store", "data"),
    [Input(f"cluster-{threshold['field']}", "value") for threshold in THRESHOLDS]
    + [Input("btn-reset-thresholds", "n_clicks")],
    State("cluster-thresholds-store", "data"),
)
def sync_threshold_store(*args):
    values = args[: len(THRESHOLDS)]
    reset_clicks = args[len(THRESHOLDS)] if len(args) > len(THRESHOLDS) else 0
    current = args[-1] if args else {}

    if reset_clicks and dash.callback_context.triggered_id == "btn-reset-thresholds":
        return _default_thresholds()

    data = current.copy() if isinstance(current, dict) else {}
    for threshold, value in zip(THRESHOLDS, values):
        if value is not None:
            data[threshold["field"]] = float(value)
    return data


@callback(
    [Output(f"cluster-{threshold['field']}", "value") for threshold in THRESHOLDS],
    Input("cluster-thresholds-store", "data"),
)
def hydrate_sliders(data):
    data = data or _default_thresholds()
    return [data.get(threshold["field"], threshold["minimum"]) for threshold in THRESHOLDS]


@callback(
    Output("cluster-summary", "children"),
    Output("cluster-list", "children"),
    Output("cluster-pairs", "data"),
    Output("cluster-graph", "figure"),
    Input("companies-store", "data"),
    Input("parameters-store", "data"),
    Input("cluster-thresholds-store", "data"),
)
def update_clusters(companies, params, thresholds):
    companies = _filter_small_companies(companies)
    if not companies:
        empty_fig = px.scatter(title="Недостаточно данных для визуализации")
        return (
            html.Span("Загрузите или добавьте компании для расчёта кластеров.", className="note"),
            html.Ul([html.Li("Нет доступных компаний")]),
            [],
            empty_fig,
        )

    params = params or {}
    thresholds = thresholds or _default_thresholds()

    metrics = compute_company_metrics(companies, params)
    for item in metrics:
        item["total_projects"] = item.get("n_I", 0) + item.get("n_II", 0) + item.get("n_III", 0)

    clusters, pair_rows, cluster_lookup = _cluster_metrics(metrics, thresholds)

    if not clusters:
        empty_fig = px.scatter(title="Кластеры не найдены")
        return (
            html.Span("Кластеры не найдены.", className="warn"),
            html.Ul([html.Li("Нет доступных компаний")]),
            pair_rows,
            empty_fig,
        )

    cluster_items = [html.Li(", ".join(cluster)) for cluster in clusters]
    summary = html.Span(
        [
            f"Кластеров: {len(clusters)}. ",
            f"Δ одобрения ≤ {thresholds.get('approvals_tol', 0)}; ",
            f"Δ бюджета ≤ {thresholds.get('budget_tol', 0)}; ",
            f"Δ стоимости ≤ {thresholds.get('unit_cost_tol', 0)}.",
        ]
    )

    graph_data = []
    for item in metrics:
        enriched = item.copy()
        enriched["cluster"] = cluster_lookup.get(item["name"], "Кластер ?")
        graph_data.append(enriched)

    fig = px.scatter(
        graph_data,
        x="approvals",
        y="budget",
        color="cluster",
        hover_name="name",
        size="total_projects",
        labels={"approvals": "Ожидаемые одобрения", "budget": "Бюджет (млн $)"},
    )
    fig.update_layout(template="plotly_white", height=520, margin=dict(l=20, r=20, t=50, b=50))

    return summary, html.Ul(cluster_items), pair_rows, fig


@callback(
    Output("cluster-download", "data"),
    Input("btn-download-thresholds", "n_clicks"),
    State("cluster-thresholds-store", "data"),
    State("companies-store", "data"),
    State("parameters-store", "data"),
    prevent_initial_call=True,
)
def download_thresholds(n_clicks, thresholds, companies, params):
    thresholds = thresholds or _default_thresholds()
    companies = _filter_small_companies(companies)
    params = params or {}
    metrics = compute_company_metrics(companies, params)

    payload = {
        "thresholds": thresholds,
        "companies": [
            {
                "name": item["name"],
                "approvals": item.get("approvals", 0.0),
                "budget": item.get("budget", 0.0),
                "unit_cost": item.get("unit_cost", math.nan),
            }
            for item in metrics
        ],
    }

    content = json.dumps(payload, ensure_ascii=False, indent=2)
    return dict(content=content, filename="cluster_thresholds.json")
