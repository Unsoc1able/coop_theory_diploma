"""Financial analytics page with stacked bar breakdowns of expenses."""

from __future__ import annotations

from typing import List

import dash
from dash import Input, Output, callback, dcc, html
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from ..data import EXPENSES_DATA


dash.register_page(__name__, path="/finance", name="Финансовый обзор")


MONTH_LABELS_RU = {
    1: "Январь",
    2: "Февраль",
    3: "Март",
    4: "Апрель",
    5: "Май",
    6: "Июнь",
    7: "Июль",
    8: "Август",
    9: "Сентябрь",
    10: "Октябрь",
    11: "Ноябрь",
    12: "Декабрь",
}


def _format_month_label(timestamp: pd.Timestamp) -> str:
    month_name = MONTH_LABELS_RU.get(timestamp.month, timestamp.strftime("%B"))
    return f"{month_name} {timestamp.year}"


def _build_dataframe() -> pd.DataFrame:
    if not EXPENSES_DATA:
        return pd.DataFrame(columns=["month", "category", "subcategory", "amount", "month_key", "month_label"])

    frame = pd.DataFrame(EXPENSES_DATA)
    frame["amount"] = frame["amount"].astype(float)
    frame["month"] = pd.to_datetime(frame["month"], format="%Y-%m")
    frame["month_key"] = frame["month"].dt.strftime("%Y-%m")
    frame["month_label"] = frame["month"].apply(_format_month_label)
    return frame


EXPENSES_DF = _build_dataframe()


def _month_options() -> List[dict[str, str]]:
    if EXPENSES_DF.empty:
        return []
    values = (
        EXPENSES_DF.sort_values("month", ascending=False)[["month_key", "month_label"]]
        .drop_duplicates()
        .to_dict("records")
    )
    return [{"value": item["month_key"], "label": item["month_label"]} for item in values]


def _category_options() -> List[str]:
    if EXPENSES_DF.empty:
        return []
    categories = EXPENSES_DF["category"].drop_duplicates()
    return sorted(categories.tolist())


MONTH_OPTIONS = _month_options()
CATEGORY_OPTIONS = _category_options()
DEFAULT_MONTH = MONTH_OPTIONS[0]["value"] if MONTH_OPTIONS else None
DEFAULT_CATEGORY = CATEGORY_OPTIONS[0] if CATEGORY_OPTIONS else None


def _empty_figure(message: str) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        template="plotly_white",
        height=420,
        margin=dict(l=20, r=20, t=40, b=40),
        annotations=[
            {
                "text": message,
                "xref": "paper",
                "yref": "paper",
                "x": 0.5,
                "y": 0.5,
                "showarrow": False,
                "font": {"size": 14},
            }
        ],
    )
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


def _ordered_categories(data: pd.DataFrame) -> List[str]:
    totals = data.groupby("category")["amount"].sum()
    return totals.sort_values(ascending=True).index.tolist()


def _build_overview_figure() -> go.Figure:
    if EXPENSES_DF.empty:
        return _empty_figure("Нет данных о расходах")

    aggregated = (
        EXPENSES_DF.groupby(["category", "subcategory"], as_index=False)["amount"].sum()
    )
    categories = _ordered_categories(aggregated)
    aggregated["category"] = pd.Categorical(aggregated["category"], categories=categories, ordered=True)
    aggregated.sort_values(["category", "subcategory"], inplace=True)

    fig = px.bar(
        aggregated,
        x="amount",
        y="category",
        color="subcategory",
        orientation="h",
        labels={"amount": "Сумма, млн ₽", "category": "Категория", "subcategory": "Подкатегория"},
    )
    fig.update_layout(
        barmode="stack",
        template="plotly_white",
        height=420,
        margin=dict(l=20, r=20, t=50, b=70),
        legend_title_text="",
    )
    fig.update_xaxes(title_text="Сумма, млн ₽")
    fig.update_yaxes(title_text="Категория", automargin=True)
    return fig


layout = html.Div(
    [
        html.Div(
            [
                html.H2("Финансовый обзор расходов"),
                html.P(
                    "Структура расходов по категориям и подкатегориям за последние месяцы.",
                    className="note",
                ),
                dcc.Tabs(
                    id="expenses-tabs",
                    value="categories",
                    children=[
                        dcc.Tab(
                            label="Категории",
                            value="categories",
                            children=[
                                html.Div(
                                    [
                                        html.Div(
                                            [
                                                html.Label("Месяц", className="note small"),
                                                dcc.Dropdown(
                                                    id="expenses-month",
                                                    options=MONTH_OPTIONS,
                                                    value=DEFAULT_MONTH,
                                                    clearable=False,
                                                    placeholder="Выберите месяц",
                                                ),
                                            ],
                                            className="controls-stack",
                                        ),
                                        html.Div(
                                            [
                                                html.Label("Категория для детализации", className="note small"),
                                                dcc.Dropdown(
                                                    id="expenses-category",
                                                    options=[
                                                        {"label": item, "value": item}
                                                        for item in CATEGORY_OPTIONS
                                                    ],
                                                    value=DEFAULT_CATEGORY,
                                                    clearable=False,
                                                    placeholder="Выберите категорию",
                                                ),
                                            ],
                                            className="controls-stack",
                                        ),
                                    ],
                                    className="controls-grid",
                                    style={"marginTop": "12px"},
                                ),
                                html.Div(
                                    [
                                        html.Div(
                                            dcc.Graph(id="graph-expenses-monthly"),
                                            style={"gridColumn": "1 / -1"},
                                        ),
                                        dcc.Graph(
                                            id="graph-expenses-overview",
                                            figure=_build_overview_figure(),
                                        ),
                                        dcc.Graph(id="graph-expenses-drilldown"),
                                    ],
                                    className="graph-grid",
                                    style={"marginTop": "12px"},
                                ),
                            ],
                        )
                    ],
                ),
            ],
            className="section-card",
        )
    ]
)


@callback(Output("graph-expenses-monthly", "figure"), Input("expenses-month", "value"))
def update_monthly_chart(month_key: str | None) -> go.Figure:
    if not month_key or EXPENSES_DF.empty:
        return _empty_figure("Нет данных за выбранный месяц")

    month_frame = EXPENSES_DF[EXPENSES_DF["month_key"] == month_key]
    if month_frame.empty:
        return _empty_figure("Нет данных за выбранный месяц")

    aggregated = month_frame.groupby(["category", "subcategory"], as_index=False)["amount"].sum()
    categories = _ordered_categories(aggregated)
    aggregated["category"] = pd.Categorical(aggregated["category"], categories=categories, ordered=True)
    aggregated.sort_values(["category", "subcategory"], inplace=True)

    fig = px.bar(
        aggregated,
        x="amount",
        y="category",
        color="subcategory",
        orientation="h",
        labels={"amount": "Сумма, млн ₽", "category": "Категория", "subcategory": "Подкатегория"},
    )
    fig.update_layout(
        barmode="stack",
        template="plotly_white",
        height=420,
        margin=dict(l=20, r=20, t=50, b=70),
        legend_title_text="",
    )
    fig.update_xaxes(title_text="Сумма, млн ₽")
    fig.update_yaxes(title_text="Категория", automargin=True)
    return fig


@callback(Output("graph-expenses-drilldown", "figure"), Input("expenses-category", "value"))
def update_drilldown_chart(category: str | None) -> go.Figure:
    if not category or EXPENSES_DF.empty:
        return _empty_figure("Нет данных для выбранной категории")

    category_frame = EXPENSES_DF[EXPENSES_DF["category"] == category]
    if category_frame.empty:
        return _empty_figure("Нет данных для выбранной категории")

    aggregated = (
        category_frame.groupby(["month_key", "month_label", "subcategory"], as_index=False)["amount"].sum()
    )
    aggregated.sort_values("month_key", inplace=True)

    fig = px.bar(
        aggregated,
        x="month_label",
        y="amount",
        color="subcategory",
        labels={"month_label": "Месяц", "amount": "Сумма, млн ₽", "subcategory": "Подкатегория"},
    )
    fig.update_layout(
        barmode="stack",
        template="plotly_white",
        height=420,
        margin=dict(l=20, r=20, t=50, b=90),
        legend_title_text="",
    )
    fig.update_xaxes(categoryorder="array", categoryarray=aggregated["month_label"].unique())
    fig.update_yaxes(title_text="Сумма, млн ₽")
    return fig

