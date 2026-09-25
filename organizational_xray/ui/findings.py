"""X-Ray Findings with full explainability."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from analytics.anomalies import TYPE_LABELS_AR, explain_finding
from ui.common import empty_state, kpi, page_header, severity_label, table
from ui.state import context
from utils.config import FINDING_TYPES, SEVERITIES
from visualization.dashboards import findings_by_type

LIST_COLS = ["finding_id", "type", "severity", "entity_type", "entity_id", "entity_name",
             "department", "description", "evidence", "recommended_investigation"]


def _fmt_value(v, threshold=False):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    return str(v)


def render() -> None:
    ctx = context()
    page_header("X-Ray Findings",
                "ملاحظات تنظيمية مكتشفة آليًا. كل ملاحظة تستدعي المراجعة ولا تمثل حكمًا نهائيًا.", ctx)
    f = ctx.findings
    if f.empty:
        empty_state("لا توجد ملاحظات.")
        return
    c = st.columns(5)
    kpi(c[0], "Findings", f"{len(f):,}")
    for col, sev in zip(c[1:], SEVERITIES):
        kpi(col, severity_label(sev), f"{int((f['severity'] == sev).sum()):,}")

    c1, c2, c3, c4 = st.columns([1.3, 1, 1.2, 1.5])
    types = c1.multiselect("Type", [t for t in FINDING_TYPES if t in set(f["type"])],
                           key="fd_type", placeholder="All",
                           format_func=lambda t: f"{t} · {TYPE_LABELS_AR.get(t, '')}")
    sevs = c2.multiselect("Severity", SEVERITIES, key="fd_sev", placeholder="All")
    depts = c3.multiselect("Department", sorted(v for v in f["department"].unique() if v),
                           key="fd_dept", placeholder="All")
    q = c4.text_input("بحث في النص / المعرفات", key="fd_q")
    view = f
    if types:
        view = view[view["type"].isin(types)]
    if sevs:
        view = view[view["severity"].isin(sevs)]
    if depts:
        view = view[view["department"].isin(depts)]
    if q:
        hay = view[["finding_id", "entity_id", "entity_name", "description", "evidence"]] \
            .fillna("").astype(str).agg(" ".join, axis=1)
        view = view[hay.str.contains(q, case=False, regex=False)]

    with st.expander("توزيع الملاحظات حسب النوع", expanded=False):
        st.plotly_chart(findings_by_type(view), width="stretch")

    st.caption(f"{len(view):,} ملاحظة. اختر صفًا لعرض التفسير الكامل (Explainability).")
    shown = view[LIST_COLS].copy()
    shown["severity"] = shown["severity"].map(severity_label)
    event = table(shown, "findings_table", "xray_findings", height=380,
                  on_select="rerun", selection_mode="single-row")
    sel_rows = event.selection.rows if event is not None else []
    options = view["finding_id"].tolist()
    if not options:
        return
    default = options[sel_rows[0]] if sel_rows else options[0]
    fid = st.selectbox("Finding", options, index=options.index(default), key=f"fd_sel_{default}")
    _explain(ctx, fid)


def _explain(ctx, fid: str) -> None:
    e = explain_finding(ctx.findings_all, fid, ctx.model)
    st.subheader(f"{e['finding_id']} · {e['type']}")
    st.markdown(f"**{severity_label(e['severity'])}** · {e['entity_type']}: `{e['entity_id']}` — "
                f"{e['entity_name']} · Department: {e['department'] or '—'}")
    st.markdown(e["description"])
    c = st.columns(4)
    c[0].metric("Metric", e["metric"] or "—", border=True)
    c[1].metric("Value", _fmt_value(e["value"]), border=True)
    c[2].metric("Configured Threshold", _fmt_value(e["threshold"]), border=True)
    c[3].metric("Benchmark", e["benchmark"] or "—", border=True)
    st.markdown("**Evidence**")
    st.info(e["evidence"])
    st.markdown("**Rule**")
    st.code(e["rule"], language=None)
    st.markdown("**Recommended Investigation**")
    st.markdown(e["recommended_investigation"])
    recs = e["records"]
    st.markdown(f"**السجلات المصدرية ({len(recs)})**")
    cols = ["row_number", "node_id", "employee_name", "job_title", "job_level", "department",
            "manager_id", "manager_name", "employment_status", "position_id", "position_status",
            "depth", "direct_reports", "total_reports", "reporting_status"]
    table(recs[cols], f"fd_records", f"evidence_{fid}", height=300)
