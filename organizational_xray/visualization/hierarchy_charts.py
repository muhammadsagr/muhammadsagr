"""Charts for layers, depth and the overall structure."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from utils.helpers import blank_to_label
from visualization.theme import PRIMARY, SECONDARY, SEQUENTIAL, style


def layer_bars(layers: pd.DataFrame, title: str | None = None) -> go.Figure:
    """Employees and managers per layer (two series, grouped)."""
    d = layers.copy()
    d["label"] = [f"{int(l)} · {n}" if pd.notna(l) else n
                  for l, n in zip(d["layer"], d["layer_name"])]
    fig = go.Figure()
    fig.add_bar(y=d["label"], x=d["employees"], name="Employees", orientation="h",
                marker_color=PRIMARY,
                customdata=list(zip(d["pct_of_total"] * 100, d["managers"])),
                hovertemplate="%{y}<br>Employees: %{x:,}<br>Share: %{customdata[0]:.1f}%"
                              "<br>Managers: %{customdata[1]:,}<extra></extra>")
    fig.add_bar(y=d["label"], x=d["managers"], name="Managers", orientation="h",
                marker_color=SECONDARY,
                hovertemplate="%{y}<br>Managers: %{x:,}<extra></extra>")
    fig.update_layout(barmode="group", yaxis=dict(autorange="reversed"))
    fig.update_xaxes(title="Count")
    return style(fig, height=max(260, 42 * len(d)), title=title)


def depth_histogram(df: pd.DataFrame, threshold: int | None = None) -> go.Figure:
    d = df[df["is_active"] & df["depth"].notna()]["depth"].astype(int)
    counts = d.value_counts().sort_index()
    colors = [SECONDARY if threshold is not None and k > threshold else PRIMARY
              for k in counts.index]
    fig = go.Figure(go.Bar(x=counts.index, y=counts.values, marker_color=colors,
                           hovertemplate="Depth %{x}<br>Employees: %{y:,}<extra></extra>"))
    fig.update_xaxes(title="Depth (reporting steps to the CEO)", dtick=1)
    fig.update_yaxes(title="Employees")
    return style(fig, legend=False)


def level_depth_heatmap(matrix: pd.DataFrame) -> go.Figure:
    if matrix.empty:
        return style(go.Figure())
    fig = go.Figure(go.Heatmap(
        z=matrix.values, x=[f"Depth {c}" for c in matrix.columns],
        y=[f"Level {i}" for i in matrix.index],
        colorscale=[[i / (len(SEQUENTIAL) - 1), c] for i, c in enumerate(SEQUENTIAL)],
        text=matrix.values, texttemplate="%{text}", hoverongaps=False,
        hovertemplate="%{y} at %{x}: %{z:,} employees<extra></extra>"))
    fig.update_yaxes(autorange="reversed")
    return style(fig, height=320, legend=False)


def structure_sunburst(df: pd.DataFrame) -> go.Figure:
    a = df[df["is_active"]].copy()
    for c in ("business_unit", "division", "department"):
        a[c] = blank_to_label(a[c])
    g = a.groupby(["business_unit", "division", "department"]).size().reset_index(name="headcount")
    fig = px.sunburst(g, path=["business_unit", "division", "department"], values="headcount",
                      color_discrete_sequence=["#2a78d6", "#eb6834", "#1baf7a", "#4a3aa7",
                                               "#eda100"])
    fig.update_traces(hovertemplate="%{label}<br>Headcount: %{value:,}<extra></extra>",
                      insidetextorientation="radial")
    return style(fig, height=420, legend=False)
