"""واجهة المتصفح (عربية RTL):  streamlit run puzzle_app.py"""

import anthropic
import streamlit as st

from puzzle_agents import LEVEL_NAMES, MAX_LEVEL, Council, CouncilError, puzzles_for

st.set_page_config(page_title="مجلس الوكلاء", page_icon="🧠", layout="wide")
st.markdown(
    "<style>.stApp, .stApp * {direction: rtl; text-align: right;}</style>", unsafe_allow_html=True
)
st.title("🧠 مجلس الوكلاء")
st.caption("ثلاثة وكلاء يحلّون باستقلال، ثم يتناقشون، ثم يراجع كل منهم زملاءه، ثم يصدر المنسّق الحكم.")

state = st.session_state
state.setdefault("level", 1)

with st.sidebar:
    mode = st.radio("الوضع", ["ألغاز متدرجة", "ناقشوا فكرتي"])
    rounds = st.slider("جولات النقاش", 1, 3, 1)
    st.metric("المستوى الذي بلغه المجلس", f"{state.level}/{MAX_LEVEL}")

puzzle = None
if mode == "ألغاز متدرجة":
    level = st.select_slider(
        "المستوى", list(LEVEL_NAMES), value=state.level,
        format_func=lambda n: f"{n} — {LEVEL_NAMES[n]}",
    )
    puzzle = st.selectbox("اللغز", puzzles_for(level), format_func=lambda p: p.title)
    st.info(puzzle.question)
    task = puzzle.question
    note = st.text_area("فكرة أو تلميح للوكلاء (اختياري)")
else:
    task = st.text_area("فكرتك أو مسألتك", height=140)
    note = st.text_area("ملاحظات إضافية أو تعليق على حكم سابق (اختياري)")

if st.button("ابدأ المداولة", type="primary", disabled=not task.strip()):
    council = Council(rounds=rounds)
    titles = {"proposal": "الحلول المستقلة", "debate": "النقاش", "review": "مراجعة الأقران"}
    shown = None
    try:
        with st.spinner("المجلس يتداول…"):
            for ev in council.deliberate(
                task,
                kind="puzzle" if puzzle else "idea",
                reference=puzzle.answer if puzzle else None,
                user_note=note,
            ):
                header = titles.get(ev.phase, "") + (f" — الجولة {ev.round}" if ev.round else "")
                if header and header != shown:
                    shown = header
                    st.subheader(header)
                if ev.phase in ("proposal", "debate"):
                    with st.chat_message(ev.agent.name, avatar=ev.agent.emoji):
                        st.markdown(f"**{ev.agent.name}**\n\n{ev.text}")
                elif ev.phase == "review":
                    with st.chat_message(ev.agent.name, avatar=ev.agent.emoji):
                        for r in ev.data.reviews:
                            st.markdown(
                                f"**{ev.agent.name} يراجع «{r.target}»** — {r.verdict} ({r.score}/10)\n\n"
                                + "".join(f"- ✅ {s}\n" for s in r.strengths)
                                + "".join(f"- ⚠️ {i}\n" for i in r.issues)
                                + f"\n**اقتراح:** {r.suggestion}"
                            )
                elif ev.phase == "verdict":
                    v = ev.data
                    st.subheader("🏛️ الحكم النهائي")
                    st.success(v.final_answer)
                    st.markdown(f"{v.reasoning}\n\n**الثقة:** {v.confidence}")
                    if v.dissent.strip():
                        st.warning(f"خلاف باقٍ: {v.dissent}")
                elif ev.phase == "judgement":
                    if ev.data.correct:
                        st.balloons()
                        st.success(f"✅ جواب صحيح — {ev.data.comment}")
                        if puzzle.level == state.level and state.level < MAX_LEVEL:
                            state.level += 1
                    else:
                        st.error(f"❌ جواب خاطئ — {ev.data.comment}")
                        st.caption(f"الجواب المرجعي: {puzzle.answer}")
    except CouncilError as e:
        st.error(f"تعذّر إكمال المداولة: {e}")
    except anthropic.AuthenticationError:
        st.error("مفتاح API غير صالح أو غير موجود: اضبط ANTHROPIC_API_KEY ثم أعد التشغيل.")
    except anthropic.RateLimitError:
        st.error("تجاوزت حد الطلبات؛ انتظر قليلاً ثم أعد المحاولة.")
    except anthropic.APIStatusError as e:
        st.error(f"خطأ من الخادم ({e.status_code}): {e.message}")
    except anthropic.APIConnectionError:
        st.error("تعذّر الاتصال بالخادم؛ تحقق من الشبكة.")
    u = council.usage
    st.caption(f"{u.calls} نداء | رموز الإدخال {u.input_tokens:,} | رموز الإخراج {u.output_tokens:,}")
