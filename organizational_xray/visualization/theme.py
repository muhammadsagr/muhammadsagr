"""Shared chart styling. Colours follow a validated, colour-blind-safe palette;
status colours are reserved for severity and never reused for series."""
from __future__ import annotations

import plotly.graph_objects as go

CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7",
               "#e34948"]
SEQUENTIAL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#2a78d6", "#1c5cab", "#104281",
              "#0d366b"]
PRIMARY = "#2a78d6"
SECONDARY = "#eb6834"
MUTED = "#898781"
GRID = "rgba(137,135,129,0.25)"

SEVERITY_COLORS = {
    "Critical": "#d03b3b",
    "Significant": "#ec835a",
    "Attention": "#fab219",
    "Informational": "#898781",
}
SPAN_COLORS = {"Low": "#eb6834", "Within Range": "#2a78d6", "High": "#4a3aa7"}
FONT = "system-ui, -apple-system, 'Segoe UI', sans-serif"


def style(fig: go.Figure, height: int = 360, title: str | None = None,
          legend: bool = True) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=8, t=40 if title else 12, b=8),
        title=dict(text=title, x=0, font=dict(size=14)) if title else None,
        font=dict(family=FONT, size=12),
        showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None),
        hoverlabel=dict(font=dict(family=FONT)),
        bargap=0.25,
    )
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor=GRID)
    fig.update_yaxes(gridcolor=GRID, zeroline=False)
    return fig


def threshold_line(fig: go.Figure, value: float, label: str, axis: str = "x",
                   color: str = MUTED) -> go.Figure:
    kw = dict(line_dash="dash", line_color=color, line_width=1.5, annotation_text=label,
              annotation_font_size=11, annotation_font_color=color)
    if axis == "x":
        fig.add_vline(x=value, annotation_position="top", **kw)
    else:
        fig.add_hline(y=value, annotation_position="top left", **kw)
    return fig
