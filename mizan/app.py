"""لوحة ميزان — المرحلة 1: الأسعار والعوائد.

التشغيل من مجلد المشروع:
    python mizan/app.py
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# عند التشغيل بـ python مباشرة: أعد تشغيل الملف عبر Streamlit ليفتح في المتصفح
if not st.runtime.exists():
    sys.exit(subprocess.call([sys.executable, "-m", "streamlit", "run", __file__]))

from mizan import analytics
from mizan.collector import collect
from mizan.sources import SYNTHETIC_UNIVERSE, CSVSource, SyntheticSource
from mizan.store import TimeSeriesStore

DATA_DIR = ROOT / "mizan_data"
# لوحة ألوان فئوية بترتيب ثابت؛ اللون يتبع الأصل نفسه ولا يتغير مع الفلترة
PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
# تدرج متباعد للارتباط: أزرق (سالب) ← رمادي (صفر) ← أحمر (موجب = مخاطر متركزة)
DIVERGING = [[0.0, "#1c5cab"], [0.25, "#6da7ec"], [0.5, "#f0efec"], [0.75, "#ef8a89"], [1.0, "#b8302f"]]

st.set_page_config(page_title="ميزان — تحليل المخاطر", page_icon="⚖️", layout="wide")
st.markdown("<style>.main, .stMarkdown, .stCaption {direction: rtl; text-align: right;}</style>",
            unsafe_allow_html=True)


@st.cache_resource
def get_store(path: str) -> TimeSeriesStore:
    return TimeSeriesStore(path)


def style(fig: go.Figure, y_title: str, percent: bool = False) -> go.Figure:
    fig.update_traces(line_width=2)
    fig.update_layout(
        hovermode="x unified", legend_title_text="", yaxis_title=y_title, xaxis_title="",
        legend=dict(orientation="h", y=1.08, x=0), margin=dict(t=40, b=10, l=10, r=10),
    )
    if percent:
        fig.update_yaxes(tickformat=".0%")
    return fig


# ================================================================ الشريط الجانبي
st.sidebar.title("⚖️ ميزان")
source_name = st.sidebar.radio("مصدر البيانات", ["بيانات تجريبية", "ملفات CSV"])
if source_name == "بيانات تجريبية":
    source = SyntheticSource()
    universe = list(SYNTHETIC_UNIVERSE)
    labels = {s: f"{s} — {spec.label}" for s, spec in SYNTHETIC_UNIVERSE.items()}
    store = get_store(str(DATA_DIR / "synthetic"))
else:
    folder = Path(st.sidebar.text_input("مجلد ملفات CSV", str(ROOT / "mizan_csv")))
    source = CSVSource(folder)
    universe = source.available() if folder.is_dir() else []
    labels = {s: s for s in universe}
    store = get_store(str(DATA_DIR / "csv"))
    if not universe:
        st.sidebar.warning("لا توجد ملفات CSV في هذا المجلد. ضع ملفاً لكل رمز مثل AAPL.csv "
                           "يحتوي الأعمدة Date, Open, High, Low, Close, Volume.")

colors = {s: PALETTE[i % len(PALETTE)] for i, s in enumerate(universe)}
symbols = st.sidebar.multiselect("الأصول", universe, default=universe[:4], format_func=labels.get,
                                 max_selections=len(PALETTE))
today = pd.Timestamp.today().normalize()
period = st.sidebar.date_input("الفترة", (today - pd.DateOffset(years=3), today))
if len(period) != 2:  # المستخدم اختار تاريخ البداية ولم يختر النهاية بعد
    st.stop()
start, end = period

if st.sidebar.button("🔄 تحديث البيانات", use_container_width=True, disabled=not symbols):
    with st.spinner("جاري جمع البيانات..."):
        results = collect(source, symbols, start, end, store)
    for r in results:
        if r.error:
            st.sidebar.error(f"{r.symbol}: {r.error}")
    st.sidebar.success(f"أُضيف {sum(r.rows for r in results):,} صف جديد")

# ================================================================ تحميل البيانات
st.title("⚖️ ميزان — الأسعار والعوائد")
if source_name == "بيانات تجريبية":
    st.caption("البيانات الحالية مُولَّدة للتجربة والتعلّم وليست أسعار سوق حقيقية. هذه أداة تحليل وليست نصيحة استثمارية.")

stored = set(store.symbols())
missing = [s for s in symbols if s not in stored]
if missing:
    st.info(f"لا توجد بيانات محفوظة لـ: {', '.join(missing)}. اضغط «تحديث البيانات» في الشريط الجانبي.")
available = [s for s in symbols if s in stored]
if not available:
    st.stop()

prices = pd.DataFrame({s: store.read(s, start, end)["close"] for s in available}).sort_index()
if len(prices) < 2:
    st.warning("البيانات في هذه الفترة غير كافية. وسّع الفترة أو حدّث البيانات.")
    st.stop()
returns = analytics.simple_returns(prices)
color_map = {s: colors[s] for s in available}

# ================================================================ ملخص
summary = analytics.summary(prices)
st.subheader("الملخص")
st.dataframe(
    summary.rename(index=labels),
    use_container_width=True,
    column_config={
        "last_price": st.column_config.NumberColumn("آخر سعر", format="%.2f"),
        "total_return": st.column_config.NumberColumn("العائد الكلي", format="percent"),
        "cagr": st.column_config.NumberColumn("العائد السنوي المركب", format="percent"),
        "volatility": st.column_config.NumberColumn("التذبذب السنوي", format="percent"),
        "sharpe": st.column_config.NumberColumn("نسبة شارب", format="%.2f"),
        "max_drawdown": st.column_config.NumberColumn("أقصى تراجع", format="percent"),
        "worst_day": st.column_config.NumberColumn("أسوأ يوم", format="percent"),
        "best_day": st.column_config.NumberColumn("أفضل يوم", format="percent"),
    },
)

tab_perf, tab_risk, tab_corr, tab_data = st.tabs(["📈 الأداء", "📉 التراجع والتذبذب", "🔗 الارتباط", "🗂️ البيانات"])

with tab_perf:
    st.markdown("**نمو 100 وحدة مستثمرة في بداية الفترة**")
    fig = px.line(analytics.rebase(prices), color_discrete_map=color_map)
    st.plotly_chart(style(fig, "القيمة (بداية = 100)"), use_container_width=True)

    st.markdown("**توزيع العوائد اليومية**")
    long = returns.melt(var_name="الأصل", value_name="العائد").dropna()
    fig = px.box(long, x="الأصل", y="العائد", color="الأصل", color_discrete_map=color_map, points=False)
    fig.update_layout(showlegend=False, margin=dict(t=10, b=10, l=10, r=10), xaxis_title="")
    fig.update_yaxes(tickformat=".1%")
    st.plotly_chart(fig, use_container_width=True)

with tab_risk:
    st.markdown("**التراجع عن أعلى قمة سابقة**")
    fig = px.line(analytics.drawdown(prices), color_discrete_map=color_map)
    st.plotly_chart(style(fig, "التراجع", percent=True), use_container_width=True)

    window = st.slider("نافذة التذبذب المتحرك (أيام تداول)", 10, 126, 21)
    st.markdown(f"**التذبذب السنوي المتحرك ({window} يوماً)**")
    fig = px.line(analytics.rolling_volatility(returns, window), color_discrete_map=color_map)
    st.plotly_chart(style(fig, "التذبذب", percent=True), use_container_width=True)

with tab_corr:
    if len(available) < 2:
        st.info("اختر أصلين على الأقل لعرض الارتباط.")
    else:
        st.markdown("**ارتباط العوائد اليومية** — الارتباط المرتفع يعني أن الأصول تنخفض معاً، أي تنويع أقل.")
        corr = returns.corr()
        fig = px.imshow(corr, text_auto=".2f", zmin=-1, zmax=1, color_continuous_scale=DIVERGING, aspect="auto")
        fig.update_layout(margin=dict(t=10, b=10, l=10, r=10), coloraxis_colorbar_title="")
        st.plotly_chart(fig, use_container_width=True)

with tab_data:
    st.dataframe(prices.sort_index(ascending=False), use_container_width=True)
    st.download_button("⬇️ تحميل الأسعار CSV", prices.to_csv().encode("utf-8-sig"),
                       "mizan_prices.csv", "text/csv")
