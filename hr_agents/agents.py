"""تعريف الـ Agents الخمسة وحلقة استدعاء الأدوات (tool use) المشتركة بينها."""
from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable

import anthropic
import pandas as pd

from . import config
from .tools import TOOL_SPECS, run_tool


# ================================================================ سجل الأحداث
@dataclass
class AgentEvent:
    agent: str      # من قام بالاستدعاء
    kind: str       # "agent" أو "tool"
    name: str       # اسم الـ Agent أو الأداة المستدعاة
    detail: str = ""


@dataclass
class EventLog:
    events: list[AgentEvent] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, *args, **kwargs) -> None:
        with self._lock:
            self.events.append(AgentEvent(*args, **kwargs))


# ================================================================ حلقة tool use العامة
def _create(client: anthropic.Anthropic, **kwargs):
    """طلب واحد إلى Claude، مع تفعيل البديل التلقائي عند الرفض إن كان النموذج يدعمه."""
    if config.MODEL in config.FALLBACK_MODELS:
        return client.beta.messages.create(betas=[config.FALLBACK_BETA], fallbacks="default", **kwargs)
    return client.messages.create(**kwargs)


def _text(response) -> str:
    return "\n".join(b.text for b in response.content if b.type == "text").strip()


ToolHandler = Callable[[str, dict], dict | str]


def run_loop(
    client: anthropic.Anthropic,
    *,
    agent_name: str,
    system: str,
    user_content: str,
    tools: list[dict],
    handler: ToolHandler,
    effort: str,
    log: EventLog,
    history: list[dict] | None = None,
) -> str:
    """يشغّل Agent حتى ينهي إجابته: يستدعي الأدوات بالتوازي ويعيد نتائجها، بحد أقصى MAX_TOOL_ROUNDS."""
    messages = list(history or []) + [{"role": "user", "content": user_content}]
    base = dict(model=config.MODEL, max_tokens=config.MAX_TOKENS, system=system,
                output_config={"effort": effort})
    if tools:
        base["tools"] = tools

    for round_no in range(config.MAX_TOOL_ROUNDS + 1):
        last_round = round_no == config.MAX_TOOL_ROUNDS
        extra = {"tool_choice": {"type": "none"}} if (last_round and tools) else {}
        response = _create(client, messages=messages, **base, **extra)

        if response.stop_reason == "refusal":
            return (_text(response) + "\n\n" if _text(response) else "") + "⚠️ تعذّرت معالجة هذا الطلب."
        if response.stop_reason != "tool_use":
            text = _text(response)
            if response.stop_reason == "max_tokens":
                text += "\n\n⚠️ (الإجابة مقطوعة لأنها بلغت الحد الأقصى للطول)"
            return text

        # أعِد المحتوى كما هو (بما فيه كتل التفكير) ثم نتائج كل الأدوات في رسالة واحدة
        messages.append({"role": "assistant", "content": response.content})
        calls = [b for b in response.content if b.type == "tool_use"]

        def execute(block):
            log.add(agent_name, "agent" if block.name.startswith("ask_") else "tool", block.name,
                    json.dumps(block.input, ensure_ascii=False))
            try:
                out = handler(block.name, dict(block.input))
                content = out if isinstance(out, str) else json.dumps(out, ensure_ascii=False, default=str)
                return {"type": "tool_result", "tool_use_id": block.id, "content": content}
            except Exception as exc:  # أعِد الخطأ للنموذج بدل أن يتعطل التطبيق
                return {"type": "tool_result", "tool_use_id": block.id, "is_error": True,
                        "content": f"فشل تنفيذ الأداة: {exc}"}

        with ThreadPoolExecutor(max_workers=config.MAX_PARALLEL) as pool:
            results = list(pool.map(execute, calls))

        if round_no == config.MAX_TOOL_ROUNDS - 1:
            results.append({"type": "text",
                            "text": "بلغت الحد الأقصى لاستدعاء الأدوات. اكتب إجابتك النهائية الآن مما لديك."})
        messages.append({"role": "user", "content": results})

    return "⚠️ لم يكتمل التحليل ضمن الحد المسموح من الخطوات."


# ================================================================ تعريف الـ Agents
COMMON_RULES = f"""
قواعد ملزمة:
- اكتب بالعربية الفصحى المختصرة وبتنسيق Markdown (عناوين قصيرة ونقاط وجداول عند الحاجة).
- كل رقم تذكره يجب أن يأتي من نتيجة أداة. لا تخمّن ولا تحسب أرقاماً جديدة من عندك، ولا تختلق بيانات.
- البيانات افتراضية وقد تكون مفلترة من المستخدم؛ إذا كانت العينة صغيرة فقل ذلك صراحة.
- أنت لا تتخذ قرارات تخص أي موظف. كل توصية هي اقتراح يُكتب بجانبه: "({config.HUMAN_REVIEW_NOTE})".
- إذا أعادت أداة خطأً (مثل اسم قسم غير موجود) فصحّح المدخلات وأعد المحاولة مرة واحدة.
"""


@dataclass(frozen=True)
class AgentSpec:
    key: str
    title: str
    description: str   # يظهر للمنسّق ليعرف متى يستدعيه
    system: str
    tools: tuple[str, ...]


AGENTS: dict[str, AgentSpec] = {
    spec.key: spec
    for spec in [
        AgentSpec(
            key="turnover_analyst",
            title="📉 محلل الدوران",
            description="يحلل ترك العمل: معدلات الدوران حسب القسم، الأسباب، الاتجاه السنوي، ومدة الخدمة عند الترك. "
                        "يعيد أعلى 3 مخاطر مع الدليل الرقمي والتوصيات.",
            system="أنت محلل دوران وظيفي في إدارة الموارد البشرية.\n"
                   "مهمتك: تحديد أعلى 3 مخاطر تتعلق بترك العمل، ولكل خطر: الدليل الرقمي من الأدوات، ثم توصية عملية.\n"
                   "ابدأ بالأدوات العامة ثم تعمّق في القسم المعني إن وُجد."
                   + COMMON_RULES
                   + "- لا تذكر أسماء موظفين.",
            tools=("turnover_by_department", "exit_reasons_breakdown", "turnover_trend_by_year", "tenure_at_exit"),
        ),
        AgentSpec(
            key="attrition_predictor",
            title="🔮 متنبئ الاستقالات",
            description="يحدد الموظفين النشطين الأعلى خطراً لترك العمل بدرجة 0-100 وأسباب كل منهم. "
                        "يمكن تحديد قسم معين.",
            system="أنت متخصص في التنبؤ بخطر الاستقالة.\n"
                   "استخدم أداة risk_scores، ثم اعرض أعلى الموظفين خطراً في جدول (الرقم الوظيفي، الاسم، القسم، "
                   "الدرجة، الأسباب)، ثم 2-3 توصيات وقائية عامة.\n"
                   "اشرح باختصار قواعد الحساب، وأكّد أنها لا تستخدم الجنس أو العمر أو المدينة.\n"
                   "اختم بتنبيه: النتيجة إرشادية مبنية على قواعد بسيطة وليست قراراً بشأن أي موظف."
                   + COMMON_RULES,
            tools=("risk_scores",),
        ),
        AgentSpec(
            key="pay_equity_auditor",
            title="⚖️ مراجع الرواتب",
            description="يراجع عدالة الرواتب: الفجوة بين الجنسين داخل نفس الوظيفة، الرواتب حسب المؤهل، "
                        "وعلاقة الراتب بالأداء.",
            system="أنت مراجع عدالة الأجور.\n"
                   "اعرض الفجوات التي تتجاوز 5% وعينتها كافية فقط كنتائج، مع حجم العينة لكل منها. "
                   "المجموعات ذات العينة غير الكافية (أقل من 5 لكل جنس) اذكر عددها فقط وارفض الاستنتاج منها.\n"
                   "علّق أيضاً على علاقة الراتب بالأداء والمؤهل إن كان السؤال يتطلب ذلك."
                   + COMMON_RULES
                   + "- لا تذكر أسماء موظفين.",
            tools=("salary_gap_by_gender", "salary_by_education", "salary_vs_performance"),
        ),
        AgentSpec(
            key="policy_assistant",
            title="📘 مساعد السياسات",
            description="يجيب عن أسئلة سياسات الشركة (الإجازات، العمل عن بُعد، التدريب) من ملفات السياسات فقط.",
            system="أنت مساعد سياسات الموارد البشرية.\n"
                   "اعرض قائمة السياسات، واقرأ الملف المناسب، ثم أجب فقط مما ورد فيه، واذكر اسم الملف المصدر "
                   "في آخر الإجابة بصيغة: المصدر: `اسم_الملف`.\n"
                   "إذا لم تجد الإجابة في الملفات فقل صراحة: \"لم أجد هذه المعلومة في سياسات الشركة المتاحة\"، "
                   "واقترح التواصل مع إدارة الموارد البشرية. لا تستخدم معلوماتك العامة.\n"
                   "اكتب بالعربية وباختصار.",
            tools=("list_policies", "read_policy"),
        ),
        AgentSpec(
            key="report_writer",
            title="📝 كاتب التقارير",
            description="يكتب تقريراً تنفيذياً للإدارة من النتائج التي جمعها بقية الـ Agents. "
                        "مرّر له كل النتائج كاملة في المهمة.",
            system="أنت كاتب تقارير تنفيذية لإدارة الموارد البشرية.\n"
                   "اكتب تقريراً بالعربية بصيغة Markdown بهذه الأقسام بالترتيب:\n"
                   "# عنوان التقرير\n## الملخص التنفيذي\n## أهم المؤشرات\n## المخاطر\n## التوصيات\n## الخطوات التالية\n"
                   "استخدم فقط الأرقام الواردة في المدخلات ولا تضف أرقاماً جديدة. "
                   "إذا كان قسم ما بلا بيانات فاكتب ذلك. اكتب بجانب كل توصية: "
                   f"\"({config.HUMAN_REVIEW_NOTE})\". اجعل التقرير في صفحة إلى صفحتين.",
            tools=(),
        ),
    ]
}


def run_agent(client: anthropic.Anthropic, key: str, task: str, df: pd.DataFrame, log: EventLog) -> str:
    """تشغيل Agent متخصص على مهمة نصية وبيانات مفلترة."""
    spec = AGENTS[key]
    return run_loop(
        client,
        agent_name=key,
        system=spec.system,
        user_content=task,
        tools=[TOOL_SPECS[t] for t in spec.tools],
        handler=lambda name, args: run_tool(name, args, df),
        effort=config.AGENT_EFFORT,
        log=log,
    )
