"""Employee Explorer."""
from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from ui.common import kpi, page_header, severity_label, table
from ui.state import context
from utils.config import LEVEL_NAMES
from utils.helpers import fmt_num

REPORT_COLS = ["node_id", "employee_name", "job_title", "job_level", "department", "manager_id",
               "depth", "direct_reports", "total_reports", "position_status", "reporting_status"]


def render() -> None:
    ctx = context()
    page_header("Employee Explorer", "ابحث عن موظف لعرض سلسلته الإدارية والموظفين التابعين له")
    model = ctx.model
    df = model.df[~model.df["is_duplicate_id"]]
    q = st.text_input("Search (Employee ID أو Employee Name)", key="exp_q",
                      placeholder="مثال: E10492 أو Smith")
    pool = df[df["is_active"] | df["is_vacant"] | df["employment_status"].eq("Terminated")]
    if q:
        m = (pool["node_id"].str.contains(q, case=False, regex=False)
             | pool["employee_name"].str.contains(q, case=False, regex=False))
        pool = pool[m]
    else:
        pool = pool.sort_values("total_reports", ascending=False)
    if pool.empty:
        st.warning("لا توجد نتائج مطابقة.")
        return
    st.caption(f"{len(pool):,} نتيجة" + (" (أول 300 معروضة)" if len(pool) > 300 else ""))
    options = pool.head(300)
    labels = {r.node_id: f"{r.node_id} · {r.employee_name or '(Vacant)'} · {r.job_title} · {r.department}"
              for r in options.itertuples()}
    emp_id = st.selectbox("Employee", list(labels), format_func=labels.get, key="exp_sel")
    r = model.node(emp_id)
    if r is None:
        return

    st.subheader(f"{r['employee_name'] or '(Vacant position)'} — {r['job_title']}")
    c = st.columns(6)
    kpi(c[0], "Position", r["position_id"] or "—", f"Position Status: {r['position_status']}")
    kpi(c[1], "Department", r["department"] or "—", f"{r['division']} · {r['business_unit']}")
    kpi(c[2], "Salary", fmt_num(r["salary"], 0))
    lvl = r["job_level"]
    kpi(c[3], "Job Level", "—" if pd.isna(lvl) else f"{int(lvl)} · {LEVEL_NAMES.get(int(lvl), '')}",
        f"Grade: {r['grade']}")
    kpi(c[4], "Years of Service", fmt_num(r["years_of_service"]))
    kpi(c[5], "Depth", fmt_num(r["depth"]), f"Reporting status: {r['reporting_status']}")
    st.caption(f"Employment: {r['employment_status']} · {r['employment_type']} · "
               f"{r['work_arrangement']} · {r['location']} · Performance: {fmt_num(r['performance_rating'])}")

    left, right = st.columns([1, 2])
    with left:
        st.markdown("**السلسلة الإدارية للأعلى**")
        chain = model.chain_up(emp_id)
        loop = len(chain) > 1 and chain[-1] in chain[:-1]
        parts = []
        for i, nid in enumerate(chain):
            n = model.node(nid)
            if n is None:
                body = f"<b>{html.escape(nid)}</b> — <i>غير موجود في البيانات</i>"
            else:
                status = "" if n["employment_status"] in ("Active", "On Leave", "") else \
                    f" <b>[{html.escape(n['employment_status'])}]</b>"
                body = (f"<b>{html.escape(nid)}</b> · {html.escape(n['employee_name'] or '(Vacant)')}"
                        f"{status}<br><small>{html.escape(n['job_title'])} · "
                        f"{html.escape(n['department'])}</small>")
            if loop and i == len(chain) - 1:
                body = f"↻ {body} <small>(circular reporting)</small>"
            cls = "node sel" if i == 0 else "node"
            parts.append(f"<div class='{cls}'>{body}</div>")
        tail = ""
        last = model.node(chain[-1])
        if not loop and last is not None and last["manager_id"] == "" and chain[-1] != model.ceo_id:
            tail = "<div class='arrow'>↑</div><div class='node'><i>لا يوجد Manager ID</i></div>"
        st.markdown("<div class='xr-chain'>" + "<div class='arrow'>↑</div>".join(parts) + tail +
                    "</div>", unsafe_allow_html=True)
        if chain[-1] == model.ceo_id:
            st.caption(f"تصل السلسلة إلى الـCEO في {len(chain) - 1} خطوة.")
        else:
            st.warning("السلسلة لا تصل إلى الـCEO.")
    with right:
        direct = model.direct_report_ids(emp_id, include_vacant=True)
        indirect = sorted(set(model.subtree_ids(emp_id, include_root=False, include_vacant=True))
                          - set(direct))
        st.markdown(f"**Direct Reports ({len(direct)})**")
        if direct:
            table(df[df["node_id"].isin(direct)][REPORT_COLS], "exp_direct", f"direct_reports_{emp_id}",
                  height=240)
        else:
            st.caption("لا يوجد.")
        st.markdown(f"**Indirect Reports ({len(indirect)})**")
        if indirect:
            table(df[df["node_id"].isin(indirect)][REPORT_COLS].sort_values("depth"),
                  "exp_indirect", f"indirect_reports_{emp_id}", height=260)
        else:
            st.caption("لا يوجد.")

    f = ctx.findings_all
    f = f[f["related_ids"].map(lambda ids: emp_id in ids)]
    if len(f):
        st.markdown(f"**Findings المرتبطة ({len(f)})**")
        v = f[["finding_id", "type", "severity", "description"]].copy()
        v["severity"] = v["severity"].map(severity_label)
        table(v, "exp_findings", f"findings_{emp_id}")
