"""Organization Map (Employee → Manager network)."""
from __future__ import annotations

import streamlit as st

from ui.common import empty_state, page_header, table
from ui.state import context
from visualization.network import SCOPES, network_figure, select_nodes


def render() -> None:
    ctx = context()
    page_header("Organization Map", "الشبكة التنظيمية Employee → Manager (NetworkX + Plotly)")
    st.caption("الخريطة تُرسم دائمًا على كامل البيانات حتى تبقى السلاسل الإدارية مكتملة؛ "
               "استخدم النطاق أدناه لاختيار الجزء المعروض.")
    model, s = ctx.model, ctx.settings
    df = model.df

    c1, c2 = st.columns([1, 2])
    scope = c1.radio("النطاق", SCOPES, key="net_scope")
    value = None
    with c2:
        if scope in ("Business Unit", "Division", "Department"):
            col = {"Business Unit": "business_unit", "Division": "division",
                   "Department": "department"}[scope]
            vals = sorted(v for v in df.loc[df["is_active"], col].unique() if v)
            value = st.selectbox(scope, vals, key=f"net_val_{col}")
        elif scope == "Specific Manager":
            mgr = df[df["is_manager"]].sort_values("total_reports", ascending=False)
            labels = {r.node_id: f"{r.node_id} · {r.employee_name} · {r.job_title} "
                                 f"({r.total_reports} reports)" for r in mgr.itertuples()}
            value = st.selectbox("Manager", list(labels), format_func=labels.get, key="net_mgr")
        o1, o2, o3, o4 = st.columns(4)
        managers_only = o1.toggle("Managers only", value=(scope == "Entire Organization"),
                                  key=f"net_mo_{scope}",
                                  help="عرض المديرين فقط يجعل خريطة المنظمة كاملة مقروءة.")
        include_vacant = o2.toggle("Show vacancies", value=False, key="net_vac")
        levels = o3.number_input("Max levels", 1, 15, 15 if scope != "Entire Organization" else 8,
                                 key=f"net_lv_{scope}")
        color_by = o4.selectbox("Color by", ["span", "depth"], key="net_color",
                                format_func={"span": "Span category", "depth": "Depth"}.get)

    sel = select_nodes(model, scope, value, managers_only, int(levels), s.max_network_nodes,
                       include_vacant)
    if not sel.nodes:
        empty_state("لا توجد عقد للعرض في هذا النطاق.")
        return
    msg = f"عرض {len(sel.nodes):,} من أصل {sel.total_in_scope:,} عقدة في النطاق."
    if sel.truncated:
        msg += (f" تم الاقتصار على أول {sel.levels_shown + 1} مستويات للحفاظ على وضوح الرسم "
                f"(الحد الأقصى {s.max_network_nodes} عقدة، قابل للتعديل من Settings).")
    st.caption(msg)
    st.plotly_chart(network_figure(model, sel, color_by, s.low_span_threshold,
                                   s.high_span_threshold), width="stretch",
                    config={"scrollZoom": True})
    st.caption("حجم العقدة ∝ إجمالي التابعين. مرّر المؤشر على أي عقدة لعرض التفاصيل؛ استخدم العجلة للتكبير.")
    with st.expander("العقد المعروضة (جدول)"):
        nodes = df[df["node_id"].isin(sel.nodes)][
            ["node_id", "employee_name", "job_title", "department", "manager_id", "depth",
             "direct_reports", "total_reports", "reporting_status"]]
        table(nodes, "network_nodes", height=320)
