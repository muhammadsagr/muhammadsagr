"""Import Data: dummy data generation and CSV / Excel upload with validation."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from analytics.report import dataset_facts
from data.loader import read_uploaded
from data.validator import validate
from exports.exporter import to_csv_bytes, to_excel_bytes
from ui.common import page_header, table
from ui.state import load_dummy, load_uploaded
from utils.config import DISPLAY_NAMES, IMPORT_REQUIRED_COLUMNS

TEMPLATE_HEADERS = ["EmployeeID", "EmployeeName", "ManagerID", "JobTitle", "Department", "Division",
                    "BusinessUnit", "JobLevel", "Salary", "EmploymentStatus", "PositionID",
                    "PositionStatus", "Location", "Gender", "Age", "HireDate", "Grade",
                    "EmploymentType", "WorkArrangement", "PerformanceRating", "YearsOfService"]


@st.cache_data(show_spinner=False, max_entries=4)
def _facts(token: str, _raw: pd.DataFrame) -> dict:
    return dataset_facts(_raw)


def render() -> None:
    page_header("Import Data", "تحميل بيانات المنظمة (CSV / Excel) أو إنشاء بيانات وهمية")
    ds = st.session_state.dataset
    st.success(f"البيانات الحالية: {ds['source']}")

    t1, t2, t3 = st.tabs(["رفع ملف", "بيانات وهمية (Dummy Data)", "وصف البيانات الحالية"])
    with t1:
        st.markdown("الحقول الأساسية: " + ", ".join(f"`{h}`" for h in TEMPLATE_HEADERS[:12]))
        st.caption("يتم التعرف على أسماء الأعمدة الشائعة تلقائيًا (مثل Employee ID / employee_id / "
                   "رقم الموظف). الوظائف الشاغرة: صف بدون EmployeeID مع PositionStatus = Vacant.")
        tmpl = pd.DataFrame(columns=TEMPLATE_HEADERS)
        c1, c2 = st.columns(2)
        c1.download_button("⬇ قالب CSV", to_csv_bytes(tmpl), "org_xray_template.csv", "text/csv")
        c2.download_button("⬇ قالب Excel", to_excel_bytes({"Employees": tmpl}), "org_xray_template.xlsx")
        up = st.file_uploader("ملف CSV أو Excel", type=["csv", "xlsx", "xlsm"], key="imp_file")
        if up is not None:
            try:
                raw = read_uploaded(up.getvalue(), up.name)
            except Exception as exc:
                st.error(f"تعذر قراءة الملف: {exc}")
                return
            rep = validate(raw)
            st.markdown(f"**نتيجة التحقق (Validation)** — {rep.n_rows:,} سجل")
            mapping = pd.DataFrame({"Column in file": list(rep.column_mapping),
                                    "Mapped to": [DISPLAY_NAMES.get(v, v)
                                                  for v in rep.column_mapping.values()]})
            with st.expander("مطابقة الأعمدة", expanded=bool(rep.missing_columns)):
                st.dataframe(mapping, hide_index=True, width="stretch")
                if rep.missing_columns:
                    st.warning("أعمدة مطلوبة غير موجودة: " + ", ".join(
                        DISPLAY_NAMES.get(c, c) for c in rep.missing_columns))
            issues = rep.to_frame()
            icon = {"Error": "🔴 Error", "Warning": "🟡 Warning", "Info": "ℹ️ Info"}
            issues["Level"] = issues["Level"].map(icon)
            table(issues, "imp_issues", "validation_report", rename=False)
            st.markdown("**معاينة**")
            st.dataframe(raw.head(20), hide_index=True, width="stretch")
            if rep.ok:
                if st.button("تحميل البيانات للتحليل", type="primary", key="imp_load"):
                    load_uploaded(raw, up.name)
                    st.success("تم تحميل البيانات. انتقل إلى Dashboard.")
                    st.rerun()
            else:
                st.error("لا يمكن تحليل الملف قبل معالجة الأخطاء (Error) أعلاه. "
                         f"الأعمدة الأساسية للهيكل: {', '.join(IMPORT_REQUIRED_COLUMNS[:1])} و ManagerID.")

    with t2:
        st.markdown("يتم بناء الهيكل التنظيمي أولًا ثم توزيع موظفين (Faker) داخله، مع إدخال مشكلات "
                    "تنظيمية متعمدة يمكن للنظام اكتشافها.")
        c1, c2 = st.columns(2)
        n = c1.select_slider("عدد الموظفين التقريبي", [1500, 3000, 5000, 10000], value=1500, key="imp_n")
        seed = c2.number_input("Seed", 0, 10_000, 42, key="imp_seed")
        if st.button("إنشاء البيانات", type="primary", key="imp_gen"):
            load_dummy(int(n), int(seed))
            st.rerun()
        raw = ds["raw"]
        c1, c2 = st.columns(2)
        c1.download_button("⬇ البيانات الحالية CSV", to_csv_bytes(raw), "org_data.csv", "text/csv")
        c2.download_button("⬇ البيانات الحالية Excel", to_excel_bytes({"Employees": raw}),
                           "org_data.xlsx")

    with t3:
        f = _facts(ds["token"], ds["raw"])
        c = st.columns(4)
        c[0].metric("السجلات", f"{f['records']:,}", border=True)
        c[1].metric("الموظفون النشطون", f"{f['active_employees']:,}", border=True)
        c[2].metric("المديرون", f"{f['managers']:,}", border=True)
        c[3].metric("الطبقات", f"{f['layers']}", border=True)
        c = st.columns(4)
        c[0].metric("الإدارات", f"{f['departments']}", border=True)
        c[1].metric("القطاعات", f"{f['divisions']}", border=True)
        c[2].metric("الوظائف الشاغرة", f"{f['vacant_positions']}", border=True)
        c[3].metric("Findings", f"{f['findings_total']}", border=True)
        st.caption("الأرقام محسوبة ديناميكيًا من البيانات الحالية بالإعدادات الافتراضية.")
        if ds.get("manifest"):
            st.markdown("**المشكلات التي تم إدخالها عمدًا في البيانات الوهمية (Manifest) والنتيجة المتوقعة**")
            man = pd.DataFrame([{**m, "ids": ", ".join(m["ids"][:8]) + (" …" if len(m["ids"]) > 8 else "")}
                                for m in ds["manifest"]])
            table(man, "imp_manifest", "injected_issues", rename=False)
