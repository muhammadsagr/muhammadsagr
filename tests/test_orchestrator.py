"""اختبار حلقة المنسّق والـ Agents بعميل وهمي (لا يحتاج مفتاح API ولا إنترنت)."""
import sys
import threading
from pathlib import Path
from types import SimpleNamespace as NS

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hr_agents import config, orchestrator  # noqa: E402
from tests.test_tools import emp  # noqa: E402


def tool_use(id_, name, input_):
    return NS(type="tool_use", id=id_, name=name, input=input_)


def text(t):
    return NS(type="text", text=t)


class FakeMessages:
    """يحاكي Claude: المنسّق يستدعي متخصصَين معاً، وكل متخصص يستدعي أداته الأولى ثم يجيب."""

    def __init__(self):
        self.calls = []
        self.lock = threading.Lock()
        self.threads = set()

    def create(self, **kw):
        kw = {**kw, "messages": list(kw["messages"])}   # لقطة لحظة الطلب كما يفعل SDK
        with self.lock:
            self.calls.append(kw)
            self.threads.add(threading.get_ident())
        last = kw["messages"][-1]["content"]
        got_results = isinstance(last, list) and any(b.get("type") == "tool_result" for b in last)
        names = [t["name"] for t in kw.get("tools", [])]

        if kw["system"] == orchestrator.ORCHESTRATOR_SYSTEM:
            if got_results:
                joined = " | ".join(b["content"] for b in last if b.get("type") == "tool_result")
                return NS(stop_reason="end_turn", content=[text(f"الخلاصة: {joined}")])
            return NS(stop_reason="tool_use", content=[
                NS(type="thinking", thinking="", signature="x"),
                tool_use("o1", "ask_turnover_analyst", {"task": "حلل الدوران في المبيعات"}),
                tool_use("o2", "ask_pay_equity_auditor", {"task": "راجع فجوة الرواتب"}),
            ])

        if got_results or not names:
            result = last[0]["content"] if got_results else ""
            return NS(stop_reason="end_turn", content=[text(f"نتيجة المتخصص ({len(result)} حرف)")])
        return NS(stop_reason="tool_use", content=[tool_use("t1", names[0], {"department": "المبيعات"})])


@pytest.fixture
def fake_client(monkeypatch):
    msgs = FakeMessages()
    client = NS(messages=msgs, beta=NS(messages=msgs))
    monkeypatch.setattr(orchestrator.anthropic, "Anthropic", lambda **kw: client)
    return msgs


@pytest.fixture
def df():
    return pd.DataFrame([emp(1), emp(2), emp(3, exit_date="2025-09-01", reason="الراتب"),
                         emp(4, dept="المالية", title="محاسب")])


def test_team_flow(fake_client, df):
    result = orchestrator.ask_team("لماذا الدوران مرتفع في المبيعات؟", df, api_key="test")
    assert result.error is None
    assert result.answer.startswith("الخلاصة:")
    assert result.answer.count("نتيجة المتخصص") == 2

    called = [(e.agent, e.kind, e.name) for e in result.events]
    assert ("orchestrator", "agent", "ask_turnover_analyst") in called
    assert ("orchestrator", "agent", "ask_pay_equity_auditor") in called
    assert ("turnover_analyst", "tool", "turnover_by_department") in called
    assert ("pay_equity_auditor", "tool", "salary_gap_by_gender") in called

    # تفعيل البديل عند الرفض للنموذج الافتراضي، ولا يُستخدم tool_choice الإجباري
    for call in fake_client.calls:
        assert call["fallbacks"] == "default" and call["betas"] == [config.FALLBACK_BETA]
        assert call.get("tool_choice", {"type": "auto"})["type"] in ("auto", "none")
    # المتخصصان عملا بالتوازي (أكثر من خيط)
    assert len(fake_client.threads) > 1


def test_assistant_content_passed_back_unchanged(fake_client, df):
    orchestrator.ask_team("سؤال", df, api_key="test")
    second_orch_call = [c for c in fake_client.calls if c["system"] == orchestrator.ORCHESTRATOR_SYSTEM][1]
    assistant = second_orch_call["messages"][-2]
    assert assistant["role"] == "assistant"
    assert assistant["content"][0].type == "thinking"      # كتل التفكير تُعاد كما هي
    results = second_orch_call["messages"][-1]["content"]
    assert [r["tool_use_id"] for r in results] == ["o1", "o2"]   # كل النتائج في رسالة واحدة


def test_history_starts_with_user(fake_client, df):
    history = [{"role": "assistant", "content": "مرحبا"}, {"role": "user", "content": "س1"},
               {"role": "assistant", "content": "ج1"}]
    orchestrator.ask_team("س2", df, api_key="test", history=history)
    first = fake_client.calls[0]["messages"]
    assert first[0]["role"] == "user" and first[0]["content"] == "س1"
    assert first[-1]["content"].startswith("س2")
