"""Layers & Organizational Depth."""
from __future__ import annotations

import streamlit as st

from analytics.departments import layer_metrics
from analytics.hierarchy import depth_stats, level_depth_matrix, longest_chains
from ui.common import empty_state, kpi, page_header, table
from ui.state import context
from utils.helpers import fmt_num
from visualization.hierarchy_charts import depth_histogram, layer_bars, level_depth_heatmap


def render() -> None:
    ctx = context()
    page_header("Layers", "تحليل الطبقات التنظيمية وعمق التسلسل الإداري", ctx)
    df, s = ctx.df, ctx.settings
    if ctx.active.empty:
        empty_state()
        return

    tab_level, tab_depth = st.tabs(["حسب Job Level (المعلن)", "حسب العمق الفعلي (Structural Depth)"])
    with tab_level:
        st.caption("Layer 0 → CEO، Layer 1 → C-Suite، Layer 2 → Directors، Layer 3 → Senior Managers، "
                   "Layer 4 → Managers، Layer 5 → Supervisors، Layer 6 → Individual Contributors")
        lm = layer_metrics(df, "job_level")
        st.plotly_chart(layer_bars(lm), width="stretch")
        table(lm, "layers_level", "layers_by_job_level")
    with tab_depth:
        st.caption("العمق = عدد العلاقات الإدارية بين الموظف والـCEO، محسوبًا من Manager ID وليس من المسمى.")
        lm = layer_metrics(df, "depth")
        st.plotly_chart(layer_bars(lm), width="stretch")
        table(lm, "layers_depth", "layers_by_depth")

    st.subheader("Organizational Depth")
    ds = depth_stats(ctx.model, df)
    c = st.columns(5)
    kpi(c[0], "Minimum", fmt_num(ds["min"]))
    kpi(c[1], "Maximum", fmt_num(ds["max"]))
    kpi(c[2], "Mean", fmt_num(ds["mean"], 2))
    kpi(c[3], "Median", fmt_num(ds["median"]))
    kpi(c[4], "Deep Hierarchy Threshold", str(s.deep_hierarchy_threshold),
        "الموظفون على عمق أكبر من هذا الحد يظهرون باللون البرتقالي.")
    st.caption(f"الإحصاءات محسوبة على {ds['count']:,} موظف متصل بالـCEO (بدون الـCEO نفسه).")
    left, right = st.columns(2)
    with left:
        st.markdown("**توزيع العمق**")
        st.plotly_chart(depth_histogram(df, s.deep_hierarchy_threshold), width="stretch")
    with right:
        st.markdown("**Job Level مقابل العمق الفعلي**")
        st.caption("الخلايا خارج القطر تعني أن المستوى المعلن لا يطابق موقع الموظف الفعلي في التسلسل.")
        st.plotly_chart(level_depth_heatmap(level_depth_matrix(df)), width="stretch")

    st.subheader("أطول Reporting Chains")
    top = st.slider("عدد السلاسل", 5, 50, 10, key="chains_top")
    chains = longest_chains(ctx.model, top, df)
    if chains.empty:
        empty_state()
    else:
        table(chains, "longest_chains", column_config={
            "Chain": st.column_config.TextColumn("Chain", width="large")})

    st.subheader("العمق لكل موظف")
    q = st.text_input("بحث (Employee ID / Name / Department)", key="depth_search")
    emp = df[df["is_active"]][["node_id", "employee_name", "job_title", "job_level", "department",
                              "manager_id", "depth", "reporting_status"]]
    if q:
        m = (emp["node_id"].str.contains(q, case=False, regex=False)
             | emp["employee_name"].str.contains(q, case=False, regex=False)
             | emp["department"].str.contains(q, case=False, regex=False))
        emp = emp[m]
    table(emp.sort_values("depth", ascending=False, na_position="first"), "depth_per_employee",
          height=360)
