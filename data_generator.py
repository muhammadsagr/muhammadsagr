"""توليد بيانات افتراضية للموارد البشرية.

يمكن تشغيله مباشرة لحفظ البيانات في ملف CSV:
    python data_generator.py
"""
from datetime import date, timedelta

import numpy as np
import pandas as pd

FIRST_NAMES_M = ["محمد", "أحمد", "خالد", "عبدالله", "علي", "عمر", "يوسف", "سعد", "فهد", "حسن", "إبراهيم", "مصطفى", "طارق", "ماجد", "سامي"]
FIRST_NAMES_F = ["فاطمة", "مريم", "نورة", "سارة", "هند", "ريم", "ليلى", "منى", "دعاء", "آمنة", "رنا", "هدى", "أسماء", "لمى", "جود"]
LAST_NAMES = ["العتيبي", "الشمري", "القحطاني", "الزهراني", "المصري", "الحربي", "الدوسري", "السيد", "الغامدي", "صقر", "المالكي", "النجار", "حسين", "إبراهيم", "الأنصاري"]

# القسم: (المسميات الوظيفية, متوسط الراتب الأساسي, وزن عدد الموظفين)
DEPARTMENTS = {
    "تقنية المعلومات": (["مطور برمجيات", "مهندس شبكات", "محلل بيانات", "مدير مشاريع تقنية"], 14000, 0.22),
    "المبيعات": (["مندوب مبيعات", "مشرف مبيعات", "مدير حسابات"], 9000, 0.24),
    "الموارد البشرية": (["أخصائي توظيف", "أخصائي رواتب", "مدير موارد بشرية"], 10000, 0.08),
    "المالية": (["محاسب", "محلل مالي", "مدقق داخلي"], 12000, 0.12),
    "التسويق": (["أخصائي تسويق رقمي", "مصمم جرافيك", "مدير علامة تجارية"], 10500, 0.10),
    "العمليات": (["منسق عمليات", "مشرف مستودع", "أخصائي لوجستيات"], 8500, 0.16),
    "خدمة العملاء": (["ممثل خدمة عملاء", "مشرف مركز اتصال"], 7000, 0.08),
}
CITIES = ["الرياض", "جدة", "الدمام", "القاهرة", "دبي"]
CITY_WEIGHTS = [0.35, 0.22, 0.13, 0.18, 0.12]
EDUCATION = ["ثانوية", "دبلوم", "بكالوريوس", "ماجستير", "دكتوراه"]
EDUCATION_WEIGHTS = [0.08, 0.17, 0.55, 0.17, 0.03]
EXIT_REASONS = ["فرصة أفضل", "أسباب شخصية", "الراتب", "بيئة العمل", "إنهاء عقد", "تقاعد"]


def generate_employees(n: int = 500, seed: int = 42, today: date | None = None) -> pd.DataFrame:
    """إنشاء جدول موظفين افتراضي قابل للتكرار (نفس البذرة = نفس البيانات)."""
    rng = np.random.default_rng(seed)
    today = today or date.today()
    dept_names = list(DEPARTMENTS)
    dept_weights = np.array([DEPARTMENTS[d][2] for d in dept_names])
    dept_weights /= dept_weights.sum()

    rows = []
    for i in range(n):
        gender = rng.choice(["ذكر", "أنثى"], p=[0.62, 0.38])
        first = rng.choice(FIRST_NAMES_M if gender == "ذكر" else FIRST_NAMES_F)
        dept = rng.choice(dept_names, p=dept_weights)
        titles, base_salary, _ = DEPARTMENTS[dept]
        title_idx = int(rng.integers(len(titles)))
        age = int(np.clip(rng.normal(34, 8), 21, 60))
        birth = today - timedelta(days=age * 365 + int(rng.integers(365)))
        hire = today - timedelta(days=int(rng.integers(30, 365 * 10)))
        years = (today - hire).days / 365
        education = rng.choice(EDUCATION, p=EDUCATION_WEIGHTS)

        # الراتب يرتفع مع المستوى الوظيفي وسنوات الخبرة
        salary = base_salary * (1 + 0.25 * title_idx) * (1 + 0.03 * years) * rng.normal(1, 0.1)
        performance = int(np.clip(round(rng.normal(3.4, 0.9)), 1, 5))

        # احتمال ترك العمل أعلى لضعيفي الأداء
        left = rng.random() < (0.28 if performance <= 2 else 0.14)
        exit_date = exit_reason = None
        if left and (today - hire).days > 60:
            exit_date = hire + timedelta(days=int(rng.integers(60, (today - hire).days)))
            exit_reason = rng.choice(EXIT_REASONS)

        rows.append({
            "الرقم الوظيفي": f"EMP{1001 + i}",
            "الاسم": f"{first} {rng.choice(LAST_NAMES)}",
            "الجنس": gender,
            "العمر": age,
            "تاريخ الميلاد": birth,
            "القسم": dept,
            "المسمى الوظيفي": titles[title_idx],
            "المدينة": rng.choice(CITIES, p=CITY_WEIGHTS),
            "المؤهل": education,
            "تاريخ التعيين": hire,
            "الراتب": int(round(salary, -1)),
            "تقييم الأداء": performance,
            "أيام الإجازة المستخدمة": int(rng.integers(0, 31)),
            "ساعات التدريب": int(rng.integers(0, 80)),
            "الحالة": "مستقيل" if exit_date else "نشط",
            "تاريخ ترك العمل": exit_date,
            "سبب ترك العمل": exit_reason,
        })

    df = pd.DataFrame(rows)
    for col in ["تاريخ الميلاد", "تاريخ التعيين", "تاريخ ترك العمل"]:
        df[col] = pd.to_datetime(df[col])
    return df


if __name__ == "__main__":
    data = generate_employees()
    data.to_csv("hr_data.csv", index=False, encoding="utf-8-sig")
    print(f"تم حفظ {len(data)} موظف في hr_data.csv")
