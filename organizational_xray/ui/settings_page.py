"""Settings: user-adjustable thresholds."""
from __future__ import annotations

import json

import streamlit as st

from ui.common import page_header
from utils.config import SETTING_DESCRIPTIONS, Settings


def render() -> None:
    page_header("Settings", "حدود التحليل (Thresholds). تُطبق فورًا على كل الصفحات والـFindings.")
    cur: Settings = st.session_state.settings
    d = Settings()
    with st.form("settings_form"):
        c1, c2 = st.columns(2)
        low = c1.number_input("Low Span Threshold", 0, 50, cur.low_span_threshold,
                              help=SETTING_DESCRIPTIONS["low_span_threshold"])
        high = c2.number_input("High Span Threshold", 1, 200, cur.high_span_threshold,
                               help=SETTING_DESCRIPTIONS["high_span_threshold"])
        deep = c1.number_input("Deep Hierarchy Threshold", 1, 30, cur.deep_hierarchy_threshold,
                               help=SETTING_DESCRIPTIONS["deep_hierarchy_threshold"])
        small = c2.number_input("Small Department Threshold", 0, 100, cur.small_department_threshold,
                                help=SETTING_DESCRIPTIONS["small_department_threshold"])
        ratio = c1.number_input("High Management Ratio (%)", 1.0, 100.0,
                                round(cur.high_management_ratio * 100, 1), step=1.0,
                                help=SETTING_DESCRIPTIONS["high_management_ratio"])
        sim = c2.slider("Title Similarity Threshold", 0.5, 1.0, float(cur.title_similarity_threshold),
                        0.01, help=SETTING_DESCRIPTIONS["title_similarity_threshold"])
        excl = c1.checkbox("استثناء CEO و C-Suite من ملاحظات Span of Control",
                           cur.exclude_executives_from_span)
        nodes = c2.number_input("Max network nodes", 50, 5000, cur.max_network_nodes, step=50,
                                help=SETTING_DESCRIPTIONS["max_network_nodes"])
        saved = st.form_submit_button("حفظ الإعدادات", type="primary")
    if saved:
        if low >= high:
            st.error("يجب أن يكون Low Span Threshold أقل من High Span Threshold.")
        else:
            st.session_state.settings = Settings(int(low), int(high), int(deep), int(small),
                                                 float(ratio) / 100, float(sim), bool(excl),
                                                 int(nodes))
            st.success("تم حفظ الإعدادات وإعادة حساب النتائج.")
    if st.button("استعادة القيم الافتراضية"):
        st.session_state.settings = Settings()
        st.rerun()

    st.subheader("القواعد الحالية")
    s = st.session_state.settings
    rules = [
        ("LOW_SPAN_OF_CONTROL", f"direct reports ≤ {s.low_span_threshold}"),
        ("HIGH_SPAN_OF_CONTROL", f"direct reports > {s.high_span_threshold}"),
        ("DEEP_HIERARCHY", f"depth to CEO > {s.deep_hierarchy_threshold}"),
        ("SMALL_DEPARTMENT", f"headcount ≤ {s.small_department_threshold}"),
        ("HIGH_MANAGEMENT_RATIO", f"managers ÷ headcount > {s.high_management_ratio:.0%} "
                                  f"(departments larger than {s.small_department_threshold})"),
        ("DUPLICATE_POSITION", f"duplicate Position ID, title variants, similarity ≥ {s.title_similarity_threshold:.2f}"),
    ]
    st.dataframe([{"Finding": r, "Rule": t} for r, t in rules], hide_index=True, width="stretch")
    st.caption(f"القيم الافتراضية: {json.dumps(d.as_dict())}")
