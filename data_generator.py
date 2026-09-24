"""تطبيق الموارد البشرية في ملف واحد: بيانات افتراضية + لوحة معلومات.

التشغيل: اضغط زر Run ▶ في VS Code، أو من الطرفية:
    python data_generator.py
"""
import importlib.util
import subprocess
import sys

# تثبيت المكتبات المطلوبة تلقائياً إذا لم تكن مثبتة
REQUIRED = {"streamlit": "streamlit>=1.50", "pandas": "pandas>=2.0", "numpy": "numpy>=1.24", "plotly": "plotly>=5.18"}
missing = [pkg for mod, pkg in REQUIRED.items() if importlib.util.find_spec(mod) is None]
if missing:
    print("جاري تثبيت المكتبات المطلوبة:", ", ".join(missing))
    subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])

from datetime import date, timedelta

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

# عند التشغيل بـ python مباشرة: أعد تشغيل الملف نفسه عبر Streamlit ليفتح في المتصفح
if not st.runtime.exists():
    # تخطي سؤال البريد الإلكتروني الذي يظهر عند أول تشغيل لـ Streamlit
    from pathlib import Path
    credentials = Path.home() / ".streamlit" / "credentials.toml"
    if not credentials.exists():
        credentials.parent.mkdir(exist_ok=True)
        credentials.write_text('[general]\nemail = ""\n', encoding="utf-8")
    sys.exit(subprocess.call([sys.executable, "-m", "streamlit", "run", __file__]))


# ================================================================ البيانات الافتراضية
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


# ================================================================ لوحة المعلومات
st.set_page_config(page_title="لوحة الموارد البشرية", page_icon="👥", layout="wide")

# اتجاه الصفحة من اليمين لليسار
st.markdown(
    """
    <style>
    .stApp, .stMarkdown, .stSidebar, [data-testid="stMetric"] { direction: rtl; text-align: right; }
    [data-testid="stMetric"] { background: rgba(42,120,214,0.07); border-radius: 10px; padding: 12px 16px; }
    </style>
    """,
    unsafe_allow_html=True,
)

COLORS = ["#2a78d6", "#1baf7a", "#eba827", "#d95757", "#8b64d9", "#2cb6c9", "#e07b39"]
CHART_LAYOUT = dict(margin=dict(l=10, r=10, t=40, b=10), font=dict(size=13), legend_title_text="")


def style(fig):
    fig.update_layout(**CHART_LAYOUT)
    return fig


# ---------------------------------------------------------------- البيانات
if "employees" not in st.session_state:
    st.session_state.employees = generate_employees(n=500, seed=42)
df_all: pd.DataFrame = st.session_state.employees
today = pd.Timestamp(date.today())

# ---------------------------------------------------------------- الفلاتر
st.sidebar.header("🔎 الفلاتر")
depts = st.sidebar.multiselect("القسم", sorted(df_all["القسم"].unique()), default=None, placeholder="كل الأقسام")
cities = st.sidebar.multiselect("المدينة", sorted(df_all["المدينة"].unique()), placeholder="كل المدن")
genders = st.sidebar.multiselect("الجنس", ["ذكر", "أنثى"], placeholder="الكل")
min_hire, max_hire = df_all["تاريخ التعيين"].min().date(), df_all["تاريخ التعيين"].max().date()
hire_range = st.sidebar.date_input("تاريخ التعيين", (min_hire, max_hire), min_value=min_hire, max_value=max_hire)

df = df_all.copy()
if depts:
    df = df[df["القسم"].isin(depts)]
if cities:
    df = df[df["المدينة"].isin(cities)]
if genders:
    df = df[df["الجنس"].isin(genders)]
if isinstance(hire_range, tuple) and len(hire_range) == 2:
    start, end = map(pd.Timestamp, hire_range)
    df = df[df["تاريخ التعيين"].between(start, end)]

st.sidebar.caption(f"عدد السجلات بعد التصفية: {len(df)}")
if st.sidebar.button("🔄 توليد بيانات جديدة"):
    st.session_state.employees = generate_employees(n=500, seed=int(pd.Timestamp.now().timestamp()))
    st.rerun()

active = df[df["الحالة"] == "نشط"]
exited = df[df["الحالة"] == "مستقيل"]

# ---------------------------------------------------------------- العنوان والمؤشرات
st.title("👥 لوحة معلومات الموارد البشرية")
st.caption("بيانات افتراضية لأغراض العرض والتجربة")

if df.empty:
    st.warning("لا توجد بيانات مطابقة للفلاتر المحددة.")
    st.stop()

last_year = today - pd.DateOffset(years=1)
exits_12m = (exited["تاريخ ترك العمل"] >= last_year).sum()
turnover = exits_12m / max(len(active), 1) * 100
hires_12m = (df["تاريخ التعيين"] >= last_year).sum()

k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("إجمالي الموظفين", f"{len(df):,}")
k2.metric("الموظفون النشطون", f"{len(active):,}")
k3.metric("تعيينات آخر 12 شهر", f"{hires_12m:,}")
k4.metric("معدل الدوران السنوي", f"{turnover:.1f}%")
k5.metric("متوسط الراتب", f"{active['الراتب'].mean():,.0f}" if len(active) else "—")
k6.metric("متوسط الأداء", f"{active['تقييم الأداء'].mean():.2f} / 5" if len(active) else "—")

tab_overview, tab_pay, tab_exits, tab_table, tab_add = st.tabs(
    ["📊 نظرة عامة", "💰 الرواتب والأداء", "🚪 ترك العمل", "📋 بيانات الموظفين", "➕ إضافة موظف"]
)

# ---------------------------------------------------------------- نظرة عامة
with tab_overview:
    c1, c2 = st.columns([3, 2])
    by_dept = active["القسم"].value_counts().sort_values().reset_index()
    fig = px.bar(by_dept, x="count", y="القسم", orientation="h", text="count",
                 title="الموظفون النشطون حسب القسم", color_discrete_sequence=COLORS)
    fig.update_layout(xaxis_title="", yaxis_title="")
    c1.plotly_chart(style(fig), width="stretch")

    fig = px.pie(active, names="الجنس", hole=0.55, title="التوزيع حسب الجنس",
                 color_discrete_sequence=COLORS)
    c2.plotly_chart(style(fig), width="stretch")

    c3, c4 = st.columns(2)
    hires = df.groupby(df["تاريخ التعيين"].dt.year).size().rename("تعيينات")
    leaves = exited.groupby(exited["تاريخ ترك العمل"].dt.year).size().rename("استقالات")
    trend = pd.concat([hires, leaves], axis=1).fillna(0).reset_index(names="السنة")
    fig = px.line(trend, x="السنة", y=["تعيينات", "استقالات"], markers=True,
                  title="التعيينات مقابل ترك العمل سنوياً",
                  color_discrete_map={"تعيينات": COLORS[0], "استقالات": COLORS[3]})
    fig.update_layout(xaxis_title="", yaxis_title="عدد الموظفين")
    c3.plotly_chart(style(fig), width="stretch")

    fig = px.histogram(active, x="العمر", nbins=20, title="توزيع الأعمار", color_discrete_sequence=COLORS)
    fig.update_layout(xaxis_title="العمر", yaxis_title="عدد الموظفين", bargap=0.05)
    c4.plotly_chart(style(fig), width="stretch")

    c5, c6 = st.columns(2)
    by_city = active["المدينة"].value_counts().reset_index()
    fig = px.bar(by_city, x="المدينة", y="count", text="count", title="الموظفون حسب المدينة",
                 color_discrete_sequence=COLORS[1:])
    fig.update_layout(xaxis_title="", yaxis_title="")
    c5.plotly_chart(style(fig), width="stretch")

    edu = active["المؤهل"].value_counts().reindex(EDUCATION).dropna().reset_index()
    fig = px.bar(edu, x="المؤهل", y="count", text="count", title="المؤهل العلمي",
                 color_discrete_sequence=COLORS[4:])
    fig.update_layout(xaxis_title="", yaxis_title="")
    c6.plotly_chart(style(fig), width="stretch")

# ---------------------------------------------------------------- الرواتب والأداء
with tab_pay:
    c1, c2 = st.columns(2)
    fig = px.box(active, x="القسم", y="الراتب", color="القسم", title="توزيع الرواتب حسب القسم",
                 color_discrete_sequence=COLORS)
    fig.update_layout(showlegend=False, xaxis_title="", yaxis_title="الراتب الشهري")
    c1.plotly_chart(style(fig), width="stretch")

    perf = active["تقييم الأداء"].value_counts().sort_index().reset_index()
    fig = px.bar(perf, x="تقييم الأداء", y="count", text="count", title="توزيع تقييمات الأداء (1-5)",
                 color_discrete_sequence=COLORS[1:])
    fig.update_layout(xaxis_title="التقييم", yaxis_title="عدد الموظفين", xaxis=dict(dtick=1))
    c2.plotly_chart(style(fig), width="stretch")

    summary = (
        active.groupby("القسم")
        .agg(عدد_الموظفين=("الرقم الوظيفي", "count"),
             متوسط_الراتب=("الراتب", "mean"),
             إجمالي_الرواتب=("الراتب", "sum"),
             متوسط_الأداء=("تقييم الأداء", "mean"),
             متوسط_ساعات_التدريب=("ساعات التدريب", "mean"))
        .round(1)
        .sort_values("إجمالي_الرواتب", ascending=False)
    )
    summary.columns = [c.replace("_", " ") for c in summary.columns]
    st.subheader("ملخص الأقسام")
    st.dataframe(summary.style.format("{:,.1f}"), width="stretch")

    fig = px.scatter(active, x="ساعات التدريب", y="تقييم الأداء", color="القسم", size="الراتب",
                     hover_name="الاسم", title="العلاقة بين التدريب والأداء",
                     color_discrete_sequence=COLORS)
    st.plotly_chart(style(fig), width="stretch")

# ---------------------------------------------------------------- ترك العمل
with tab_exits:
    if exited.empty:
        st.info("لا توجد حالات ترك عمل ضمن الفلاتر الحالية.")
    else:
        c1, c2 = st.columns(2)
        reasons = exited["سبب ترك العمل"].value_counts().sort_values().reset_index()
        fig = px.bar(reasons, x="count", y="سبب ترك العمل", orientation="h", text="count",
                     title="أسباب ترك العمل", color_discrete_sequence=[COLORS[3]])
        fig.update_layout(xaxis_title="", yaxis_title="")
        c1.plotly_chart(style(fig), width="stretch")

        rate = (df.groupby("القسم")["الحالة"].apply(lambda s: (s == "مستقيل").mean() * 100)
                .sort_values().reset_index(name="النسبة"))
        fig = px.bar(rate, x="النسبة", y="القسم", orientation="h", text_auto=".1f",
                     title="نسبة ترك العمل حسب القسم (%)", color_discrete_sequence=[COLORS[2]])
        fig.update_layout(xaxis_title="", yaxis_title="")
        c2.plotly_chart(style(fig), width="stretch")

        st.subheader("آخر حالات ترك العمل")
        st.dataframe(
            exited.sort_values("تاريخ ترك العمل", ascending=False)
            [["الرقم الوظيفي", "الاسم", "القسم", "المسمى الوظيفي", "تاريخ ترك العمل", "سبب ترك العمل"]]
            .head(15),
            width="stretch", hide_index=True,
        )

# ---------------------------------------------------------------- الجدول
with tab_table:
    search = st.text_input("ابحث بالاسم أو الرقم الوظيفي")
    table = df
    if search:
        mask = df["الاسم"].str.contains(search, case=False, regex=False) | df["الرقم الوظيفي"].str.contains(search, case=False, regex=False)
        table = df[mask]
    st.dataframe(
        table, width="stretch", hide_index=True,
        column_config={
            "الراتب": st.column_config.NumberColumn(format="%d"),
            "تقييم الأداء": st.column_config.ProgressColumn(min_value=0, max_value=5, format="%d"),
            "تاريخ الميلاد": st.column_config.DateColumn(format="YYYY-MM-DD"),
            "تاريخ التعيين": st.column_config.DateColumn(format="YYYY-MM-DD"),
            "تاريخ ترك العمل": st.column_config.DateColumn(format="YYYY-MM-DD"),
        },
    )
    st.download_button("⬇️ تحميل البيانات (CSV)", table.to_csv(index=False).encode("utf-8-sig"),
                       file_name="hr_data.csv", mime="text/csv")

# ---------------------------------------------------------------- إضافة موظف
with tab_add:
    with st.form("add_employee", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        name = c1.text_input("الاسم")
        gender = c2.selectbox("الجنس", ["ذكر", "أنثى"])
        age = c3.number_input("العمر", 18, 70, 30)
        dept = c1.selectbox("القسم", list(DEPARTMENTS))
        title = c2.selectbox("المسمى الوظيفي", sorted({t for v in DEPARTMENTS.values() for t in v[0]}))
        city = c3.selectbox("المدينة", CITIES)
        edu_level = c1.selectbox("المؤهل", EDUCATION, index=2)
        salary = c2.number_input("الراتب", 3000, 100000, 10000, step=500)
        perf_score = c3.slider("تقييم الأداء", 1, 5, 3)
        submitted = st.form_submit_button("حفظ الموظف")

    if submitted:
        if not name.strip():
            st.error("الرجاء إدخال اسم الموظف.")
        else:
            next_id = int(df_all["الرقم الوظيفي"].str[3:].astype(int).max()) + 1
            new_row = {
                "الرقم الوظيفي": f"EMP{next_id}", "الاسم": name.strip(), "الجنس": gender, "العمر": age,
                "تاريخ الميلاد": today - pd.DateOffset(years=age), "القسم": dept, "المسمى الوظيفي": title,
                "المدينة": city, "المؤهل": edu_level, "تاريخ التعيين": today, "الراتب": salary,
                "تقييم الأداء": perf_score, "أيام الإجازة المستخدمة": 0, "ساعات التدريب": 0,
                "الحالة": "نشط", "تاريخ ترك العمل": pd.NaT, "سبب ترك العمل": None,
            }
            st.session_state.employees = pd.concat([df_all, pd.DataFrame([new_row])], ignore_index=True)
            st.success(f"تمت إضافة {name} برقم EMP{next_id}")
            st.rerun()
