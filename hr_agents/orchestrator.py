"""المنسّق: يستقبل سؤال المستخدم، ويوزّعه على الـ Agents المناسبين (بالتوازي)، ثم يجمع الإجابة."""
from __future__ import annotations

from dataclasses import dataclass, field

import anthropic
import pandas as pd

from . import config
from .agents import AGENTS, AgentEvent, EventLog, run_agent, run_loop

ORCHESTRATOR_SYSTEM = f"""أنت منسّق فريق Agents للموارد البشرية في لوحة معلومات شركة (بيانات افتراضية).
لديك فريق من المتخصصين تستدعيهم كأدوات. لا تملك وصولاً مباشراً للبيانات، فكل رقم يجب أن يأتي من أحدهم.

طريقة العمل:
1. حدّد أي المتخصصين يلزمون للسؤال. إذا كان السؤال يحتاج أكثر من متخصص، فاستدعهم جميعاً في نفس الرد
   ليعملوا بالتوازي.
2. اكتب لكل متخصص مهمة واضحة ومحددة (واذكر القسم بالاسم العربي إن وُجد).
3. عند طلب تقرير: استدعِ أولاً المحللين اللازمين (عادة الدوران والاستقالات والرواتب) بالتوازي، ثم استدعِ
   ask_report_writer ومرّر له نتائجهم كاملة كما هي في المهمة.
4. اجمع النتائج في إجابة واحدة بالعربية، مختصرة ومنظمة بـ Markdown، دون تكرار ودون إضافة أرقام لم ترد
   من المتخصصين. إذا كتب كاتب التقارير تقريراً فاعرضه كما هو.
5. الأسئلة العامة غير المتعلقة بالموارد البشرية أو بالبيانات: اعتذر بلطف ووضّح ما يمكنك المساعدة فيه.
6. لا يتخذ الفريق قرارات بشأن الموظفين؛ احتفظ بعبارة "({config.HUMAN_REVIEW_NOTE})" بجانب التوصيات.

الأقسام المتاحة: تقنية المعلومات، المبيعات، الموارد البشرية، المالية، التسويق، العمليات، خدمة العملاء.
"""


def _agent_tools() -> list[dict]:
    return [
        {
            "name": f"ask_{spec.key}",
            "description": f"{spec.title}: {spec.description}",
            "input_schema": {
                "type": "object",
                "properties": {"task": {"type": "string", "description": "المهمة المطلوبة من هذا المتخصص بالتفصيل."}},
                "required": ["task"],
            },
        }
        for spec in AGENTS.values()
    ]


@dataclass
class TeamResult:
    answer: str
    events: list[AgentEvent] = field(default_factory=list)
    report: str | None = None   # نص التقرير إن كتبه كاتب التقارير
    error: str | None = None


def ask_team(question: str, df: pd.DataFrame, api_key: str | None = None,
             history: list[dict] | None = None) -> TeamResult:
    """نقطة الدخول: سؤال المستخدم + البيانات المفلترة ← إجابة الفريق.

    history: رسائل سابقة بصيغة [{"role": "user"|"assistant", "content": "نص"}].
    """
    client = anthropic.Anthropic(api_key=api_key, timeout=config.REQUEST_TIMEOUT, max_retries=2)
    log = EventLog()
    outputs: dict[str, str] = {}

    def handler(name: str, args: dict) -> str:
        key = name.removeprefix("ask_")
        if key not in AGENTS:
            raise KeyError(f"متخصص غير معروف: {name}")
        out = run_agent(client, key, str(args.get("task", "")), df, log)
        outputs[key] = out
        return out

    scope = f"عدد السجلات بعد الفلترة: {len(df)}، الأقسام في البيانات: {', '.join(sorted(df['القسم'].unique()))}."
    recent = [m for m in (history or []) if m.get("content")][-config.HISTORY_TURNS:]
    while recent and recent[0]["role"] != "user":   # يجب أن تبدأ المحادثة برسالة من المستخدم
        recent.pop(0)

    try:
        answer = run_loop(
            client,
            agent_name="orchestrator",
            system=ORCHESTRATOR_SYSTEM,
            user_content=f"{question}\n\n(سياق البيانات: {scope})",
            tools=_agent_tools(),
            handler=handler,
            effort=config.ORCHESTRATOR_EFFORT,
            log=log,
            history=recent,
        )
        return TeamResult(answer=answer, events=log.events, report=outputs.get("report_writer"))
    except anthropic.AuthenticationError:
        err = "مفتاح API غير صالح. تحقق من ANTHROPIC_API_KEY."
    except anthropic.PermissionDeniedError:
        err = "المفتاح لا يملك صلاحية لهذا النموذج."
    except anthropic.NotFoundError:
        err = f"النموذج '{config.MODEL}' غير متاح. غيّره بمتغير البيئة HR_AGENTS_MODEL."
    except anthropic.RateLimitError:
        err = "تم تجاوز حد الطلبات. حاول بعد قليل."
    except anthropic.APITimeoutError:
        err = "انتهت مهلة الطلب. حاول مرة أخرى أو اطرح سؤالاً أبسط."
    except anthropic.APIConnectionError:
        err = "تعذّر الاتصال بخدمة Claude. تحقق من الإنترنت."
    except anthropic.APIStatusError as exc:
        err = f"خطأ من الخدمة ({exc.status_code}): {exc.message}"
    return TeamResult(answer="", events=log.events, error=err)
