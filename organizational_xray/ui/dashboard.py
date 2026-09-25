"""Dashboard – the organisational summary."""
from __future__ import annotations

import html

import streamlit as st

from analytics.departments import layer_metrics
from analytics.hierarchy import layer_count
from analytics.insights import key_questions
from ui.common import empty_state, kpi, page_header
from ui.state import context
from utils.config import INVALID_REPORTING_STATUSES, RS_DISCONNECTED, SEVERITIES
from utils.helpers import fmt_num, pct
from visualization.dashboards import department_distribution, findings_by_type, span_histogram
from visualization.hierarchy_charts import layer_bars, structure_sunburst


def render() -> None:
    ctx = context()
    page_header("Organizational X-Ray", f"الملخص التنظيمي · {ctx.source}", ctx)
    df, s = ctx.df, ctx.settings
    act = ctx.active
    if act.empty:
        empty_state()
        return
    mgr = act[act["is_manager"]]
    spans = mgr["direct_reports"]
    vac = int((df["is_vacant"] & ~df["is_duplicate_id"]).sum())
    positions = len(act) + vac
    invalid = int(act["reporting_status"].isin(INVALID_REPORTING_STATUSES).sum())
    disconnected = int(act["reporting_status"].eq(RS_DISCONNECTED).sum())

    c = st.columns(5)
    kpi(c[0], "إجمالي الموظفين", f"{len(act):,}", "الموظفون النشطون (Active + On Leave) في وظائف مشغولة.")
    kpi(c[1], "إجمالي المديرين", f"{len(mgr):,}", "موظفون نشطون لديهم موظف مباشر نشط واحد على الأقل.")
    kpi(c[2], "Management Ratio", pct(len(mgr) / len(act)), "عدد المديرين ÷ إجمالي الموظفين.")
    kpi(c[3], "الطبقات التنظيمية", f"{layer_count(df)}",
        "عدد مستويات العمق المختلفة (CEO = 0) بين الموظفين المتصلين بالـCEO.")
    kpi(c[4], "Vacancy Rate", pct(vac / positions if positions else float("nan")),
        f"{vac} وظيفة شاغرة ÷ {positions:,} وظيفة.")
    c = st.columns(4)
    kpi(c[0], "Average Span of Control", fmt_num(spans.mean(), 2) if len(spans) else "—",
        "متوسط عدد الموظفين المباشرين لكل مدير.")
    kpi(c[1], "Median Span of Control", fmt_num(spans.median()) if len(spans) else "—")
    kpi(c[2], "علاقات إدارية غير صحيحة", f"{invalid:,}",
        "بدون Manager ID، Manager ID غير موجود، مدير منتهي الخدمة، أو علاقة دائرية. "
        f"يضاف إليهم {disconnected} موظف منقطعون بسبب خلل في مستوى أعلى.")
    kpi(c[3], "Organizational Findings", f"{len(ctx.findings):,}",
        " · ".join(f"{sev}: {int((ctx.findings['severity'] == sev).sum())}" for sev in SEVERITIES))

    st.subheader("إجابات الأشعة السينية")
    st.caption("كل إجابة محسوبة مباشرة من البيانات الحالية (مع الفلاتر)، والأدلة التفصيلية في الصفحات المشار إليها.")
    qa = key_questions(ctx.model, df, ctx.findings, s)
    cols = st.columns(3)
    for i, item in enumerate(qa):
        cols[i % 3].markdown(
            f"<div class='xr-qa'><div class='q'>{html.escape(item['question'])}</div>"
            f"<div class='a'>{html.escape(item['answer'])}</div>"
            f"<div class='e'>{html.escape(item['evidence'])} · <i>{item['page']}</i></div></div>",
            unsafe_allow_html=True)

    st.subheader("التوزيع والهيكل")
    left, right = st.columns(2)
    with left:
        st.markdown("**توزيع الموظفين على الطبقات (Job Level)**")
        st.plotly_chart(layer_bars(layer_metrics(df, "job_level")), width="stretch")
    with right:
        st.markdown("**توزيع Span of Control**")
        if len(spans):
            st.plotly_chart(span_histogram(spans, s.low_span_threshold, s.high_span_threshold,
                                           float(spans.median())), width="stretch")
        else:
            empty_state("لا يوجد مديرون ضمن الفلاتر الحالية.")
    left, right = st.columns(2)
    with left:
        st.markdown("**توزيع الموظفين على الإدارات**")
        st.plotly_chart(department_distribution(df), width="stretch")
    with right:
        st.markdown("**الهيكل الإداري: Business Unit → Division → Department**")
        st.plotly_chart(structure_sunburst(df), width="stretch")
    st.markdown("**Organizational Findings حسب النوع ومستوى الأهمية**")
    st.plotly_chart(findings_by_type(ctx.findings), width="stretch")
