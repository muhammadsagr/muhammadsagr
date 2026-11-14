"""اختبار تدفق المداولة بعميل وهمي (بلا شبكة ولا مفتاح)."""

from types import SimpleNamespace

from puzzle_agents import AGENTS, MAX_LEVEL, Council, Judgement, Review, ReviewSet, Verdict, puzzles_for


class FakeMessages:
    def __init__(self):
        self.calls = []

    def _response(self, **extra):
        usage = SimpleNamespace(input_tokens=10, output_tokens=5)
        return SimpleNamespace(stop_reason="end_turn", usage=usage, **extra)

    def create(self, **kw):
        self.calls.append(kw)
        return self._response(content=[SimpleNamespace(type="text", text="موقفي الآن: الحفرة")])

    def parse(self, *, output_format, **kw):
        self.calls.append({**kw, "output_format": output_format})
        if output_format is ReviewSet:
            out = ReviewSet(reviews=[Review(target="المبدع", verdict="مقبول", score=9,
                                            strengths=["واضح"], issues=[], suggestion="لا شيء")])
        elif output_format is Verdict:
            out = Verdict(final_answer="الحفرة", reasoning="…", confidence="عالية", dissent="")
        else:
            out = Judgement(correct=True, comment="مطابق")
        return self._response(parsed_output=out)


def fake_council(**kw):
    messages = FakeMessages()
    client = SimpleNamespace(beta=SimpleNamespace(messages=messages))
    return Council(client=client, **kw), messages


def test_puzzle_flow_order_and_call_count():
    council, messages = fake_council(rounds=2)
    events = list(council.deliberate("لغز", reference="الحفرة", user_note="تلميح"))
    n = len(AGENTS)
    assert [e.phase for e in events] == (
        ["proposal"] * n + ["debate"] * 2 * n + ["review"] * n + ["verdict", "judgement"]
    )
    assert [e.agent.name for e in events[:n]] == [a.name for a in AGENTS]
    assert events[-1].data.correct
    assert council.usage.calls == len(messages.calls) == 4 * n + 2
    assert all("تلميح" in c["messages"][0]["content"] for c in messages.calls[:-1])
    # الجواب المرجعي لا يصل إلا للحَكَم
    assert all("الجواب المرجعي" not in c["messages"][0]["content"] for c in messages.calls[:-1])


def test_idea_flow_has_no_judgement():
    council, _ = fake_council()
    phases = [e.phase for e in council.deliberate("فكرة", kind="idea")]
    assert phases[-1] == "verdict" and "judgement" not in phases


def test_every_level_has_puzzles():
    assert all(len(puzzles_for(level)) >= 3 for level in range(1, MAX_LEVEL + 1))
