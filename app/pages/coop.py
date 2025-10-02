"""Cooperation analysis page with Shapley value computation."""

from __future__ import annotations

import math
from dataclasses import asdict
from typing import List, Optional, Sequence, Union

import dash
from dash import Input, Output, State, callback, dcc, dash_table, html
from dash.exceptions import PreventUpdate

from ..logic import (
    coalition_savings,
    core_diagnostics,
    expected_budget,
    shapley_values,
)


dash.register_page(__name__, path="/coop", name="Кооперация и Шепли")


CORE_TABLE_COLUMNS = [
    {"name": "S (коалиция)", "id": "coalition"},
    {"name": "|S|", "id": "size"},
    {"name": "v(S)", "id": "vS"},
    {"name": "Σφ(S)", "id": "phiS"},
    {"name": "Δ(S)", "id": "deficit"},
    {"name": "Δ(S)/v(S)", "id": "deficitShare"},
    {"name": "mask", "id": "mask"},
    {"name": "violation", "id": "violation"},
    {"name": "group", "id": "is_group"},
]


layout = html.Div(
    [
        dcc.Store(id="coop-analysis-store"),
        html.Div(
            [
                html.H2("Кооперация и распределение экономии"),
                html.P(
                    "На этой странице оцениваем экономию большой коалиции, распределение по Шепли и проверяем ядро.",
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
                dcc.Tabs(
                    id="coop-tabs",
                    value="distribution",
                    children=[
                        dcc.Tab(
                            label="Распределение",
                            value="distribution",
                            children=[
                                html.Div(
                                    id="coop-summary",
                                    className="coop-summary",
                                    style={"marginTop": "12px"},
                                ),
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
                        ),
                        dcc.Tab(
                            label="Ядро",
                            value="core",
                            children=[
                                html.Div(
                                    [
                                        html.Button(
                                            "Проверить ядро",
                                            id="btn-check-core",
                                            className="nav-link",
                                            n_clicks=0,
                                        ),
                                        html.Button(
                                            "Экспорт CSV",
                                            id="btn-core-download",
                                            className="nav-link",
                                            n_clicks=0,
                                            style={"marginLeft": "12px"},
                                        ),
                                        html.Span(
                                            "Нажмите «Проверить ядро» — результаты будут обновляться автоматически.",
                                            id="core-status",
                                            className="note",
                                            style={"marginLeft": "12px"},
                                        ),
                                    ],
                                    className="flex-row",
                                    style={"alignItems": "center", "marginTop": "12px"},
                                ),
                                html.Div(
                                    [
                                        dcc.Checklist(
                                            id="core-options",
                                            options=[
                                                {"label": "Показывать только нарушения", "value": "only"},
                                                {"label": "Группировать по размеру |S|", "value": "group"},
                                            ],
                                            value=["only"],
                                            inline=True,
                                            className="core-filter-checklist",
                                        ),
                                        dcc.Dropdown(
                                            id="core-rmax",
                                            placeholder="Макс. размер S",
                                            clearable=True,
                                            options=[
                                                {"label": str(k), "value": k}
                                                for k in range(1, 11)
                                            ],
                                            style={"width": "200px", "marginLeft": "12px"},
                                        ),
                                        dcc.Input(
                                            id="core-topk",
                                            type="number",
                                            min=5,
                                            max=200,
                                            step=5,
                                            value=20,
                                            debounce=True,
                                            style={"width": "120px", "marginLeft": "12px"},
                                        ),
                                    ],
                                    className="flex-row",
                                    style={"marginTop": "12px", "flexWrap": "wrap"},
                                ),
                                html.Div(id="core-summary", className="coop-summary", style={"marginTop": "12px"}),
                                dash_table.DataTable(
                                    id="core-violations-table",
                                    columns=CORE_TABLE_COLUMNS,
                                    hidden_columns=["mask", "violation", "is_group"],
                                    style_cell={"fontSize": 13},
                                    style_header={"fontWeight": "600", "color": "#111827"},
                                    style_table={"marginTop": "12px"},
                                    sort_action="native",
                                    page_size=20,
                                ),
                                html.Div(id="core-heatmap", className="core-heatmap", style={"marginTop": "16px"}),
                                dcc.Download(id="core-download"),
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
    Output("coop-analysis-store", "data"),
    Input("btn-calc-coop", "n_clicks"),
    Input("parameters-store", "data"),
    State("coop-selection", "value"),
    State("companies-store", "data"),
)
def compute_cooperation(_, params, selected, companies):
    selected = selected or []
    companies = companies or []
    params = params or {}

    if len(selected) < 2 or len(selected) > 7:
        message = html.Span(
            "Выберите от 2 до 7 компаний для расчёта Шепли (n! растёт быстро).",
            className="warn",
        )
        return [], message, None

    phi = shapley_values(selected, companies, params)
    savings = coalition_savings(selected, companies, params)
    diagnostics = core_diagnostics(phi, selected, companies, params)
    is_core = diagnostics.efficient and not any(v.violation for v in diagnostics.coalitions)

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

    core_payload = {
        "players": selected,
        "phi": {player: float(value) for player, value in phi.items()},
        "grand_value": diagnostics.grand_value,
        "total_phi": diagnostics.total_phi,
        "efficient": diagnostics.efficient,
        "sampled": diagnostics.sampled,
        "coalitions": [asdict(item) for item in diagnostics.coalitions],
    }

    return rows, summary, core_payload


def _format_number(value: float) -> str:
    if math.isfinite(value):
        if abs(value) >= 1:
            return f"{value:,.2f}".replace(",", " ")
        return f"{value:.4f}"
    return "—"


def _build_grouped_rows(rows: Sequence[dict]) -> List[dict]:
    grouped: List[dict] = []
    by_size: dict[int, List[dict]] = {}
    for row in rows:
        by_size.setdefault(row["size"], []).append(row)
    for size in sorted(by_size):
        coalition_rows = by_size[size]
        grouped.append(
            {
                "coalition": f"|S| = {size} (коалиций: {len(coalition_rows)})",
                "size": "",
                "vS": "",
                "phiS": "",
                "deficit": "",
                "deficitShare": "",
                "mask": "",
                "violation": False,
                "is_group": True,
            }
        )
        grouped.extend(coalition_rows)
    return grouped


def _build_heatmap(
    players: Sequence[str],
    coalitions: Sequence[dict],
    top_k: int,
) -> Union[html.Table, html.Div]:
    violating = [row for row in coalitions if row.get("violation")]
    if not violating:
        return html.Div("Нарушающие коалиции отсутствуют.", className="note")

    top = violating[: max(1, top_k)]
    header = html.Thead(
        html.Tr(
            [html.Th("S\\i")] + [html.Th(player) for player in players],
            className="core-heatmap-header",
        )
    )

    body_rows: List[html.Tr] = []
    for row in top:
        coalition_players: List[str] = row.get("coalition", [])
        marginals = row.get("marginals", {})
        positive_marginals = [value for value in marginals.values() if value > 0]
        max_margin = max(positive_marginals) if positive_marginals else 0.0
        cells = [html.Td(", ".join(coalition_players) or "—", className="core-heatmap-label")]
        for player in players:
            in_coalition = player in coalition_players
            base_alpha = 0.1 if in_coalition else 0.0
            intensity = 0.0
            if in_coalition and max_margin > 0:
                intensity = max(0.0, marginals.get(player, 0.0)) / max_margin
            alpha = base_alpha + 0.55 * intensity
            style = {
                "backgroundColor": f"rgba(220, 53, 69, {alpha:.2f})" if alpha > 0 else "transparent",
            }
            cells.append(html.Td("" if not in_coalition else "●", style=style))
        body_rows.append(html.Tr(cells))

    return html.Table([header, html.Tbody(body_rows)], className="core-heatmap-table")


def _filter_coalitions(
    payload: dict,
    *,
    r_max: Optional[int],
) -> List[dict]:
    coalitions = payload.get("coalitions") or []
    players = payload.get("players") or []
    n = len(players)
    if not r_max:
        return coalitions
    return [
        row
        for row in coalitions
        if row.get("size") <= r_max or row.get("size") >= n - r_max
    ]


@callback(
    Output("core-summary", "children"),
    Output("core-violations-table", "data"),
    Output("core-violations-table", "style_data_conditional"),
    Output("core-heatmap", "children"),
    Input("btn-check-core", "n_clicks"),
    Input("coop-analysis-store", "data"),
    Input("core-options", "value"),
    Input("core-rmax", "value"),
    Input("core-topk", "value"),
)
def update_core_tab(n_clicks, payload, options, r_max, top_k):
    if not n_clicks:
        raise PreventUpdate
    payload = payload or {}
    players = payload.get("players") or []
    coalitions = payload.get("coalitions") or []
    if len(players) < 2 or not coalitions:
        return (
            html.Span("Нет данных для проверки ядра. Пересчитайте Шепли.", className="warn"),
            [],
            [],
            html.Div("Недостаточно данных.", className="note"),
        )

    options = options or []
    show_only = "only" in options
    group_by = "group" in options
    filtered = _filter_coalitions(payload, r_max=r_max)

    rows: List[dict] = []
    for row in filtered:
        display_row = row.copy()
        deficit_value = float(display_row.get("deficit", 0.0))
        if show_only and deficit_value <= 0:
            continue
        display_row["_deficit_value"] = deficit_value
        display_row["coalition"] = ", ".join(display_row.get("coalition", []))
        display_row["vS"] = _format_number(float(display_row.get("v_s", display_row.get("vS", 0.0))))
        display_row["phiS"] = _format_number(float(display_row.get("phi_s", display_row.get("phiS", 0.0))))
        display_row["deficit"] = _format_number(deficit_value)
        share = float(display_row.get("deficit_share", display_row.get("deficitShare", 0.0)))
        display_row["deficitShare"] = "—" if not math.isfinite(share) else f"{share * 100:.1f}%"
        display_row.setdefault("violation", bool(display_row.get("violation")))
        display_row.setdefault("mask", display_row.get("mask", ""))
        display_row.setdefault("is_group", False)
        display_row.pop("marginals", None)
        rows.append(display_row)

    rows.sort(key=lambda item: float(item.get("_deficit_value", 0.0)), reverse=True)
    data_rows = _build_grouped_rows(rows) if group_by else rows
    for item in data_rows:
        item.pop("_deficit_value", None)

    style_data_conditional = [
        {
            "if": {"filter_query": "{violation} = True"},
            "backgroundColor": "rgba(220, 53, 69, 0.12)",
        },
        {
            "if": {"filter_query": "{is_group} = True"},
            "fontWeight": "600",
            "backgroundColor": "rgba(15, 23, 42, 0.05)",
        },
    ]

    top_k = max(5, int(top_k or 20))
    # Pass raw coalition data (without formatting) for the heatmap.
    heatmap = _build_heatmap(players, filtered, top_k)

    violations = [row for row in filtered if row.get("violation")]
    total_deficit = sum(float(row.get("deficit", 0.0)) for row in violations if float(row.get("deficit", 0.0)) > 0)
    summary_parts = [
        f"Σφ = {_format_number(payload.get('total_phi', 0.0))}",
        f"v(N) = {_format_number(payload.get('grand_value', 0.0))}",
    ]
    if payload.get("efficient"):
        summary_parts.append("эффективность выполнена")
    else:
        summary_parts.append("эффективность нарушена")
    summary_parts.append(f"Нарушений: {len(violations)}")
    if total_deficit > 0:
        summary_parts.append(f"ΣΔ(S) = {_format_number(total_deficit)}")
    if payload.get("sampled"):
        summary_parts.append("режим семплирования")

    summary = html.Span("; ".join(summary_parts), className="note")

    return summary, data_rows, style_data_conditional, heatmap


@callback(
    Output("core-download", "data"),
    Input("btn-core-download", "n_clicks"),
    State("core-violations-table", "data"),
    prevent_initial_call=True,
)
def export_core_csv(n_clicks, table_data):
    if not n_clicks:
        raise PreventUpdate
    table_data = table_data or []
    rows = [row for row in table_data if not row.get("is_group")]
    if not rows:
        raise PreventUpdate

    headers = ["S", "|S|", "v(S)", "Σφ(S)", "Δ(S)", "Δ(S)/v(S)"]
    lines = [";".join(headers)]
    for row in rows:
        lines.append(
            ";".join(
                [
                    row.get("coalition", ""),
                    str(row.get("size", "")),
                    str(row.get("vS", "")),
                    str(row.get("phiS", "")),
                    str(row.get("deficit", "")),
                    str(row.get("deficitShare", "")),
                ]
            )
        )

    csv_data = "\n".join(lines)
    return dict(content=csv_data, filename="core_violations.csv")
