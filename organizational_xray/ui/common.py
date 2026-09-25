"""Reusable UI building blocks."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from exports.exporter import to_csv_bytes
from ui.state import FILTERS, filter_options, reset_filters
from utils.config import DISPLAY_NAMES, LEVEL_NAMES
from utils.helpers import display_df

CSS = """
<style>
/* Arabic prose reads right-to-left; tables and charts stay left-to-right. */
[data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] li,
[data-testid="stCaptionContainer"], .stAlert p { direction: rtl; text-align: right; }
[data-testid="stMarkdownContainer"] .ltr, [data-testid="stMarkdownContainer"] .ltr p,
[data-testid="stMarkdownContainer"] code { direction: ltr; text-align: left; unicode-bidi: plaintext; }
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { direction: ltr; text-align: left; }
[data-testid="stMetric"] { padding: 0.6rem 0.8rem; }
[data-testid="stMetricValue"] { font-size: 1.6rem; }
.xr-qa { border: 1px solid rgba(137,135,129,.25); border-radius: 8px; padding: .6rem .8rem;
         margin-bottom: .5rem; direction: rtl; text-align: right; }
.xr-qa .q { font-size: .85rem; opacity: .75; }
.xr-qa .a { font-size: 1.05rem; font-weight: 600; margin: .15rem 0; }
.xr-qa .e { font-size: .8rem; opacity: .7; }
.xr-chain { direction: ltr; text-align: left; }
.xr-chain .node { border: 1px solid rgba(137,135,129,.35); border-radius: 6px; padding: .35rem .6rem;
                  display: inline-block; min-width: 320px; }
.xr-chain .node.sel { border-color: #2a78d6; border-width: 2px; }
.xr-chain .arrow { opacity: .5; padding-left: 1.2rem; }
.xr-badge { border-radius: 4px; padding: 1px 6px; font-size: .78rem; font-weight: 600; }
</style>
"""

SEVERITY_ICONS = {"Critical": "🔴", "Significant": "🟠", "Attention": "🟡", "Informational": "⚪"}


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def page_header(title: str, subtitle: str, ctx=None) -> None:
    st.title(title)
    st.caption(subtitle)
    if ctx is not None and ctx.filtered:
        st.info(f"الفلاتر العامة مفعّلة — {ctx.filter_summary}", icon="🔎")


def sidebar_filters(model) -> None:
    opts = filter_options(model)
    with st.sidebar:
        st.markdown("**Global Filters**")
        for key, label in FILTERS:
            fmt = (lambda v: f"{v} · {LEVEL_NAMES.get(v, '')}") if key == "job_level" else str
            st.multiselect(label, opts[key], key=f"flt_{key}", format_func=fmt,
                           placeholder="All")
        mgr = model.df[model.df["is_manager"]].sort_values("total_reports", ascending=False)
        labels = {r.node_id: f"{r.node_id} · {r.employee_name} · {r.job_title}"
                  for r in mgr.itertuples()}
        st.selectbox("Manager (organisation under)", [None] + list(labels), key="flt_manager",
                     format_func=lambda v: "All" if v is None else labels.get(v, v),
                     placeholder="All")
        st.button("Clear filters", on_click=reset_filters, width="stretch")


def kpi(col, label: str, value: str, help: str | None = None, delta: str | None = None) -> None:
    col.metric(label, value, delta=delta, help=help, border=True)


def table(df: pd.DataFrame, key: str, filename: str | None = None, height: int | None = None,
          rename: bool = True, column_config: dict | None = None, **kwargs):
    """Dataframe with a CSV download button. Returns the st.dataframe event (if selectable)."""
    shown = display_df(df) if rename else df
    cfg = default_column_config(shown)
    if column_config:
        cfg.update(column_config)
    args = dict(width="stretch", hide_index=True, column_config=cfg)
    if height:
        args["height"] = height
    args.update(kwargs)
    event = st.dataframe(shown, key=key, **args)
    st.download_button("⬇ CSV", to_csv_bytes(shown), file_name=f"{filename or key}.csv",
                       mime="text/csv", key=f"dl_{key}")
    return event


def default_column_config(df: pd.DataFrame) -> dict:
    cfg = {}
    for c in df.columns:
        lc = str(c).lower()
        if "ratio" in lc or "rate" in lc or lc in ("pct of total", "score"):
            cfg[c] = st.column_config.NumberColumn(c, format="percent")
        elif "salary" in lc:
            cfg[c] = st.column_config.NumberColumn(c, format="%,.0f")
        elif lc in ("avg span", "avg depth", "mean", "avg_span", "avg_depth", "median span"):
            cfg[c] = st.column_config.NumberColumn(c, format="%.2f")
    return cfg


def severity_label(sev: str) -> str:
    return f"{SEVERITY_ICONS.get(sev, '')} {sev}"


def empty_state(msg: str = "لا توجد بيانات مطابقة للفلاتر الحالية.") -> None:
    st.info(msg, icon="ℹ️")


def col_label(c: str) -> str:
    return DISPLAY_NAMES.get(c, c.replace("_", " ").title())
