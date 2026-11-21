"""أدوات حسابية (pandas) يستدعيها الـ Agents.

القاعدة: الـ Agent لا يحسب الأرقام بنفسه، بل يستدعي هذه الدوال ويفسّر نتائجها.
كل دالة تأخذ DataFrame (بعد الفلترة) وتُرجع قاموساً قابلاً للتحويل إلى JSON.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

POLICIES_DIR = Path(__file__).resolve().parent.parent / "policies"
MIN_SAMPLE = 5          # أقل حجم عينة لقبول مقارنة رواتب
GAP_THRESHOLD = 5.0     # فجوة الرواتب (%) التي تُعدّ لافتة


# ---------------------------------------------------------------- مساعدات
def _today(today: pd.Timestamp | None) -> pd.Timestamp:
    return (today or pd.Timestamp.today()).normalize()


def _filter_dept(df: pd.DataFrame, department: str | None) -> pd.DataFrame:
    if department:
        return df[df["القسم"] == department]
    return df


def _r(x, nd: int = 1):
    """تقريب آمن يحوّل أنواع numpy إلى أنواع بايثون."""
    if x is None or pd.isna(x):
        return None
    return round(float(x), nd)


def _dept_turnover_rates(df: pd.DataFrame, today: pd.Timestamp) -> pd.Series:
    """معدل الدوران السنوي لكل قسم = ترك العمل آخر 12 شهر ÷ النشطين × 100."""
    last_year = today - pd.DateOffset(years=1)
    active = df[df["الحالة"] == "نشط"].groupby("القسم").size()
    exits = df[df["تاريخ ترك العمل"] >= last_year].groupby("القسم").size()
    return (exits.reindex(active.index, fill_value=0) / active.clip(lower=1) * 100).fillna(0)


# ================================================================ محلل الدوران
def turnover_by_department(df: pd.DataFrame, today: pd.Timestamp | None = None) -> dict:
    today = _today(today)
    last_year = today - pd.DateOffset(years=1)
    rows = []
    for dept, g in df.groupby("القسم"):
        active = int((g["الحالة"] == "نشط").sum())
        exits_12m = int((g["تاريخ ترك العمل"] >= last_year).sum())
        rows.append({
            "القسم": dept,
            "النشطون": active,
            "إجمالي من ترك العمل": int((g["الحالة"] == "مستقيل").sum()),
            "ترك العمل آخر 12 شهر": exits_12m,
            "معدل الدوران السنوي %": _r(exits_12m / max(active, 1) * 100),
        })
    rows.sort(key=lambda r: r["معدل الدوران السنوي %"] or 0, reverse=True)
    active_all = int((df["الحالة"] == "نشط").sum())
    exits_all = int((df["تاريخ ترك العمل"] >= last_year).sum())
    return {
        "معدل الدوران العام %": _r(exits_all / max(active_all, 1) * 100),
        "الأقسام": rows,
    }


def exit_reasons_breakdown(df: pd.DataFrame, department: str | None = None) -> dict:
    exited = _filter_dept(df, department)
    exited = exited[exited["الحالة"] == "مستقيل"]
    total = len(exited)
    counts = exited["سبب ترك العمل"].value_counts()
    result = {
        "القسم": department or "كل الأقسام",
        "عدد من ترك العمل": total,
        "الأسباب": [
            {"السبب": reason, "العدد": int(n), "النسبة %": _r(n / max(total, 1) * 100)}
            for reason, n in counts.items()
        ],
    }
    if not department and total:
        top = exited.groupby("القسم")["سبب ترك العمل"].agg(lambda s: s.value_counts().index[0])
        result["السبب الأول في كل قسم"] = top.to_dict()
    return result


def turnover_trend_by_year(df: pd.DataFrame, department: str | None = None) -> dict:
    d = _filter_dept(df, department)
    hires = d.groupby(d["تاريخ التعيين"].dt.year).size()
    exits = d.dropna(subset=["تاريخ ترك العمل"]).groupby(d["تاريخ ترك العمل"].dt.year).size()
    years = sorted(set(hires.index) | set(exits.index))
    return {
        "القسم": department or "كل الأقسام",
        "السنوات": [
            {
                "السنة": int(y),
                "تعيينات": int(hires.get(y, 0)),
                "ترك العمل": int(exits.get(y, 0)),
                "الصافي": int(hires.get(y, 0) - exits.get(y, 0)),
            }
            for y in years
        ],
    }


def tenure_at_exit(df: pd.DataFrame, department: str | None = None) -> dict:
    exited = _filter_dept(df, department)
    exited = exited[exited["الحالة"] == "مستقيل"].copy()
    if exited.empty:
        return {"القسم": department or "كل الأقسام", "عدد من ترك العمل": 0}
    exited["المدة"] = (exited["تاريخ ترك العمل"] - exited["تاريخ التعيين"]).dt.days / 365.25
    buckets = pd.cut(exited["المدة"], [0, 1, 3, 5, 100], right=False,
                     labels=["أقل من سنة", "1-3 سنوات", "3-5 سنوات", "5 سنوات فأكثر"])
    dist = buckets.value_counts().reindex(buckets.cat.categories, fill_value=0)
    return {
        "القسم": department or "كل الأقسام",
        "عدد من ترك العمل": len(exited),
        "متوسط مدة الخدمة عند الترك (سنوات)": _r(exited["المدة"].mean()),
        "التوزيع": {k: int(v) for k, v in dist.items()},
        "متوسط المدة لكل قسم": {k: _r(v) for k, v in exited.groupby("القسم")["المدة"].mean().items()},
    }


# ================================================================ متنبئ الاستقالات
RISK_RULES = {
    "راتب أقل من متوسط نظرائه بأكثر من 10%": 30,
    "تقييم أداء منخفض (2 أو أقل)": 20,
    "ساعات تدريب قليلة (أقل من 15)": 15,
    "مدة خدمة بين سنة و3 سنوات": 15,
    "قسمه دورانه أعلى من المعدل العام": 20,
}


def risk_scores(df: pd.DataFrame, department: str | None = None, top_n: int = 10,
                today: pd.Timestamp | None = None) -> dict:
    """درجة خطر ترك العمل (0-100) بقواعد شفافة.

    لا تُستخدم الجنس أو العمر أو المدينة في الحساب إطلاقاً.
    """
    today = _today(today)
    active = df[df["الحالة"] == "نشط"].copy()
    if active.empty:
        return {"عدد الموظفين النشطين": 0, "الموظفون": []}

    peer_avg = active.groupby(["القسم", "المسمى الوظيفي"])["الراتب"].transform("mean")
    tenure = (today - active["تاريخ التعيين"]).dt.days / 365.25
    dept_rates = _dept_turnover_rates(df, today)
    overall = (df["تاريخ ترك العمل"] >= today - pd.DateOffset(years=1)).sum() / max(len(active), 1) * 100
    high_dept = active["القسم"].map(dept_rates).fillna(0) > overall

    flags = {
        "راتب أقل من متوسط نظرائه بأكثر من 10%": active["الراتب"] < peer_avg * 0.9,
        "تقييم أداء منخفض (2 أو أقل)": active["تقييم الأداء"] <= 2,
        "ساعات تدريب قليلة (أقل من 15)": active["ساعات التدريب"] < 15,
        "مدة خدمة بين سنة و3 سنوات": tenure.between(1, 3),
        "قسمه دورانه أعلى من المعدل العام": high_dept,
    }
    score = sum(mask.astype(int) * RISK_RULES[name] for name, mask in flags.items())
    active["درجة الخطر"] = score

    scope = _filter_dept(active, department)
    top = scope.sort_values(["درجة الخطر", "تقييم الأداء"], ascending=[False, True]).head(top_n)
    employees = [
        {
            "الرقم الوظيفي": row["الرقم الوظيفي"],
            "الاسم": row["الاسم"],
            "القسم": row["القسم"],
            "المسمى الوظيفي": row["المسمى الوظيفي"],
            "درجة الخطر": int(row["درجة الخطر"]),
            "الأسباب": [name for name, mask in flags.items() if mask.loc[idx]],
        }
        for idx, row in top.iterrows()
    ]
    return {
        "القسم": department or "كل الأقسام",
        "القواعد ونقاطها": RISK_RULES,
        "عدد الموظفين النشطين": len(scope),
        "عالي الخطر (60 فأكثر)": int((scope["درجة الخطر"] >= 60).sum()),
        "متوسط درجة الخطر": _r(scope["درجة الخطر"].mean()),
        "الموظفون": employees,
    }


# ================================================================ مراجع الرواتب
def salary_gap_by_gender(df: pd.DataFrame, department: str | None = None) -> dict:
    """فجوة الرواتب بين الجنسين داخل نفس القسم والمسمى الوظيفي (موظفون نشطون)."""
    active = _filter_dept(df[df["الحالة"] == "نشط"], department)
    groups = []
    for (dept, title), g in active.groupby(["القسم", "المسمى الوظيفي"]):
        m, f = g[g["الجنس"] == "ذكر"], g[g["الجنس"] == "أنثى"]
        sufficient = len(m) >= MIN_SAMPLE and len(f) >= MIN_SAMPLE
        gap = (m["الراتب"].mean() - f["الراتب"].mean()) / m["الراتب"].mean() * 100 if len(m) and len(f) else None
        groups.append({
            "القسم": dept,
            "المسمى الوظيفي": title,
            "عدد الذكور": len(m),
            "عدد الإناث": len(f),
            "متوسط راتب الذكور": _r(m["الراتب"].mean(), 0),
            "متوسط راتب الإناث": _r(f["الراتب"].mean(), 0),
            "الفجوة % (موجب = لصالح الذكور)": _r(gap),
            "العينة كافية": sufficient,
            "فجوة لافتة": bool(sufficient and gap is not None and abs(gap) > GAP_THRESHOLD),
        })
    groups.sort(key=lambda r: abs(r["الفجوة % (موجب = لصالح الذكور)"] or 0), reverse=True)
    return {
        "القسم": department or "كل الأقسام",
        "حد العينة الأدنى لكل جنس": MIN_SAMPLE,
        "حد الفجوة اللافتة %": GAP_THRESHOLD,
        "عدد المجموعات": len(groups),
        "مجموعات بفجوة لافتة": sum(g["فجوة لافتة"] for g in groups),
        "مجموعات عينتها غير كافية": sum(not g["العينة كافية"] for g in groups),
        "المجموعات (الأكبر فجوة أولاً)": groups[:15],
    }


def salary_by_education(df: pd.DataFrame, department: str | None = None) -> dict:
    active = _filter_dept(df[df["الحالة"] == "نشط"], department)
    order = ["ثانوية", "دبلوم", "بكالوريوس", "ماجستير", "دكتوراه"]
    rows = []
    for edu in order:
        g = active[active["المؤهل"] == edu]["الراتب"]
        if len(g):
            rows.append({"المؤهل": edu, "العدد": len(g), "متوسط الراتب": _r(g.mean(), 0),
                         "الوسيط": _r(g.median(), 0), "العينة كافية": len(g) >= MIN_SAMPLE})
    return {"القسم": department or "كل الأقسام", "المؤهلات": rows}


def salary_vs_performance(df: pd.DataFrame, department: str | None = None) -> dict:
    active = _filter_dept(df[df["الحالة"] == "نشط"], department)
    rows = [
        {"تقييم الأداء": int(p), "العدد": len(g), "متوسط الراتب": _r(g["الراتب"].mean(), 0)}
        for p, g in active.groupby("تقييم الأداء")
    ]
    varies = active["الراتب"].nunique() > 1 and active["تقييم الأداء"].nunique() > 1
    corr = active["الراتب"].corr(active["تقييم الأداء"]) if len(active) > 2 and varies else None
    return {
        "القسم": department or "كل الأقسام",
        "حسب التقييم": rows,
        "معامل الارتباط بين الراتب والأداء": _r(corr, 3),
    }


# ================================================================ مساعد السياسات
def list_policies() -> dict:
    files = sorted(POLICIES_DIR.glob("*.md"))
    return {"السياسات": [
        {"الملف": f.name, "العنوان": f.read_text(encoding="utf-8").splitlines()[0].lstrip("# ").strip()}
        for f in files
    ]}


def read_policy(file_name: str) -> dict:
    path = (POLICIES_DIR / file_name).resolve()
    if path.parent != POLICIES_DIR or path.suffix != ".md" or not path.exists():
        return {"خطأ": f"الملف غير موجود: {file_name}", "المتاح": [p["الملف"] for p in list_policies()["السياسات"]]}
    return {"الملف": path.name, "المحتوى": path.read_text(encoding="utf-8")}


# ================================================================ تعريفات الأدوات (JSON Schema)
_DEPT = {"department": {"type": "string", "description": "اسم القسم بالعربية كما في البيانات. اتركه فارغاً لكل الأقسام."}}


def _schema(name: str, description: str, props: dict | None = None, required: list | None = None) -> dict:
    return {
        "name": name,
        "description": description,
        "input_schema": {"type": "object", "properties": props or {}, "required": required or []},
    }


TOOL_SPECS = {
    "turnover_by_department": _schema(
        "turnover_by_department",
        "معدل الدوران السنوي لكل قسم (ترك العمل آخر 12 شهر ÷ النشطين) والمعدل العام، مرتبة من الأعلى."),
    "exit_reasons_breakdown": _schema(
        "exit_reasons_breakdown", "توزيع أسباب ترك العمل بالعدد والنسبة، والسبب الأول في كل قسم.", _DEPT),
    "turnover_trend_by_year": _schema(
        "turnover_trend_by_year", "التعيينات وترك العمل والصافي لكل سنة.", _DEPT),
    "tenure_at_exit": _schema(
        "tenure_at_exit", "متوسط مدة الخدمة عند ترك العمل وتوزيعها على شرائح.", _DEPT),
    "risk_scores": _schema(
        "risk_scores",
        "درجة خطر ترك العمل (0-100) للموظفين النشطين بقواعد شفافة، مع أسباب كل موظف. "
        "لا تعتمد على الجنس أو العمر أو المدينة.",
        {**_DEPT, "top_n": {"type": "integer", "description": "عدد الموظفين الأعلى خطراً (افتراضي 10، أقصى 25)."}}),
    "salary_gap_by_gender": _schema(
        "salary_gap_by_gender",
        "فجوة الرواتب بين الجنسين داخل نفس القسم والمسمى الوظيفي، مع حجم العينة وهل هي كافية.", _DEPT),
    "salary_by_education": _schema("salary_by_education", "متوسط ووسيط الرواتب حسب المؤهل.", _DEPT),
    "salary_vs_performance": _schema(
        "salary_vs_performance", "متوسط الراتب لكل تقييم أداء ومعامل الارتباط بينهما.", _DEPT),
    "list_policies": _schema("list_policies", "قائمة ملفات سياسات الشركة المتاحة وعناوينها."),
    "read_policy": _schema(
        "read_policy", "قراءة نص سياسة كاملة باسم ملفها.",
        {"file_name": {"type": "string", "description": "اسم الملف كما في list_policies، مثل leave.md"}},
        ["file_name"]),
}


def run_tool(name: str, args: dict, df: pd.DataFrame) -> dict:
    """تنفيذ أداة باسمها على البيانات المفلترة."""
    dept = args.get("department") or None
    if dept and dept not in set(df["القسم"]):
        return {"خطأ": f"القسم '{dept}' غير موجود في البيانات الحالية (بعد الفلترة).",
                "الأقسام المتاحة": sorted(df["القسم"].unique().tolist())}
    if name == "turnover_by_department":
        return turnover_by_department(df)
    if name == "exit_reasons_breakdown":
        return exit_reasons_breakdown(df, dept)
    if name == "turnover_trend_by_year":
        return turnover_trend_by_year(df, dept)
    if name == "tenure_at_exit":
        return tenure_at_exit(df, dept)
    if name == "risk_scores":
        top_n = max(1, min(int(args.get("top_n") or 10), 25))
        return risk_scores(df, dept, top_n)
    if name == "salary_gap_by_gender":
        return salary_gap_by_gender(df, dept)
    if name == "salary_by_education":
        return salary_by_education(df, dept)
    if name == "salary_vs_performance":
        return salary_vs_performance(df, dept)
    if name == "list_policies":
        return list_policies()
    if name == "read_policy":
        return read_policy(str(args.get("file_name", "")))
    raise KeyError(f"أداة غير معروفة: {name}")
