"""واجهة الطرفية:  python -m puzzle_agents"""

from __future__ import annotations

import anthropic

from .council import Council, CouncilError, Event
from .puzzles import LEVEL_NAMES, MAX_LEVEL, pick

PHASE_TITLES = {
    "proposal": "الحلول المستقلة",
    "debate": "النقاش",
    "review": "مراجعة الأقران",
    "verdict": "الحكم النهائي",
    "judgement": "التحكيم",
}


def render(event: Event) -> None:
    if event.phase in ("proposal", "debate"):
        print(f"\n{event.agent.emoji} {event.agent.name}:\n{event.text}")
    elif event.phase == "review":
        for r in event.data.reviews:
            print(f"\n{event.agent.emoji} {event.agent.name} يراجع «{r.target}»: {r.verdict} ({r.score}/10)")
            for s in r.strengths:
                print(f"   + {s}")
            for i in r.issues:
                print(f"   - {i}")
            print(f"   ← {r.suggestion}")
    elif event.phase == "verdict":
        v = event.data
        print(f"\n🏛️  الجواب: {v.final_answer}\n\nالتعليل: {v.reasoning}\nالثقة: {v.confidence}")
        if v.dissent.strip():
            print(f"خلاف باقٍ: {v.dissent}")
    elif event.phase == "judgement":
        j = event.data
        print(f"\n{'✅ صحيح' if j.correct else '❌ خاطئ'} — {j.comment}")


def run(council: Council, task: str, **kwargs) -> bool | None:
    """يعرض المداولة ويعيد نتيجة التحكيم (None إن لم يكن هناك جواب مرجعي)."""
    phase, correct = None, None
    for event in council.deliberate(task, **kwargs):
        title = PHASE_TITLES[event.phase] + (f" — الجولة {event.round}" if event.round else "")
        if title != phase:
            phase = title
            print(f"\n{'═' * 12} {title} {'═' * 12}")
        render(event)
        if event.phase == "judgement":
            correct = event.data.correct
    return correct


def puzzle_ladder(council: Council) -> None:
    level, solved = 1, set()
    while level <= MAX_LEVEL:
        puzzle = pick(level, solved)
        print(f"\n\n🧩 المستوى {level}/{MAX_LEVEL} ({LEVEL_NAMES[level]}) — {puzzle.title}\n{puzzle.question}")
        note = input("\nفكرة أو تلميح للوكلاء (Enter للتخطي، q للخروج): ").strip()
        if note.lower() == "q":
            return
        if run(council, puzzle.question, reference=puzzle.answer, user_note=note):
            solved.add(puzzle.title)
            level += 1
        else:
            print(f"\nالجواب المرجعي: {puzzle.answer}\nسيحاول المجلس لغزاً آخر من المستوى نفسه.")
            solved.add(puzzle.title)
    print("\n🏆 أنهى المجلس المستويات كلها!")


def idea_mode(council: Council) -> None:
    idea = input("\nاكتب فكرتك أو مسألتك: ").strip()
    note = ""
    while idea:
        run(council, idea, kind="idea", user_note=note)
        note = input("\nتعليقك ليعيد المجلس النقاش في ضوئه (Enter للإنهاء): ").strip()
        if not note:
            return


def main() -> None:
    council = Council()
    print("مجلس الوكلاء 🧠  (1) ألغاز متدرجة الصعوبة   (2) ناقشوا فكرتي")
    choice = input("اختر 1 أو 2: ").strip()
    try:
        (idea_mode if choice == "2" else puzzle_ladder)(council)
    except (KeyboardInterrupt, EOFError):
        print()
    except CouncilError as e:
        print(f"\nتعذّر إكمال المداولة: {e}")
    except anthropic.AuthenticationError:
        print("\nمفتاح API غير صالح أو غير موجود: اضبط ANTHROPIC_API_KEY.")
    except anthropic.RateLimitError:
        print("\nتجاوزت حد الطلبات؛ انتظر قليلاً ثم أعد المحاولة.")
    except anthropic.APIStatusError as e:
        print(f"\nخطأ من الخادم ({e.status_code}): {e.message}")
    except anthropic.APIConnectionError:
        print("\nتعذّر الاتصال بالخادم؛ تحقق من الشبكة.")
    u = council.usage
    if u.calls:
        print(f"\n[{u.calls} نداء | رموز الإدخال {u.input_tokens:,} | رموز الإخراج {u.output_tokens:,}]")
