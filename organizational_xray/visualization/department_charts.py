"""Charts for departments / organisational units."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from visualization.theme import MUTED, PRIMARY, SECONDARY, style, threshold_line


def headcount_bar(units: pd.DataFrame, by: str = "department", top: int = 30) -> go.Figure:
    d = units.sort_values("headcount", ascending=True).tail(top)
    fig = go.Figure(go.Bar(
        y=d[by], x=d["headcount"], orientation="h", marker_color=PRIMARY,
        customdata=list(zip(d["managers"], d["vacancies"])),
        hovertemplate="%{y}<br>Headcount: %{x:,}<br>Managers: %{customdata[0]}"
                      "<br>Vacancies: %{customdata[1]}<extra></extra>"))
    fig.update_xaxes(title="Active employees")
    return style(fig, height=max(280, 22 * len(d)), legend=False)


def management_ratio_bar(units: pd.DataFrame, threshold: float, by: str = "department"
                         ) -> go.Figure:
    d = units.dropna(subset=["management_ratio"]).sort_values("management_ratio")
    colors = [SECONDARY if r > threshold else PRIMARY for r in d["management_ratio"]]
    fig = go.Figure(go.Bar(
        y=d[by], x=d["management_ratio"] * 100, orientation="h", marker_color=colors,
        customdata=list(zip(d["managers"], d["headcount"])),
        hovertemplate="%{y}<br>Management ratio: %{x:.1f}%<br>%{customdata[0]} managers / "
                      "%{customdata[1]} employees<extra></extra>"))
    fig.update_xaxes(title="Management ratio (%)", ticksuffix="%")
    threshold_line(fig, threshold * 100, f"Threshold {threshold * 100:.0f}%")
    return style(fig, height=max(280, 22 * len(d)), legend=False)


def span_vs_headcount(units: pd.DataFrame, by: str = "department") -> go.Figure:
    d = units.dropna(subset=["avg_span"])
    fig = go.Figure(go.Scatter(
        x=d["headcount"], y=d["avg_span"], mode="markers+text", text=d[by],
        textposition="top center", textfont=dict(size=10, color=MUTED),
        marker=dict(size=10, color=PRIMARY, line=dict(width=2, color="white")),
        customdata=list(zip(d["layers"], d["management_ratio"] * 100)),
        hovertemplate="%{text}<br>Headcount: %{x:,}<br>Avg span: %{y:.2f}"
                      "<br>Layers: %{customdata[0]}<br>Mgmt ratio: %{customdata[1]:.1f}%<extra></extra>"))
    fig.update_xaxes(title="Headcount", type="log")
    fig.update_yaxes(title="Average span of control")
    return style(fig, height=420, legend=False)


def vacancy_bar(units: pd.DataFrame, by: str = "department") -> go.Figure:
    d = units[units["vacancies"] > 0].sort_values("vacancies")
    fig = go.Figure(go.Bar(
        y=d[by], x=d["vacancies"], orientation="h", marker_color=PRIMARY,
        customdata=d["vacancy_rate"] * 100,
        hovertemplate="%{y}<br>Vacancies: %{x}<br>Vacancy rate: %{customdata:.1f}%<extra></extra>"))
    fig.update_xaxes(title="Vacant positions")
    return style(fig, height=max(260, 22 * len(d)), legend=False)
