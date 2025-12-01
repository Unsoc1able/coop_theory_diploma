"""DRAC-кластеризация портфелей по трём метрикам схожести.

Страница перенесена на алгоритм из исследовательского кода: рассчитываются
косинусное сходство портфеля фаз, Жаккард по бинарным признакам фаз и схожесть
по временным рядам успехов, агрегируются с весами и подаются в DRAC.
Если при импорте страницы появляется ошибка про ``dataclass`` и ``class
Threshold``, значит в окружении осталась старая версия файла. Удалите
закэшированные артефакты и используйте текущую ревизию.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Dict, Iterable, List, Mapping, Sequence, TypedDict

import dash
from dash import Input, Output, State, callback, dcc, dash_table, html
import plotly.express as px
import numpy as np
from scipy.stats import pearsonr

from ..data import MIN_TOTAL_PROJECTS
from ..logic import compute_company_metrics


dash.register_page(__name__, path="/clusters", name="Кластеры по схожести")


class WeightSpec(TypedDict):
    field: str
    label: str
    minimum: float
    maximum: float
    step: float
    format: str


WEIGHTS: Sequence[WeightSpec] = (
    {
        "field": "w1",
        "label": "Вес косинусного сходства",
        "minimum": 0.0,
        "maximum": 1.0,
        "step": 0.05,
        "format": "{:.2f}",
    },
    {
        "field": "w2",
        "label": "Вес Жаккарда",
        "minimum": 0.0,
        "maximum": 1.0,
        "step": 0.05,
        "format": "{:.2f}",
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


def _build_weight_slider(spec: WeightSpec) -> html.Div:
    slider_id = f"cluster-{spec['field']}"
    marks = {
        spec["minimum"]: spec["format"].format(spec["minimum"]),
        spec["maximum"]: spec["format"].format(spec["maximum"]),
    }
    return html.Div(
        [
            html.Div(spec["label"], className="slider-label"),
            dcc.Slider(
                id=slider_id,
                min=spec["minimum"],
                max=spec["maximum"],
                step=spec["step"],
                marks=marks,
                tooltip={"placement": "bottom", "always_visible": True},
            ),
        ],
        className="slider-card",
    )


def _default_weights() -> Dict[str, float]:
    return {"w1": 0.4, "w2": 0.3, "delta": 0.75, "gamma": 0.85, "min_overlap": 5, "neutral": 0.5}


def _hash_seed(name: str) -> int:
    digest = hashlib.sha256(name.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")


def generate_synthetic_data(
    n_players: int = 12,
    n_nosologies: int = 6,
    n_indications: int = 20,
    t_len_max: int = 30,
    t_len_min: int = 10,
    n_clusters: int = 3,
    noise_frac: float = 0.25,
    cluster_strength: float = 0.8,
    random_state: int | None = 42,
):
    rng = np.random.default_rng(random_state)
    n_noise = int(np.round(n_players * noise_frac))
    n_core = n_players - n_noise
    core_labels = np.repeat(np.arange(n_clusters), n_core // n_clusters)
    remainder = n_core - len(core_labels)
    if remainder > 0:
        core_labels = np.concatenate([core_labels, np.arange(remainder)])
    rng.shuffle(core_labels)
    cluster_labels = np.full(n_players, -1, dtype=int)
    cluster_labels[:n_core] = core_labels

    proto_nos = rng.gamma(shape=1.0, scale=1.0, size=(n_clusters, n_nosologies))
    proto_nos /= proto_nos.sum(axis=1, keepdims=True)
    proto_P = (rng.random((n_clusters, n_indications)) < 0.3).astype(int)

    proto_U = np.zeros((n_clusters, t_len_max))
    for k in range(n_clusters):
        eps = rng.normal(0.0, 1.0, size=t_len_max)
        proto_U[k, 0] = eps[0]
        for t in range(1, t_len_max):
            proto_U[k, t] = 0.7 * proto_U[k, t - 1] + eps[t]

    X_nos = np.zeros((n_players, n_nosologies))
    P = np.zeros((n_players, n_indications), dtype=int)
    U_list = []
    for i in range(n_core):
        cl = cluster_labels[i]
        noise_vec = rng.gamma(shape=1.0, scale=1.0, size=n_nosologies)
        noise_vec /= noise_vec.sum()
        x = cluster_strength * proto_nos[cl] + (1 - cluster_strength) * noise_vec
        x /= x.sum()
        X_nos[i] = x

        base = proto_P[cl].copy()
        flip_mask = rng.random(n_indications) < (1 - cluster_strength) * 0.7
        base[flip_mask] = 1 - base[flip_mask]
        P[i] = base

        Ti = rng.integers(t_len_min, t_len_max + 1)
        proto_tail = proto_U[cl][-Ti:]
        u = proto_tail + rng.normal(0.0, (1 - cluster_strength), size=Ti)
        U_list.append(u)

    for i in range(n_core, n_players):
        x_raw = rng.gamma(shape=1.0, scale=1.0, size=n_nosologies)
        X_nos[i] = x_raw / x_raw.sum()
        P[i] = (rng.random(n_indications) < 0.2).astype(int)

        Ti = rng.integers(t_len_min, t_len_max + 1)
        eps = rng.normal(0.0, 1.2, size=Ti)
        u = np.zeros(Ti)
        u[0] = eps[0]
        for t in range(1, Ti):
            u[t] = 0.3 * u[t - 1] + eps[t]
        U_list.append(u)

    return X_nos, P, U_list, cluster_labels


def cosine_similarity_matrix(X: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(X, axis=1, keepdims=True) + 1e-12
    X_norm = X / norms
    S = X_norm @ X_norm.T
    return np.clip(S, 0.0, 1.0)


def jaccard_similarity_matrix(P: np.ndarray) -> np.ndarray:
    intersection = P @ P.T
    row_sums = P.sum(axis=1)
    union = row_sums[:, None] + row_sums[None, :] - intersection
    return np.where(union > 0, intersection / union, 0.0)


def reliability_similarity_matrix_varlen(
    U_list: Sequence[np.ndarray],
    variant: str = "rho_to_01",
    min_overlap: int = 5,
    neutral_similarity: float = 0.5,
) -> np.ndarray:
    n = len(U_list)
    S = np.zeros((n, n), dtype=float)
    for i in range(n):
        S[i, i] = 1.0
        ui = np.asarray(U_list[i])
        for j in range(i + 1, n):
            uj = np.asarray(U_list[j])
            L = min(len(ui), len(uj))
            if L < min_overlap:
                sij = neutral_similarity
            else:
                xi = ui[-L:]
                xj = uj[-L:]
                mask = ~np.isnan(xi) & ~np.isnan(xj)
                if mask.sum() < min_overlap:
                    sij = neutral_similarity
                else:
                    r, _ = pearsonr(xi[mask], xj[mask])
                    r = np.clip(r, -1.0, 1.0)
                    if variant == "rho_to_01":
                        sij = (r + 1.0) / 2.0
                    elif variant == "diversified":
                        sij = 1.0 - abs(r)
                    else:
                        raise ValueError("Unknown variant")
            S[i, j] = sij
            S[j, i] = sij
    return S


def aggregate_similarity(S1: np.ndarray, S2: np.ndarray, S3: np.ndarray, w1: float, w2: float) -> np.ndarray:
    w3 = max(0.0, 1.0 - w1 - w2)
    S = w1 * S1 + w2 * S2 + w3 * S3
    return np.clip(S, 0.0, 1.0)


def shapley_like_centrality(S: np.ndarray) -> np.ndarray:
    S_tmp = S.copy()
    np.fill_diagonal(S_tmp, 0.0)
    return 0.5 * S_tmp.sum(axis=1)


def drac_clustering(S: np.ndarray, delta: float = 0.7, gamma: float = 0.8):
    n = S.shape[0]
    S_tmp = S.copy()
    np.fill_diagonal(S_tmp, 0.0)
    phi = 0.5 * S_tmp.sum(axis=1)
    gM = phi.max() if n > 0 else 0.0
    unassigned = set(range(n))
    clusters: List[List[int]] = []
    while unassigned:
        center = max(unassigned, key=lambda i: phi[i])
        lM = phi[center]
        beta = delta * math.sqrt(lM / gM) if gM > 0 else 0.0
        cluster = [center]
        queue = [center]
        unassigned.remove(center)
        while queue:
            p = queue.pop(0)
            for j in list(unassigned):
                if S_tmp[p, j] >= beta:
                    unassigned.remove(j)
                    cluster.append(j)
                    if phi[j] >= gamma * lM:
                        queue.append(j)
        clusters.append(cluster)
    return clusters, phi


def mds_from_similarity(S: np.ndarray, n_components: int = 2):
    D = np.sqrt(np.clip(1.0 - S, 0.0, 1.0))
    D2 = D ** 2
    n = S.shape[0]
    if n == 0:
        return np.zeros((0, n_components))
    J = np.eye(n) - np.ones((n, n)) / n
    B = -0.5 * J @ D2 @ J
    eigvals, eigvecs = np.linalg.eigh(B)
    idx = np.argsort(eigvals)[::-1]
    eigvals = eigvals[idx]
    eigvecs = eigvecs[:, idx]
    eigvals_pos = np.maximum(eigvals[:n_components], 0.0)
    return eigvecs[:, :n_components] * np.sqrt(eigvals_pos)


def _derive_series_from_company(name: str, approvals: float, projects: float, length: int = 16) -> np.ndarray:
    rng = np.random.default_rng(_hash_seed(name))
    eps = rng.normal(0.0, 1.0 + projects / 10.0, size=length)
    series = np.zeros(length)
    series[0] = eps[0]
    for t in range(1, length):
        series[t] = 0.6 * series[t - 1] + eps[t] + approvals / max(projects, 1)
    return series


def _build_similarity_from_metrics(metrics: Sequence[Mapping[str, float]], params: Mapping[str, float]):
    names = [item["name"] for item in metrics]
    counts = np.array([[item.get("n_I", 0.0), item.get("n_II", 0.0), item.get("n_III", 0.0)] for item in metrics])
    totals = counts.sum(axis=1, keepdims=True)
    X_nos = np.divide(counts, np.where(totals == 0, 1.0, totals))
    P = (counts > 0).astype(int)
    U_list = [
        _derive_series_from_company(
            item["name"],
            item.get("approvals", 0.0),
            item.get("n_I", 0.0) + item.get("n_II", 0.0) + item.get("n_III", 0.0),
        )
        for item in metrics
    ]
    S_cos = cosine_similarity_matrix(X_nos)
    S_jac = jaccard_similarity_matrix(P)
    S_rel = reliability_similarity_matrix_varlen(
        U_list,
        variant="rho_to_01",
        min_overlap=int(params.get("min_overlap", 5)),
        neutral_similarity=float(params.get("neutral", 0.5)),
    )
    S_agg = aggregate_similarity(S_cos, S_jac, S_rel, float(params.get("w1", 0.4)), float(params.get("w2", 0.3)))
    return names, S_cos, S_jac, S_rel, S_agg


layout = html.Div(
    [
        dcc.Store(id="cluster-weights-store", data=_default_weights()),
        dcc.Download(id="cluster-download"),
        html.Div(
            [
                html.H2("DRAC-кластеры по схожести портфелей"),
                html.P(
                    "Алгоритм строит три матрицы сходства (фазы, портфель, динамика), агрегирует их и выполняет DRAC-кластеризацию.",
                    className="note",
                ),
                dcc.Tabs(
                    id="cluster-tabs",
                    value="weights",
                    children=[
                        dcc.Tab(
                            label="Параметры", value="weights", children=[
                                html.Div(
                                    [
                                        html.Div(
                                            [_build_weight_slider(spec) for spec in WEIGHTS],
                                            className="controls-stack",
                                        ),
                                        html.Div(
                                            [
                                                html.Div(
                                                    [
                                                        html.Div("Вес надежности (рассчитывается как 1 - w1 - w2)", className="slider-label"),
                                                        html.Div(id="cluster-w3", className="note"),
                                                    ],
                                                    className="slider-card",
                                                ),
                                                html.Div(
                                                    [
                                                        html.Div("Δ (порог связей)", className="slider-label"),
                                                        dcc.Slider(
                                                            id="cluster-delta",
                                                            min=0.1,
                                                            max=1.2,
                                                            step=0.05,
                                                            value=_default_weights()["delta"],
                                                            tooltip={"placement": "bottom", "always_visible": True},
                                                        ),
                                                    ],
                                                    className="slider-card",
                                                ),
                                                html.Div(
                                                    [
                                                        html.Div("γ (порог ветвления)", className="slider-label"),
                                                        dcc.Slider(
                                                            id="cluster-gamma",
                                                            min=0.5,
                                                            max=1.2,
                                                            step=0.05,
                                                            value=_default_weights()["gamma"],
                                                            tooltip={"placement": "bottom", "always_visible": True},
                                                        ),
                                                    ],
                                                    className="slider-card",
                                                ),
                                                html.Div(
                                                    [
                                                        html.Div("Мин. перекрытие рядов", className="slider-label"),
                                                        dcc.Slider(
                                                            id="cluster-min-overlap",
                                                            min=2,
                                                            max=20,
                                                            step=1,
                                                            value=_default_weights()["min_overlap"],
                                                            tooltip={"placement": "bottom", "always_visible": True},
                                                        ),
                                                    ],
                                                    className="slider-card",
                                                ),
                                                html.Div(
                                                    [
                                                        html.Div("Нейтральное сходство", className="slider-label"),
                                                        dcc.Slider(
                                                            id="cluster-neutral",
                                                            min=0.0,
                                                            max=1.0,
                                                            step=0.05,
                                                            value=_default_weights()["neutral"],
                                                            tooltip={"placement": "bottom", "always_visible": True},
                                                        ),
                                                    ],
                                                    className="slider-card",
                                                ),
                                            ],
                                            className="controls-stack",
                                            style={"marginTop": "12px"},
                                        ),
                                        html.Div(
                                            [
                                                html.Button(
                                                    "Сбросить параметры",
                                                    id="btn-reset-weights",
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
                                            "Если портфелей нет, используется синтетическая выборка для демонстрации.",
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
                                                {"name": "σ_ij", "id": "sigma"},
                                                {"name": "Косинус", "id": "cosine"},
                                                {"name": "Жаккард", "id": "jaccard"},
                                                {"name": "Надежность", "id": "reliability"},
                                            ],
                                            style_cell={"fontSize": 13},
                                            style_header={"fontWeight": "600", "color": "#111827"},
                                            style_table={"marginTop": "12px"},
                                            page_size=15,
                                        ),
                                        dcc.Graph(id="cluster-graph", style={"marginTop": "18px"}),
                                        html.Div(
                                            [
                                                dcc.Graph(id="cluster-heat-cos"),
                                                dcc.Graph(id="cluster-heat-jac"),
                                                dcc.Graph(id="cluster-heat-rel"),
                                                dcc.Graph(id="cluster-heat-agg"),
                                            ],
                                            className="section-card",
                                        ),
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
    Output("cluster-weights-store", "data"),
    [Input(f"cluster-{spec['field']}", "value") for spec in WEIGHTS]
    + [
        Input("cluster-delta", "value"),
        Input("cluster-gamma", "value"),
        Input("cluster-min-overlap", "value"),
        Input("cluster-neutral", "value"),
        Input("btn-reset-weights", "n_clicks"),
    ],
    State("cluster-weights-store", "data"),
)
def sync_weight_store(*args):
    values = args[: len(WEIGHTS)]
    delta, gamma, min_overlap, neutral, reset_clicks = args[len(WEIGHTS) : len(WEIGHTS) + 5]
    current = args[-1] if args else {}
    if reset_clicks and dash.callback_context.triggered_id == "btn-reset-weights":
        return _default_weights()
    data = current.copy() if isinstance(current, dict) else {}
    for spec, value in zip(WEIGHTS, values):
        if value is not None:
            data[spec["field"]] = float(value)
    if delta is not None:
        data["delta"] = float(delta)
    if gamma is not None:
        data["gamma"] = float(gamma)
    if min_overlap is not None:
        data["min_overlap"] = int(min_overlap)
    if neutral is not None:
        data["neutral"] = float(neutral)
    return data


@callback(
    [Output(f"cluster-{spec['field']}", "value") for spec in WEIGHTS]
    + [
        Output("cluster-delta", "value"),
        Output("cluster-gamma", "value"),
        Output("cluster-min-overlap", "value"),
        Output("cluster-neutral", "value"),
        Output("cluster-w3", "children"),
    ],
    Input("cluster-weights-store", "data"),
)
def hydrate_sliders(data):
    data = data or _default_weights()
    w1 = data.get("w1", 0.4)
    w2 = data.get("w2", 0.3)
    w3 = max(0.0, 1.0 - w1 - w2)
    label_w3 = f"Текущий вес = {w3:.2f}"
    return [data.get(spec["field"], spec["minimum"]) for spec in WEIGHTS] + [
        data.get("delta", _default_weights()["delta"]),
        data.get("gamma", _default_weights()["gamma"]),
        data.get("min_overlap", _default_weights()["min_overlap"]),
        data.get("neutral", _default_weights()["neutral"]),
        label_w3,
    ]


@callback(
    Output("cluster-summary", "children"),
    Output("cluster-list", "children"),
    Output("cluster-pairs", "data"),
    Output("cluster-graph", "figure"),
    Output("cluster-heat-cos", "figure"),
    Output("cluster-heat-jac", "figure"),
    Output("cluster-heat-rel", "figure"),
    Output("cluster-heat-agg", "figure"),
    Input("companies-store", "data"),
    Input("parameters-store", "data"),
    Input("cluster-weights-store", "data"),
)
def update_clusters(companies, params, weights):
    params = params or {}
    weights = weights or _default_weights()
    companies = _filter_small_companies(companies)

    if companies:
        metrics = compute_company_metrics(companies, params)
        names, S_cos, S_jac, S_rel, S_agg = _build_similarity_from_metrics(metrics, weights)
    else:
        # Фолбэк: синтетические данные
        X_nos, P, U_list, true_clusters = generate_synthetic_data(random_state=123)
        names = [f"Игрок {i}" for i in range(len(X_nos))]
        S_cos = cosine_similarity_matrix(X_nos)
        S_jac = jaccard_similarity_matrix(P)
        S_rel = reliability_similarity_matrix_varlen(
            U_list,
            variant="rho_to_01",
            min_overlap=int(weights.get("min_overlap", 5)),
            neutral_similarity=float(weights.get("neutral", 0.5)),
        )
        S_agg = aggregate_similarity(S_cos, S_jac, S_rel, float(weights.get("w1", 0.4)), float(weights.get("w2", 0.3)))
        metrics = [
            {"name": n, "approvals": float("nan"), "budget": float("nan"), "n_I": 0, "n_II": 0, "n_III": 0}
            for n in names
        ]

    clusters, phi = drac_clustering(S_agg, delta=float(weights.get("delta", 0.75)), gamma=float(weights.get("gamma", 0.85)))
    if not clusters:
        empty_fig = px.scatter(title="Кластеры не найдены")
        blank = px.imshow([[0]], title="Нет данных")
        return (
            html.Span("Кластеры не найдены.", className="warn"),
            html.Ul([html.Li("Нет доступных компаний")]),
            [],
            empty_fig,
            blank,
            blank,
            blank,
            blank,
        )

    label_by_idx: Dict[int, str] = {}
    for cid, members in enumerate(clusters, start=1):
        for idx in members:
            label_by_idx[idx] = f"DRAC_{cid}"

    coords = mds_from_similarity(S_agg, n_components=2)
    graph_data = []
    for idx, item in enumerate(metrics):
        graph_data.append(
            {
                "name": item.get("name", names[idx]),
                "cluster": label_by_idx.get(idx, "DRAC_?"),
                "x": coords[idx, 0] if coords.size else 0.0,
                "y": coords[idx, 1] if coords.size else 0.0,
            }
        )

    fig = px.scatter(
        graph_data,
        x="x",
        y="y",
        color="cluster",
        hover_name="name",
        title="2D MDS по σ_ij",
        labels={"x": "Компонента 1", "y": "Компонента 2"},
    )
    fig.update_layout(template="plotly_white", height=520, margin=dict(l=20, r=20, t=50, b=50))

    cluster_items = [html.Li(", ".join(names[idx] for idx in sorted(cluster))) for cluster in clusters]
    summary = html.Span(
        [
            f"Кластеров: {len(clusters)}. ",
            f"Δ={weights.get('delta', 0.75)}, γ={weights.get('gamma', 0.85)}, ",
            f"веса (w1={weights.get('w1', 0.4):.2f}, w2={weights.get('w2', 0.3):.2f}, w3={max(0.0, 1-weights.get('w1',0)-weights.get('w2',0)):.2f}).",
        ]
    )

    pair_rows: List[Dict[str, object]] = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            pair_rows.append(
                {
                    "pair": f"{names[i]} / {names[j]}",
                    "sigma": round(float(S_agg[i, j]), 3),
                    "cosine": round(float(S_cos[i, j]), 3),
                    "jaccard": round(float(S_jac[i, j]), 3),
                    "reliability": round(float(S_rel[i, j]), 3),
                }
            )

    heat_cos = px.imshow(np.round(S_cos, 2), text_auto=True, aspect="auto", title="Cosine similarity S_cos")
    heat_jac = px.imshow(np.round(S_jac, 2), text_auto=True, aspect="auto", title="Jaccard similarity S_jac")
    heat_rel = px.imshow(np.round(S_rel, 2), text_auto=True, aspect="auto", title="Reliability similarity S_rel")
    heat_agg = px.imshow(np.round(S_agg, 2), text_auto=True, aspect="auto", title="Aggregated similarity σ_ij")
    for fig_heat in (heat_cos, heat_jac, heat_rel, heat_agg):
        fig_heat.update_xaxes(title="Игрок j", tickmode="linear")
        fig_heat.update_yaxes(title="Игрок i", tickmode="linear")

    return summary, html.Ul(cluster_items), pair_rows, fig, heat_cos, heat_jac, heat_rel, heat_agg


@callback(
    Output("cluster-download", "data"),
    Input("btn-download-thresholds", "n_clicks"),
    State("cluster-weights-store", "data"),
    State("companies-store", "data"),
    State("parameters-store", "data"),
    prevent_initial_call=True,
)
def download_thresholds(n_clicks, weights, companies, params):
    weights = weights or _default_weights()
    companies = _filter_small_companies(companies)
    params = params or {}
    metrics = compute_company_metrics(companies, params) if companies else []

    payload = {
        "weights": weights,
        "companies": [
            {
                "name": item["name"],
                "approvals": item.get("approvals", 0.0),
                "budget": item.get("budget", 0.0),
                "unit_cost": item.get("unit_cost", math.nan),
                "n_I": item.get("n_I", 0.0),
                "n_II": item.get("n_II", 0.0),
                "n_III": item.get("n_III", 0.0),
            }
            for item in metrics
        ],
    }

    content = json.dumps(payload, ensure_ascii=False, indent=2)
    return dict(content=content, filename="cluster_drac_params.json")
