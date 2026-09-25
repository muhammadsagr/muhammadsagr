"""Department Analysis (plus divisions, business units and job titles)."""
from __future__ import annotations

import streamlit as st

from analytics.departments import job_title_analysis, unit_metrics
from ui.common import empty_state, kpi, page_header, severity_label, table
from ui.state import context
from utils.helpers import fmt_num, pct
from visualization.department_charts import (
    headcount_bar,
    management_ratio_bar,
    span_vs_headcount,
    vacancy_bar,
)

UNIT_VIEW_COLS = ["headcount", "managers", "management_ratio", "avg_span", "avg_depth", "vacancies",
                  "avg_salary", "median_salary", "layers", "max_depth", "vacancy_rate",
                  "low_span_managers", "high_span_managers", "invalid_reporting"]


def _units_tab(ctx, by: str, key: str) -> None:
    s = ctx.settings
    units = unit_metrics(ctx.df, by, s)
    if units.empty:
        empty_state()
        return
    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    q = c1.text_input("بحث", key=f"{key}_q", placeholder="اسم الوحدة…")
    min_hc = c2.number_input("Headcount ≥", 0, value=0, key=f"{key}_min")
    flagged = c3.selectbox("تصفية", ["الكل", "Management Ratio مرتفع", "وحدات صغيرة",
                                     "بها شواغر", "بها علاقات غير صحيحة"], key=f"{key}_flag")
    sort_col = c4.selectbox("ترتيب حسب", UNIT_VIEW_COLS, key=f"{key}_sort")
    view = units[units["headcount"] >= min_hc]
    if q:
        view = view[view[by].str.contains(q, case=False, regex=False)]
    if flagged == "Management Ratio مرتفع":
        view = view[view["management_ratio"] > s.high_management_ratio]
    elif flagged == "وحدات صغيرة":
        view = view[view["headcount"] <= s.small_department_threshold]
    elif flagged == "بها شواغر":
        view = view[view["vacancies"] > 0]
    elif flagged == "بها علاقات غير صحيحة":
        view = view[view["invalid_reporting"] > 0]
    view = view.sort_values(sort_col, ascending=False, na_position="last")
    lead = [by] + (["division", "business_unit"] if by == "department" else [])
    table(view[lead + UNIT_VIEW_COLS], f"{key}_table", f"{by}_analysis", height=420)

    left, right = st.columns(2)
    with left:
        st.markdown("**Management Ratio**")
        st.plotly_chart(management_ratio_bar(view, s.high_management_ratio, by), width="stretch",
                        key=f"{key}_management_ratio_bar")
    with right:
        st.markdown("**Headcount**")
        st.plotly_chart(headcount_bar(view, by), width="stretch",
                        key=f"{key}_headcount_bar")
    left, right = st.columns(2)
    with left:
        st.markdown("**Headcount مقابل متوسط Span of Control**")
        st.plotly_chart(span_vs_headcount(view, by), width="stretch",
                        key=f"{key}_span_vs_headcount")
    with right:
        st.markdown("**الوظائف الشاغرة**")
        st.plotly_chart(vacancy_bar(view, by), width="stretch",
                        key=f"{key}_vacancy_bar")


def _drilldown(ctx) -> None:
    units = unit_metrics(ctx.df, "department", ctx.settings)
    if units.empty:
        return
    dept = st.selectbox("اختر إدارة", units["department"].tolist(), key="dept_drill")
    u = units[units["department"].eq(dept)].iloc[0]
    c = st.columns(6)
    kpi(c[0], "Headcount", f"{int(u['headcount']):,}")
    kpi(c[1], "Managers", f"{int(u['managers'])}")
    kpi(c[2], "Management Ratio", pct(u["management_ratio"]))
    kpi(c[3], "Avg Span", fmt_num(u["avg_span"], 2))
    kpi(c[4], "Layers", f"{int(u['layers'])}")
    kpi(c[5], "Vacancies", f"{int(u['vacancies'])}")
    f = ctx.findings_all
    f = f[f["department"].eq(dept)]
    st.markdown(f"**Findings في {dept}: {len(f)}**")
    if len(f):
        v = f[["finding_id", "type", "severity", "entity_name", "description"]].copy()
        v["severity"] = v["severity"].map(severity_label)
        table(v, "dept_findings", f"findings_{dept}")


def _titles_tab(ctx) -> None:
    jt = job_title_analysis(ctx.df, ctx.settings)
    st.markdown("**المسميات المتكررة بصيغ كتابة مختلفة (Duplicate Job Titles)**")
    if jt["variants"].empty:
        st.caption("لا توجد.")
    else:
        table(jt["variants"], "title_variants")
    st.markdown(f"**المسميات المتشابهة (Similar Job Titles ≥ {ctx.settings.title_similarity_threshold:.2f})**")
    st.caption("مقارنة داخل نفس القطاع. يتم تجاهل أزواج السلم الوظيفي (مثل Accountant / Senior Accountant).")
    if jt["similar"].empty:
        st.caption("لا توجد.")
    else:
        table(jt["similar"], "title_similar")
    st.markdown("**تكرار المسميات الوظيفية**")
    table(jt["titles"].drop(columns=["normalized"]), "title_counts", height=360)


def render() -> None:
    ctx = context()
    page_header("Departments", "تحليل الإدارات والقطاعات ووحدات الأعمال", ctx)
    if ctx.active.empty and not ctx.df["is_vacant"].any():
        empty_state()
        return
    tabs = st.tabs(["Departments", "Department Drill-down", "Divisions", "Business Units",
                    "Job Titles"])
    with tabs[0]:
        _units_tab(ctx, "department", "dept")
    with tabs[1]:
        _drilldown(ctx)
    with tabs[2]:
        _units_tab(ctx, "division", "div")
    with tabs[3]:
        _units_tab(ctx, "business_unit", "bu")
    with tabs[4]:
        _titles_tab(ctx)
