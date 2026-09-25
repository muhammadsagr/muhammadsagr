"""Span of Control."""
from __future__ import annotations

import streamlit as st

from analytics.span_of_control import manager_table, span_by, span_stats
from ui.common import empty_state, kpi, page_header, table
from ui.state import context
from utils.helpers import fmt_num
from visualization.dashboards import span_histogram


def render() -> None:
    ctx = context()
    page_header("Span of Control", "عدد الموظفين المباشرين النشطين لكل مدير", ctx)
    s = ctx.settings
    mt = manager_table(ctx.df, s)
    if mt.empty:
        empty_state("لا يوجد مديرون ضمن الفلاتر الحالية.")
        return
    st_ = span_stats(mt["direct_reports"])
    c = st.columns(7)
    kpi(c[0], "Managers", f"{st_['count']:,}")
    for col, (k, label) in zip(c[1:], [("min", "Minimum"), ("max", "Maximum"), ("mean", "Mean"),
                                        ("median", "Median"), ("p25", "P25"), ("p75", "P75")]):
        kpi(col, label, fmt_num(st_[k], 2))

    st.plotly_chart(span_histogram(mt["direct_reports"], s.low_span_threshold,
                                   s.high_span_threshold, st_["median"]), width="stretch")
    st.caption(f"Low Span: ≤ {s.low_span_threshold} · High Span: > {s.high_span_threshold} "
               "(قابلة للتعديل من Settings). التصنيف يستدعي المراجعة ولا يعني حكمًا على المدير أو الدور.")

    st.subheader("المديرون")
    c1, c2, c3 = st.columns([1, 1, 2])
    cats = c1.multiselect("Span Category", ["Low", "Within Range", "High"], key="span_cat",
                          placeholder="All")
    rng = c2.slider("Direct reports", 0, int(mt["direct_reports"].max()),
                    (0, int(mt["direct_reports"].max())), key="span_rng")
    q = c3.text_input("بحث (ID / Name / Title / Department)", key="span_q")
    view = mt[mt["direct_reports"].between(*rng)]
    if cats:
        view = view[view["span_category"].isin(cats)]
    if q:
        hay = view[["node_id", "employee_name", "job_title", "department"]].fillna("").astype(str).agg(" ".join, axis=1)
        view = view[hay.str.contains(q, case=False, regex=False)]
    view = view.assign(org_median=st_["median"],
                       vs_median=(view["direct_reports"] / st_["median"]).round(2))
    table(view, "managers_span", "managers_span_of_control", height=420)

    st.subheader("Span of Control حسب الإدارة")
    table(span_by(ctx.df, "department", s), "span_by_department")
    st.subheader("Span of Control حسب Job Level")
    table(span_by(ctx.df, "job_level", s), "span_by_level")
