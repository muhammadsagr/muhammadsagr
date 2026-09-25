"""Overview charts: span distribution, findings, department distribution."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from utils.config import FINDING_TYPES, SEVERITIES
from visualization.theme import PRIMARY, SEVERITY_COLORS, SPAN_COLORS, style, threshold_line


def span_histogram(spans: pd.Series, low: int, high: int, median: float | None = None
                   ) -> go.Figure:
    counts = spans.astype(int).value_counts().sort_index()
    cats = ["Low" if k <= low else ("High" if k > high else "Within Range") for k in counts.index]
    fig = go.Figure()
    for cat in ["Low", "Within Range", "High"]:
        idx = [i for i, c in zip(counts.index, cats) if c == cat]
        if not idx:
            continue
        fig.add_bar(x=idx, y=counts.loc[idx].values, name=cat, marker_color=SPAN_COLORS[cat],
                    hovertemplate="%{x} direct reports<br>Managers: %{y}<extra>" + cat + "</extra>")
    fig.update_xaxes(title="Direct reports per manager", dtick=1 if counts.index.max() <= 40 else 5)
    fig.update_yaxes(title="Managers")
    threshold_line(fig, low + 0.5, f"Low ≤ {low}")
    threshold_line(fig, high + 0.5, f"High > {high}")
    if median is not None:
        fig.add_vline(x=median, line_color=PRIMARY, line_width=1, line_dash="dot",
                      annotation_text=f"Median {median:g}", annotation_position="bottom right",
                      annotation_font_size=11)
    fig.update_layout(barmode="stack")
    return style(fig)


def findings_by_type(findings: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if findings.empty:
        return style(fig)
    order = [t for t in FINDING_TYPES if t in set(findings["type"])]
    for sev in SEVERITIES:
        sub = findings[findings["severity"].eq(sev)]["type"].value_counts()
        fig.add_bar(y=order, x=[int(sub.get(t, 0)) for t in order], name=sev, orientation="h",
                    marker_color=SEVERITY_COLORS[sev],
                    hovertemplate="%{y}<br>" + sev + ": %{x}<extra></extra>")
    fig.update_layout(barmode="stack", yaxis=dict(autorange="reversed"))
    fig.update_xaxes(title="Findings")
    return style(fig, height=max(260, 30 * len(order)))


def department_distribution(df: pd.DataFrame, top: int = 25) -> go.Figure:
    a = df[df["is_active"]]
    counts = a["department"].replace("", "(Unassigned)").value_counts().head(top).sort_values()
    fig = go.Figure(go.Bar(y=counts.index, x=counts.values, orientation="h",
                           marker_color=PRIMARY,
                           hovertemplate="%{y}<br>Employees: %{x:,}<extra></extra>"))
    fig.update_xaxes(title="Active employees")
    return style(fig, height=max(300, 20 * len(counts)), legend=False)
