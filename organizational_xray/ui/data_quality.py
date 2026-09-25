"""Data Quality."""
from __future__ import annotations

import streamlit as st

from analytics.data_quality import affected_records, dimension_scores, overall_score
from ui.common import kpi, page_header, table
from ui.state import cached_quality, context
from utils.helpers import pct

RECORD_COLS = ["row_number", "node_id", "employee_id", "employee_name", "job_title", "job_level",
               "department", "division", "manager_id", "manager_name", "employment_status",
               "position_id", "position_status", "salary", "hire_date", "reporting_status"]


def render() -> None:
    ctx = context()
    page_header("Data Quality", "Completeness · Uniqueness · Validity · Consistency · Referential Integrity")
    st.caption("تُحسب جودة البيانات على كامل الملف (بدون الفلاتر العامة) حتى لا تُخفى السجلات المعيبة.")
    checks = cached_quality(ctx.token, ctx.model)
    dims = dimension_scores(checks)
    c = st.columns(len(dims) + 1)
    kpi(c[0], "Overall", pct(overall_score(checks)), "نسبة الفحوص الناجحة على مستوى السجلات.")
    for col, r in zip(c[1:], dims.itertuples()):
        kpi(col, r.dimension, pct(r.score), f"{r.failed} سجل غير مطابق من {r.records:,} فحص")

    st.subheader("المقاييس")
    st.caption("اختر أي مقياس لعرض السجلات المتأثرة.")
    view = checks.drop(columns=["failing_rows", "error"])
    status_icon = {"Pass": "✅ Pass", "Warning": "🟡 Warning", "Fail": "🔴 Fail"}
    view = view.assign(status=view["status"].map(status_icon))
    event = table(view, "dq_checks", "data_quality_checks", height=420, on_select="rerun",
                  selection_mode="single-row")
    rows = event.selection.rows if event is not None else []
    failing = checks[checks["failed"] > 0]
    default_id = checks.iloc[rows[0]]["check_id"] if rows else \
        (failing.iloc[0]["check_id"] if len(failing) else checks.iloc[0]["check_id"])
    ids = checks["check_id"].tolist()
    names = dict(zip(checks["check_id"], checks["check"]))
    cid = st.selectbox("المقياس", ids, index=ids.index(default_id),
                       format_func=lambda i: f"{i} · {names[i]}", key=f"dq_sel_{default_id}")
    chk = checks[checks["check_id"].eq(cid)].iloc[0]
    st.markdown(f"**{chk['check']}** — {chk['rule']} · Score: **{pct(chk['score'])}** "
                f"({chk['failed']} من {chk['records_checked']:,})")
    recs = affected_records(ctx.model, checks, cid)
    if recs.empty:
        st.success("لا توجد سجلات متأثرة.")
    else:
        table(recs[RECORD_COLS], "dq_records", f"dq_{cid}", height=320)
