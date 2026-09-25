"""What-If Simulator."""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from analytics.anomalies import detect_findings
from analytics.hierarchy import department_heads
from analytics.simulations import SimulationError, apply_scenario, compare
from ui.common import page_header, table
from ui.state import context
from utils.config import LEVEL_NAMES

ACTION_LABELS = {
    "merge_departments": "دمج إدارات",
    "remove_layer": "إزالة طبقة إدارية",
    "move_employee": "نقل موظف",
    "remove_manager": "إزالة مدير",
}


def _describe(a: dict) -> str:
    t = a["type"]
    if t == "merge_departments":
        return (f"دمج {' + '.join(a['departments'])} → {a['new_name']}"
                + (" (توحيد القيادة)" if a.get("consolidate_heads") else ""))
    if t == "remove_layer":
        return (f"إزالة المديرين في Job Level {a['job_level']} ({LEVEL_NAMES.get(a['job_level'], '')})"
                + (f" في {a['department']}" if a.get("department") else " في كل المنظمة"))
    if t == "move_employee":
        return f"نقل {a['employee_id']} إلى المدير {a['new_manager_id']}"
    if t == "remove_manager":
        return f"إزالة المدير {a['manager_id']} → المستلم: {a['reassign_to']}"
    return json.dumps(a, ensure_ascii=False)


def _add(action: dict) -> None:
    st.session_state.scenario = st.session_state.scenario + [action]


def _labels(df: pd.DataFrame) -> dict[str, str]:
    return {r.node_id: f"{r.node_id} · {r.employee_name} · {r.job_title} · {r.department}"
            for r in df.itertuples()}


def _builder(ctx) -> None:
    model = ctx.model
    df = model.df
    act = df[df["is_active"]]
    heads = department_heads(model)
    depts = sorted(heads)
    t1, t2, t3, t4 = st.tabs(list(ACTION_LABELS.values()))

    with t1:
        sel = st.multiselect("الإدارات المراد دمجها (الأولى = الإدارة الأساسية)", depts, key="sim_mg_depts",
                             max_selections=6)
        name = st.text_input("اسم الإدارة الجديدة", value=" & ".join(sel), key=f"sim_mg_name_{'|'.join(sel)}")
        cons = st.checkbox("توحيد القيادة: نقل فرق رؤساء الإدارات الأخرى إلى رئيس الإدارة الأساسية "
                           "وحذف وظائفهم", key="sim_mg_cons")
        if sel:
            h = heads.get(sel[0])
            st.caption(f"رئيس الإدارة الأساسية: {h} · {model.node(h)['employee_name']} · "
                       f"{model.node(h)['job_title']}" if h else "")
        if st.button("➕ أضف إلى السيناريو", key="sim_mg_add", disabled=len(sel) < 2):
            _add({"type": "merge_departments", "departments": sel, "new_name": name,
                  "consolidate_heads": cons})
            st.rerun()

    with t2:
        c1, c2 = st.columns(2)
        lvl = c1.selectbox("Job Level", [1, 2, 3, 4, 5], index=3, key="sim_ly_lvl",
                           format_func=lambda v: f"{v} · {LEVEL_NAMES[v]}")
        dept = c2.selectbox("النطاق", [None] + depts, key="sim_ly_dept",
                            format_func=lambda v: "كل المنظمة" if v is None else v)
        n = act[act["is_manager"] & act["job_level"].eq(lvl)]
        if dept:
            n = n[n["department"].eq(dept)]
        st.caption(f"سيتم حذف {len(n)} وظيفة إشرافية، ونقل {int(n['direct_reports'].sum())} موظف "
                   f"و{int(n['vacant_direct_positions'].sum())} وظيفة شاغرة (تابعين مباشرين) إلى "
                   "المدير الأعلى التالي في سلسلتهم.")
        if st.button("➕ أضف إلى السيناريو", key="sim_ly_add", disabled=n.empty):
            _add({"type": "remove_layer", "job_level": int(lvl), "department": dept})
            st.rerun()

    with t3:
        labels = _labels(act.sort_values("node_id"))
        emp = st.selectbox("الموظف", list(labels), format_func=labels.get, key="sim_mv_emp")
        cur = model.node(emp)
        st.caption(f"المدير الحالي: {cur['manager_id'] or '—'} · {cur['manager_name'] or ''}")
        new = st.selectbox("المدير الجديد", [k for k in labels if k != emp], format_func=labels.get,
                           key="sim_mv_new")
        mvd = st.checkbox("نقل الموظف إلى إدارة المدير الجديد", value=True, key="sim_mv_dept")
        if st.button("➕ أضف إلى السيناريو", key="sim_mv_add"):
            _add({"type": "move_employee", "employee_id": emp, "new_manager_id": new,
                  "move_department": mvd})
            st.rerun()

    with t4:
        mgrs = _labels(act[act["is_manager"] & act["node_id"].ne(model.ceo_id)]
                       .sort_values("direct_reports"))
        mid = st.selectbox("المدير المراد إزالته", list(mgrs), format_func=mgrs.get, key="sim_rm_mgr")
        m = model.node(mid)
        head = heads.get(m["department"])
        st.caption(f"لديه {int(m['direct_reports'])} موظف مباشر · مديره: {m['manager_id']} · "
                   f"رئيس الإدارة: {head}")
        choice = st.radio("من سيستلم الموظفين؟",
                          ["manager_of_removed", "department_head", "specific"], key="sim_rm_choice",
                          format_func={"manager_of_removed": f"المدير الأعلى ({m['manager_id']})",
                                       "department_head": f"رئيس الإدارة ({head})",
                                       "specific": "مدير آخر / ترقية أحد الموظفين المباشرين"}.get)
        target = choice
        if choice == "specific":
            directs = model.direct_report_ids(mid)
            cand = act[act["node_id"].ne(mid)]
            order = directs + [n for n in cand["node_id"] if n not in set(directs)]
            lab = _labels(cand.set_index("node_id").loc[order].reset_index())
            target = st.selectbox("المستلم (الموظفون المباشرون أولًا = ترقية)", order,
                                  format_func=lab.get, key="sim_rm_target")
        if st.button("➕ أضف إلى السيناريو", key="sim_rm_add"):
            _add({"type": "remove_manager", "manager_id": mid, "reassign_to": target})
            st.rerun()


def _run(ctx, actions: list[dict]):
    key = (ctx.token, json.dumps(actions, sort_keys=True), ctx.settings.cache_key())
    cache = st.session_state.setdefault("_sim_cache", {})
    if key not in cache:
        cache.clear()
        with st.spinner("Running simulation on a copy of the data…"):
            res = apply_scenario(ctx.model.df, actions, ctx.model)
            cmp = compare(ctx.model, res.model, ctx.settings)
            f_after = detect_findings(res.model, ctx.settings)
        cache[key] = (res, cmp, f_after)
    return cache[key]


def render() -> None:
    ctx = context()
    page_header("What-If Simulator",
                "جرّب تغييرات افتراضية على نسخة من البيانات وقارن النتائج قبل التطبيق الفعلي. "
                "البيانات الأصلية لا تتغير.")
    st.caption("المحاكاة تعمل على كامل المنظمة (بدون الفلاتر العامة).")
    _builder(ctx)

    st.subheader("السيناريو")
    scen = st.session_state.scenario
    if not scen:
        st.info("أضف إجراءً واحدًا أو أكثر لبدء المحاكاة. يمكن جمع عدة إجراءات في سيناريو واحد.")
        return
    for i, a in enumerate(scen):
        c1, c2 = st.columns([10, 1])
        c1.markdown(f"{i + 1}. {_describe(a)}")
        if c2.button("✕", key=f"sim_del_{i}_{len(scen)}"):
            st.session_state.scenario = scen[:i] + scen[i + 1:]
            st.rerun()
    c1, c2 = st.columns([1, 1])
    if c1.button("مسح السيناريو", key="sim_clear"):
        st.session_state.scenario = []
        st.rerun()
    c2.download_button("⬇ Scenario JSON", json.dumps(scen, ensure_ascii=False, indent=2),
                       "scenario.json", "application/json")

    try:
        res, cmp, f_after = _run(ctx, scen)
    except SimulationError as exc:
        st.error(f"تعذر تطبيق السيناريو: {exc}")
        return
    for line in res.log:
        st.caption(line)

    st.subheader("Before / After")
    summ = cmp["summary"][["Metric", "Before (fmt)", "After (fmt)"]].rename(
        columns={"Before (fmt)": "BEFORE", "After (fmt)": "AFTER"})
    summ["Δ"] = ["" if b == a else "●" for b, a in zip(summ["BEFORE"], summ["AFTER"])]
    left, right = st.columns([1, 1])
    with left:
        table(summ, "sim_summary", "scenario_before_after", rename=False,
              height=35 * (len(summ) + 1) + 3)
    with right:
        st.markdown("**ما الذي تغير؟**")
        lines = cmp["narrative"]
        if lines:
            st.markdown("<div class='ltr'>" + "<br>".join(lines[:40]) + "</div>",
                        unsafe_allow_html=True)
            if len(lines) > 40:
                st.caption(f"… و{len(lines) - 40} تغييرات أخرى في الجداول أدناه.")
        else:
            st.caption("لا توجد تغييرات في المؤشرات.")

    last = scen[-1]
    if last["type"] == "move_employee":
        _move_focus(ctx, res, cmp, last)

    t1, t2, t3, t4 = st.tabs(["Span of Control", "Departments", "Organizational Depth", "Findings"])
    with t1:
        table(cmp["span_changes"], "sim_spans", "scenario_span_changes")
    with t2:
        table(cmp["department_changes"], "sim_depts", "scenario_department_changes", rename=False)
    with t3:
        dc = cmp["depth_changes"]
        st.caption(f"{len(dc)} موظف تغير عمقهم.")
        table(dc, "sim_depth", "scenario_depth_changes")
    with t4:
        fb = ctx.findings_all["type"].value_counts()
        fa = f_after["type"].value_counts()
        comp = pd.DataFrame({"Before": fb, "After": fa}).fillna(0).astype(int)
        comp["Change"] = comp["After"] - comp["Before"]
        table(comp.reset_index(names="Finding Type"), "sim_findings", "scenario_findings",
              rename=False)


def _move_focus(ctx, res, cmp, a: dict) -> None:
    st.subheader("أثر نقل الموظف")
    before, after = ctx.model, res.model
    emp = a["employee_id"]
    old_mgr = before.node(emp)["manager_id"]
    rows = []
    for label, nid in [("المدير الحالي", old_mgr), ("المدير الجديد", a["new_manager_id"])]:
        b, af = before.node(nid), after.node(nid)
        rows.append({"Role": label, "Manager": nid,
                     "Span Before": None if b is None else int(b["direct_reports"]),
                     "Span After": None if af is None else int(af["direct_reports"])})
    st.markdown("**Span of Control قبل وبعد**")
    table(pd.DataFrame(rows), "sim_mv_span", rename=False)
    sub = [emp] + before.subtree_ids(emp, include_root=False)
    b = before.df.set_index("node_id").loc[sub, ["employee_name", "depth", "department"]]
    af = after.df[~after.df["is_duplicate_id"]].set_index("node_id").reindex(sub)[["depth", "department"]]
    d = b.rename(columns={"depth": "Depth Before", "department": "Department Before"})
    d["Depth After"] = af["depth"]
    d["Department After"] = af["department"]
    st.markdown("**Organizational Depth قبل وبعد (الموظف وفريقه)**")
    table(d.reset_index(), "sim_mv_depth", rename=False)
    st.markdown("**Department distribution قبل وبعد**")
    dc = cmp["department_changes"]
    table(dc[["department", "headcount_before", "headcount_after"]] if len(dc) else dc,
          "sim_mv_dept", rename=False)
