"""Import validation: decides whether an uploaded file can be analysed and
lists everything the user should know before trusting the results."""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from data.loader import map_columns, normalize
from utils.config import (
    EMPLOYMENT_STATUSES,
    IMPORT_REQUIRED_COLUMNS,
    POSITION_STATUSES,
    STRUCTURALLY_REQUIRED,
)


@dataclass
class ValidationIssue:
    level: str  # Error | Warning | Info
    field: str
    message: str
    count: int = 0
    rows: list[int] = field(default_factory=list)  # 1-based source row numbers


@dataclass
class ValidationReport:
    issues: list[ValidationIssue]
    column_mapping: dict[str, str]
    missing_columns: list[str]
    n_rows: int

    @property
    def ok(self) -> bool:
        return not any(i.level == "Error" for i in self.issues)

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame([{
            "Level": i.level, "Field": i.field, "Message": i.message, "Count": i.count,
            "Rows (first 20)": ", ".join(map(str, i.rows[:20])),
        } for i in self.issues], columns=["Level", "Field", "Message", "Count", "Rows (first 20)"])


def _has_value(s: pd.Series) -> pd.Series:
    txt = s.astype("object").map(lambda v: "" if pd.isna(v) else str(v).strip())
    return ~txt.isin(["", "nan", "None", "NaN", "NaT", "<NA>"])


def validate(raw: pd.DataFrame) -> ValidationReport:
    issues: list[ValidationIssue] = []
    mapping = map_columns(raw.columns)
    present = set(mapping.values())
    missing = [c for c in IMPORT_REQUIRED_COLUMNS if c not in present]

    if raw.empty:
        issues.append(ValidationIssue("Error", "*", "الملف لا يحتوي على أي سجلات."))
        return ValidationReport(issues, mapping, missing, 0)
    for col in missing:
        level = "Error" if col in STRUCTURALLY_REQUIRED else "Warning"
        issues.append(ValidationIssue(level, col, f"العمود المطلوب '{col}' غير موجود في الملف."
                                      + ("" if level == "Error" else " سيتم إنشاؤه فارغًا.")))
    unmapped = [c for c in raw.columns if c not in mapping]
    if unmapped:
        issues.append(ValidationIssue("Info", "*", "أعمدة إضافية لم يتم التعرف عليها وسيتم الاحتفاظ بها: "
                                      + ", ".join(map(str, unmapped[:15])), len(unmapped)))
    if any(i.level == "Error" for i in issues):
        return ValidationReport(issues, mapping, missing, len(raw))

    df = normalize(raw)

    def add(level, fld, msg, mask):
        n = int(mask.sum())
        if n:
            issues.append(ValidationIssue(level, fld, msg, n, df.loc[mask, "row_number"].tolist()))

    add("Warning", "employee_id", "Employee ID مكرر (سيتم استبعاد التكرارات من التحليل الهيكلي).",
        df["employee_id"].ne("") & df["employee_id"].duplicated(keep=False))
    add("Warning", "employee_id", "سجل موظف (وظيفة مشغولة) بدون Employee ID.",
        ~df["is_vacant"] & df["employee_id"].eq(""))
    ids = set(df["node_id"])
    add("Warning", "manager_id", "Manager ID غير موجود ضمن أرقام الموظفين.",
        df["manager_id"].ne("") & ~df["manager_id"].isin(ids))
    add("Warning", "manager_id", "الموظف مسجل كمدير لنفسه.", df["manager_id"].eq(df["node_id"]))
    roots = df["is_active"] & df["manager_id"].eq("")
    if roots.sum() == 0:
        issues.append(ValidationIssue("Warning", "manager_id",
                                      "لا يوجد موظف نشط بدون مدير؛ لا يمكن تحديد الـCEO وسيتعذر حساب العمق."))
    elif roots.sum() > 1:
        add("Info", "manager_id", "أكثر من موظف نشط بدون مدير؛ سيتم اختيار الـCEO تلقائيًا "
            "واعتبار الباقين Orphan Employees.", roots)

    raw_norm = raw.rename(columns=mapping)
    for col in ("salary", "job_level", "age"):
        if col in raw_norm.columns:
            had_value = _has_value(raw_norm[col])
            add("Warning", col, f"قيم غير رقمية في {col} تم تحويلها إلى فارغ.",
                had_value.values & df[col].isna().values)
    if "hire_date" in raw_norm.columns:
        add("Warning", "hire_date", "تواريخ توظيف غير قابلة للقراءة.",
            _has_value(raw_norm["hire_date"]).values & df["hire_date"].isna().values)
    add("Warning", "employment_status",
        f"حالة وظيفية غير معروفة (المسموح: {', '.join(EMPLOYMENT_STATUSES)}).",
        ~df["is_vacant"] & ~df["employment_status"].isin(EMPLOYMENT_STATUSES))
    add("Warning", "position_status",
        f"Position Status غير معروف (المسموح: {', '.join(POSITION_STATUSES)}).",
        ~df["position_status"].isin(POSITION_STATUSES))
    if not issues or all(i.level == "Info" for i in issues):
        issues.append(ValidationIssue("Info", "*", "لم يتم العثور على مشكلات تمنع التحليل."))
    return ValidationReport(issues, mapping, missing, len(raw))
