"""اختبارات الأدوات الحسابية (حتمية، لا تحتاج مفتاح API)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hr_agents import tools  # noqa: E402

TODAY = pd.Timestamp("2026-01-01")


def emp(i, dept="المبيعات", title="مندوب مبيعات", gender="ذكر", salary=10000, perf=3, training=40,
        hire="2020-01-01", exit_date=None, reason=None, age=30, city="الرياض"):
    return {
        "الرقم الوظيفي": f"EMP{1000 + i}", "الاسم": f"موظف {i}", "الجنس": gender, "العمر": age,
        "تاريخ الميلاد": pd.Timestamp("1995-01-01"), "القسم": dept, "المسمى الوظيفي": title,
        "المدينة": city, "المؤهل": "بكالوريوس", "تاريخ التعيين": pd.Timestamp(hire), "الراتب": salary,
        "تقييم الأداء": perf, "أيام الإجازة المستخدمة": 10, "ساعات التدريب": training,
        "الحالة": "مستقيل" if exit_date else "نشط",
        "تاريخ ترك العمل": pd.Timestamp(exit_date) if exit_date else pd.NaT, "سبب ترك العمل": reason,
    }


@pytest.fixture
def df():
    rows = [
        # المبيعات: 4 نشطين، 2 تركوا العمل خلال آخر سنة
        emp(1), emp(2), emp(3), emp(4),
        emp(5, exit_date="2025-06-01", reason="الراتب", hire="2024-01-01"),
        emp(6, exit_date="2025-09-01", reason="فرصة أفضل", hire="2021-01-01"),
        # المالية: 4 نشطين، 1 ترك العمل قبل أكثر من سنة
        emp(7, dept="المالية", title="محاسب"), emp(8, dept="المالية", title="محاسب"),
        emp(9, dept="المالية", title="محاسب"), emp(10, dept="المالية", title="محاسب"),
        emp(11, dept="المالية", title="محاسب", exit_date="2023-03-01", reason="الراتب", hire="2022-01-01"),
    ]
    return pd.DataFrame(rows)


def test_turnover_by_department(df):
    out = tools.turnover_by_department(df, today=TODAY)
    by = {r["القسم"]: r for r in out["الأقسام"]}
    assert by["المبيعات"]["ترك العمل آخر 12 شهر"] == 2
    assert by["المبيعات"]["معدل الدوران السنوي %"] == 50.0
    assert by["المالية"]["ترك العمل آخر 12 شهر"] == 0
    assert out["الأقسام"][0]["القسم"] == "المبيعات"          # مرتبة من الأعلى
    assert out["معدل الدوران العام %"] == 25.0               # 2 ÷ 8


def test_exit_reasons(df):
    out = tools.exit_reasons_breakdown(df)
    reasons = {r["السبب"]: r["العدد"] for r in out["الأسباب"]}
    assert reasons == {"الراتب": 2, "فرصة أفضل": 1}
    assert out["السبب الأول في كل قسم"]["المالية"] == "الراتب"
    assert tools.exit_reasons_breakdown(df, "المالية")["عدد من ترك العمل"] == 1


def test_trend_and_tenure(df):
    years = {r["السنة"]: r for r in tools.turnover_trend_by_year(df)["السنوات"]}
    assert years[2025]["ترك العمل"] == 2
    assert years[2020]["تعيينات"] == 8
    tenure = tools.tenure_at_exit(df)
    assert tenure["عدد من ترك العمل"] == 3
    assert sum(tenure["التوزيع"].values()) == 3


def test_risk_scores_rules(df):
    df.loc[0, ["الراتب", "تقييم الأداء", "ساعات التدريب"]] = [5000, 1, 0]
    out = tools.risk_scores(df, today=TODAY)
    top = out["الموظفون"][0]
    assert top["الرقم الوظيفي"] == "EMP1001"
    # راتب منخفض 30 + أداء 20 + تدريب 15 + قسم دورانه مرتفع 20 = 85
    assert top["درجة الخطر"] == 85
    assert len(top["الأسباب"]) == 4
    assert all(0 <= e["درجة الخطر"] <= 100 for e in out["الموظفون"])


def test_risk_ignores_protected_attributes(df):
    base = tools.risk_scores(df, top_n=20, today=TODAY)["الموظفون"]
    changed = df.copy()
    changed["الجنس"] = "أنثى"
    changed["العمر"] = 59
    changed["المدينة"] = "دبي"
    after = tools.risk_scores(changed, top_n=20, today=TODAY)["الموظفون"]
    assert [(e["الرقم الوظيفي"], e["درجة الخطر"]) for e in base] == \
           [(e["الرقم الوظيفي"], e["درجة الخطر"]) for e in after]


def test_salary_gap_sample_size():
    rows = [emp(i, gender="ذكر", salary=12000) for i in range(5)] + \
           [emp(10 + i, gender="أنثى", salary=10000) for i in range(5)] + \
           [emp(20, dept="المالية", title="محاسب", gender="ذكر", salary=20000),
            emp(21, dept="المالية", title="محاسب", gender="أنثى", salary=10000)]
    out = tools.salary_gap_by_gender(pd.DataFrame(rows))
    groups = {g["القسم"]: g for g in out["المجموعات (الأكبر فجوة أولاً)"]}
    sales = groups["المبيعات"]
    assert sales["الفجوة % (موجب = لصالح الذكور)"] == pytest.approx(16.7, abs=0.1)
    assert sales["العينة كافية"] and sales["فجوة لافتة"]
    finance = groups["المالية"]
    assert not finance["العينة كافية"] and not finance["فجوة لافتة"]   # 50% لكن العينة صغيرة
    assert out["مجموعات بفجوة لافتة"] == 1


def test_salary_by_education_and_performance(df):
    edu = tools.salary_by_education(df)["المؤهلات"]
    assert edu[0]["المؤهل"] == "بكالوريوس" and edu[0]["العدد"] == 8
    perf = tools.salary_vs_performance(df)
    assert perf["حسب التقييم"][0]["تقييم الأداء"] == 3


def test_policies():
    names = [p["الملف"] for p in tools.list_policies()["السياسات"]]
    assert {"leave.md", "remote_work.md", "training.md"} <= set(names)
    assert "21 يوم" in tools.read_policy("leave.md")["المحتوى"]
    assert "خطأ" in tools.read_policy("../README.md")      # منع الخروج من مجلد السياسات
    assert "خطأ" in tools.read_policy("missing.md")


def test_run_tool_dispatch(df):
    for name in tools.TOOL_SPECS:
        args = {"file_name": "leave.md"} if name == "read_policy" else {}
        result = tools.run_tool(name, args, df)
        assert isinstance(result, dict)
    err = tools.run_tool("risk_scores", {"department": "قسم وهمي"}, df)
    assert "خطأ" in err and "المبيعات" in err["الأقسام المتاحة"]
    with pytest.raises(KeyError):
        tools.run_tool("unknown", {}, df)


def test_results_are_json_serializable(df):
    import json
    for name in tools.TOOL_SPECS:
        args = {"file_name": "leave.md"} if name == "read_policy" else {}
        json.dumps(tools.run_tool(name, args, df), ensure_ascii=False)


def test_works_on_random_large_data():
    rng = np.random.default_rng(0)
    rows = []
    depts = ["المبيعات", "المالية", "التسويق"]
    for i in range(300):
        left = rng.random() < 0.2
        rows.append(emp(i, dept=str(rng.choice(depts)), gender=str(rng.choice(["ذكر", "أنثى"])),
                        salary=int(rng.integers(5000, 20000)), perf=int(rng.integers(1, 6)),
                        training=int(rng.integers(0, 80)), hire="2019-05-01",
                        exit_date="2025-08-01" if left else None, reason="الراتب" if left else None))
    big = pd.DataFrame(rows)
    out = tools.risk_scores(big, top_n=25, today=TODAY)
    assert len(out["الموظفون"]) == 25
    assert tools.turnover_by_department(big, today=TODAY)["معدل الدوران العام %"] > 0
