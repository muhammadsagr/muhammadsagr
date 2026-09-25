"""Export results to Excel / CSV."""
from __future__ import annotations

import streamlit as st

from exports.exporter import build_export_tables, to_csv_bytes, to_excel_bytes
from ui.common import page_header
from ui.state import context


def render() -> None:
    ctx = context()
    page_header("Export", "تصدير النتائج إلى Excel أو CSV", ctx)
    use_filters = st.toggle("تطبيق الفلاتر العامة على التصدير", value=ctx.filtered,
                            disabled=not ctx.filtered, key="exp_filters")
    df = ctx.df if use_filters else ctx.model.df
    findings = ctx.findings if use_filters else ctx.findings_all
    with st.spinner("Preparing export…"):
        sheets = build_export_tables(ctx.model, findings, ctx.settings, df)
    st.markdown("**ملف Excel واحد يحتوي على الأوراق التالية:**")
    st.markdown("<div class='ltr'>" + " · ".join(f"{k} ({len(v):,})" for k, v in sheets.items())
                + "</div>", unsafe_allow_html=True)
    st.download_button("⬇ Download Excel (organizational_xray.xlsx)", to_excel_bytes(sheets),
                       "organizational_xray.xlsx", type="primary",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.subheader("CSV")
    name = st.selectbox("الجدول", list(sheets), key="exp_csv_sheet")
    st.dataframe(sheets[name].head(200), hide_index=True, width="stretch", height=320)
    st.download_button(f"⬇ {name}.csv", to_csv_bytes(sheets[name]),
                       f"{name.lower().replace(' ', '_')}.csv", "text/csv")
    st.caption("كل جدول في التطبيق يحتوي أيضًا على زر ⬇ CSV خاص به.")
