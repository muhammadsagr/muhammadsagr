"""صفحة محاكاة التهرب الضريبي والاحتيال المالي (لأغراض الكشف وتقييم السياسات)."""
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from mizan.fraudsim.detection import benford_test, run_detectors
from mizan.fraudsim.ledger import TYPOLOGIES, LedgerConfig, account_labels, simulate_ledger
from mizan.fraudsim.tax import TaxPolicy, generate_population, policy_sweep, simulate

BLUE, ORANGE = "#2a78d6", "#eb6834"
SEQUENTIAL = ["#cde2fb", "#86b6ef", "#3987e5", "#256abf", "#0d366b"]
MARGIN = dict(t=10, b=10, l=10, r=10)

st.title("🕵️ محاكاة التهرب الضريبي والاحتيال المالي")
st.caption("كل البيانات هنا مُولَّدة بالكامل. الهدف قياس أثر السياسات الرقابية ودقة أدوات الكشف، "
           "على غرار أدوات البحث المعروفة مثل PaySim و AMLSim.")

tab_tax, tab_fraud = st.tabs(["🧾 التهرب الضريبي والسياسات", "💳 الاحتيال المالي والكشف"])


@st.cache_data(show_spinner=False)
def run_tax(n, honest, seed, policy_items, years):
    pop = generate_population(n, honest, seed)
    return simulate(pop, TaxPolicy(**dict(policy_items)), years, seed)


@st.cache_data(show_spinner=False)
def run_sweep(n, honest, seed, policy_items):
    pop = generate_population(n, honest, seed)
    return policy_sweep(pop, TaxPolicy(**dict(policy_items)),
                        audit_rates=[0.01, 0.02, 0.04, 0.07, 0.10], penalties=[0.5, 1.0, 2.0, 3.0, 4.0],
                        years=5, seed=seed)


@st.cache_data(show_spinner=False)
def run_fraud(camouflage, schemes, seed):
    cfg = LedgerConfig(camouflage=camouflage, schemes=schemes)
    ledger = simulate_ledger(cfg, seed)
    labels = account_labels(ledger)
    return cfg, ledger, labels, run_detectors(ledger, labels, cfg.report_threshold, seed)


# ====================================================================== التهرب الضريبي
with tab_tax:
    st.markdown("كل شخص يقرر كم يصرّح من دخله، بموازنة المكسب مقابل احتمال التدقيق والغرامة وكلفته الأخلاقية "
                "(نموذج Allingham–Sandmo). مصلحة الضرائب لا ترى الدخل الحقيقي، بل مؤشراً غير دقيق عنه.")
    c1, c2, c3, c4 = st.columns(4)
    tax_rate = c1.slider("نسبة الضريبة", 0.05, 0.35, 0.20, 0.01, format="%.2f")
    penalty = c2.slider("الغرامة (× الضريبة المتهرَّب منها)", 0.0, 4.0, 1.5, 0.25)
    audit_rate = c3.slider("نسبة التدقيق السنوية", 0.005, 0.15, 0.03, 0.005, format="%.3f")
    targeting = c4.slider("حصة التدقيق الموجّه بالمخاطر", 0.0, 1.0, 0.5, 0.1)
    c1, c2, c3, c4 = st.columns(4)
    detection = c1.slider("فعالية التدقيق في الكشف", 0.3, 1.0, 0.8, 0.05)
    noise = c2.slider("ضوضاء بيانات الطرف الثالث", 0.05, 1.0, 0.35, 0.05,
                      help="كلما قلّت، عرفت المصلحة الدخل الحقيقي بدقة أكبر فصار الاستهداف أنجح")
    honest = c3.slider("نسبة الملتزمين دائماً", 0.0, 0.9, 0.3, 0.05)
    years = c4.slider("عدد السنوات", 3, 20, 10)

    policy = TaxPolicy(tax_rate, penalty, audit_rate, targeting, detection, noise)
    items = tuple(policy.__dict__.items())
    with st.spinner("جاري المحاكاة..."):
        yearly, people = run_tax(5000, honest, 0, items, years)
    last = yearly.iloc[-1]

    k = st.columns(4)
    k[0].metric("الفجوة الضريبية", f"{last.tax_gap / last.tax_due:.1%}", help="الضريبة غير المصرّح بها ÷ الضريبة المستحقة")
    k[1].metric("نسبة المتهرّبين", f"{1 - last.compliance:.0%}", help="من يخفي أي جزء من دخله")
    k[2].metric("نسبة نجاح التدقيق", f"{last.hit_rate:.0%}", help="نسبة الملفات المدققة التي كُشف فيها تهرب")
    k[3].metric("المُسترد بالغرامات (آخر سنة)", f"{last.recovered / 1e6:,.1f} مليون")

    left, right = st.columns(2)
    with left:
        st.markdown("**نسبة الدخل المخفي حسب القطاع**")
        by_sector = (1 - people.groupby("sector")["declared_share"].mean()).sort_values()
        fig = go.Figure(go.Bar(x=by_sector.values, y=by_sector.index, orientation="h", marker_color=BLUE,
                               hovertemplate="%{y}: %{x:.1%}<extra></extra>"))
        fig.update_layout(margin=MARGIN, height=320, xaxis_tickformat=".0%")
        st.plotly_chart(fig, use_container_width=True)
        st.caption("الموظفون الذين يُبلغ صاحب العمل عن رواتبهم لا يستطيعون الإخفاء تقريباً؛ "
                   "التهرب يتركز حيث لا يوجد طرف ثالث يبلّغ.")
    with right:
        st.markdown("**الفجوة الضريبية عبر السنوات**")
        fig = px.line(yearly, x="year", y=yearly.tax_gap / yearly.tax_due, markers=True)
        fig.update_traces(line_color=BLUE, line_width=2, hovertemplate="السنة %{x}: %{y:.2%}<extra></extra>")
        fig.update_layout(margin=MARGIN, height=320, yaxis_tickformat=".1%", yaxis_title="", xaxis_title="السنة")
        st.plotly_chart(fig, use_container_width=True)
        st.caption("تتغير الفجوة مع تعلّم الناس من تجاربهم وتجارب زملائهم في القطاع.")

    st.markdown("**أي سياسة أفضل؟ الفجوة الضريبية بعد 5 سنوات لكل مزيج من التدقيق والغرامة**")
    if st.toggle("تشغيل مقارنة السيناريوهات (25 محاكاة)"):
        with st.spinner("جاري تشغيل 25 سيناريو..."):
            sweep = run_sweep(5000, honest, 0, items)
        grid = sweep.pivot(index="penalty", columns="audit_rate", values="tax_gap_share")
        fig = px.imshow(grid, text_auto=".1%", color_continuous_scale=SEQUENTIAL, aspect="auto",
                        labels=dict(x="نسبة التدقيق", y="الغرامة", color="الفجوة"))
        fig.update_xaxes(tickformat=".0%", type="category")
        fig.update_yaxes(type="category")
        fig.update_layout(margin=MARGIN, coloraxis_colorbar_tickformat=".0%")
        st.plotly_chart(fig, use_container_width=True)

    with st.expander("المؤشرات السنوية"):
        st.dataframe(yearly, use_container_width=True, hide_index=True)

# ====================================================================== الاحتيال المالي
with tab_fraud:
    st.markdown("سجل معاملات لـ 750 حساباً على مدى 180 يوماً، حُقنت فيه أنماط احتيال معروفة "
                "(من أدلة مجموعة العمل المالي FATF). نعرف الإجابة الصحيحة لكل حساب، فنقيس دقة كل أداة كشف.")
    c1, c2, c3 = st.columns(3)
    camouflage = c1.slider("مستوى تمويه المحتالين", 0.0, 1.0, 0.0, 0.1,
                           help="0: أنماط صريحة. 1: المحتالون يتكيّفون لتفادي القواعد المعروفة")
    schemes = c2.slider("عدد المخططات من كل نمط", 5, 30, 15)
    seed = c3.number_input("البذرة العشوائية", 0, 999, 0)
    with st.spinner("جاري توليد المعاملات وتشغيل الكواشف..."):
        cfg, ledger, labels, det = run_fraud(camouflage, schemes, int(seed))

    k = st.columns(4)
    k[0].metric("المعاملات", f"{len(ledger):,}")
    k[1].metric("معاملات احتيالية", f"{ledger.is_fraud.sum():,}", help=f"{ledger.is_fraud.mean():.2%} من كل المعاملات")
    k[2].metric("حسابات متورطة", f"{labels.is_fraud.sum()}")
    k[3].metric("دوائر مغلقة مكتشفة", f"{len(det['cycles'])}")

    st.markdown("**مقارنة أدوات الكشف** (على نصف الحسابات المحجوز للاختبار)")
    rows = [{"الأداة": name, "حسابات مُعلَّمة": r["flagged"], "الدقة": r["precision"], "الاستدعاء": r["recall"],
             "F1": r["f1"], **{TYPOLOGIES[t]: v for t, v in r["recall_by_typology"].items()}}
            for name, r in det["results"].items()]
    pct = st.column_config.ProgressColumn
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True, column_config={
        "الدقة": pct("الدقة", help="من بين المُعلَّمين، كم منهم محتال فعلاً", format="percent", min_value=0, max_value=1),
        "الاستدعاء": pct("الاستدعاء", help="من بين المحتالين، كم منهم كُشف", format="percent", min_value=0, max_value=1),
        "F1": st.column_config.NumberColumn("F1", format="%.2f"),
        **{TYPOLOGIES[t]: st.column_config.NumberColumn(TYPOLOGIES[t], format="percent") for t in TYPOLOGIES},
    })
    st.caption("ارفع مستوى التمويه وراقب الفرق: القواعد الثابتة مصممة لأنماط معروفة فتنهار عندما يتكيّف "
               "المحتالون، بينما يصمد النموذج المدرَّب أكثر (بشرط وجود أمثلة مُعلَّمة حديثة للتدريب).")

    left, right = st.columns(2)
    with left:
        st.markdown("**قانون بنفورد: توزيع الرقم الأول للمبالغ**")
        subset = st.radio("المعاملات", ["المعاملات السليمة", "الفواتير الوهمية", "كل المعاملات"], horizontal=True)
        amounts = {"المعاملات السليمة": ledger.loc[~ledger.is_fraud, "amount"],
                   "الفواتير الوهمية": ledger.loc[ledger.typology == "fake_invoice", "amount"],
                   "كل المعاملات": ledger.amount}[subset]
        b = benford_test(amounts)
        fig = go.Figure()
        fig.add_bar(x=b["digit"], y=b["observed"], name="الملاحظ", marker_color=BLUE,
                    hovertemplate="الرقم %{x}: %{y:.1%}<extra>الملاحظ</extra>")
        fig.add_scatter(x=b["digit"], y=b["expected"], name="بنفورد", mode="lines+markers",
                        line=dict(color=ORANGE, width=2), marker_size=8,
                        hovertemplate="الرقم %{x}: %{y:.1%}<extra>بنفورد</extra>")
        fig.update_layout(margin=MARGIN, height=330, yaxis_tickformat=".0%", xaxis=dict(dtick=1),
                          legend=dict(orientation="h", y=1.1, x=0))
        st.plotly_chart(fig, use_container_width=True)
        st.caption(f"الانحراف المطلق المتوسط (MAD) = {b['mad']:.4f} ← **{b['verdict']}** (معايير Nigrini، {b['n']:,} مبلغ)")
    with right:
        st.markdown("**ما الذي تعلّمه النموذج؟** (أوزان الخصائص بعد التوحيد)")
        names = {"pass_through": "نسبة تمرير الأموال", "round_share": "حصة المبالغ المستديرة",
                 "round_count": "عدد المبالغ المستديرة الكبيرة", "avg_amount_log": "متوسط المبلغ",
                 "near_threshold": "إيداعات قرب حد الإبلاغ", "fan_in_ratio": "نسبة المرسلين للمستقبلين",
                 "burst_senders": "مرسلون كثر في أسبوع", "uniq_src": "عدد المرسلين", "uniq_dst": "عدد المستقبلين",
                 "n_in": "عدد الواردات", "n_out": "عدد الصادرات"}
        w = det["weights"].iloc[::-1]
        fig = go.Figure(go.Bar(x=w.values, y=[names[i] for i in w.index], orientation="h",
                               marker_color=np.where(w.values >= 0, ORANGE, BLUE),
                               hovertemplate="%{y}: %{x:.2f}<extra></extra>"))
        fig.update_layout(margin=MARGIN, height=380)
        st.plotly_chart(fig, use_container_width=True)
        st.caption("البرتقالي يرفع الاشتباه، والأزرق يخفضه.")

    st.markdown("**أعلى الحسابات اشتباهاً حسب النموذج** (حسابات الاختبار فقط)")
    test = det["test_accounts"]
    top = (pd.DataFrame({"درجة الاشتباه": det["scores"].reindex(test),
                         "الحقيقة": labels.loc[test, "typology"].map(TYPOLOGIES).fillna("سليم")})
           .sort_values("درجة الاشتباه", ascending=False).head(25).rename_axis("الحساب"))
    st.dataframe(top, use_container_width=True, column_config={
        "درجة الاشتباه": pct("درجة الاشتباه", format="percent", min_value=0, max_value=1)})

    if det["cycles"]:
        with st.expander(f"الدوائر المغلقة المكتشفة ({len(det['cycles'])})"):
            st.dataframe(pd.DataFrame([{"المسار": " ← ".join(c["accounts"] + [c["accounts"][0]]),
                                        "المبلغ": round(c["amount"]), "اليوم": c["day"]} for c in det["cycles"]]),
                         hide_index=True, use_container_width=True)
    with st.expander("سجل المعاملات"):
        st.dataframe(ledger, hide_index=True, use_container_width=True)
        st.download_button("⬇️ تحميل السجل CSV", ledger.to_csv(index=False).encode("utf-8-sig"),
                           "mizan_ledger.csv", "text/csv")
