"""مجلس الوكلاء: حل مستقل ← نقاش ← مراجعة أقران ← حكم نهائي (← تحكيم للألغاز).

`Council.deliberate()` مولِّد يُخرج `Event` بعد كل مساهمة، فتستطيع أي واجهة
(طرفية أو متصفح) عرض النقاش أثناء حدوثه.
"""

from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Iterator, Literal, TypeVar

import anthropic
from pydantic import BaseModel

MODEL = os.environ.get("PUZZLE_AGENTS_MODEL", "claude-opus-5-5")
EFFORT = os.environ.get("PUZZLE_AGENTS_EFFORT", "high")
MAX_TOKENS = 16000
# عند رفض النموذج الأساسي للطلب يعيد الخادم تشغيله على نموذج بديل داخل النداء نفسه.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


# ---------------------------------------------------------------- الوكلاء
@dataclass(frozen=True)
class Agent:
    name: str
    emoji: str
    persona: str


AGENTS: tuple[Agent, ...] = (
    Agent(
        "المحلل",
        "🧮",
        "أسلوبك الاستدلال الصارم: تصوغ المسألة بدقة، وتتقدم خطوة خطوة، وتتحقق من الحساب "
        "ومن أن الحل يستوفي كل شرط ورد في النص.",
    ),
    Agent(
        "المبدع",
        "💡",
        "أسلوبك التفكير الجانبي: تبحث عن الخدعة في الصياغة، وعن القراءة غير المتوقعة للنص، "
        "وعن زاوية تجعل المسألة أبسط مما تبدو.",
    ),
    Agent(
        "المشكك",
        "🔍",
        "أسلوبك الشك المنهجي: تبحث عن الافتراضات غير المعلنة، وتجرّب الحالات الصغيرة والحدّية "
        "والأمثلة المضادة قبل أن تقبل أي جواب، ومنها جوابك أنت.",
    ),
)


# ---------------------------------------------------------- مخرجات منظَّمة
class Review(BaseModel):
    target: str  # اسم الزميل صاحب الحل
    verdict: Literal["مقبول", "تعديلات طفيفة", "تعديلات جوهرية", "مرفوض"]
    score: int  # من 1 إلى 10
    strengths: list[str]
    issues: list[str]
    suggestion: str


class ReviewSet(BaseModel):
    reviews: list[Review]


class Verdict(BaseModel):
    final_answer: str
    reasoning: str
    confidence: Literal["منخفضة", "متوسطة", "عالية"]
    dissent: str  # ما بقي من خلاف، أو نص فارغ


class Judgement(BaseModel):
    correct: bool
    comment: str


@dataclass
class Event:
    phase: Literal["proposal", "debate", "review", "verdict", "judgement"]
    agent: Agent | None = None
    text: str = ""
    data: BaseModel | None = None
    round: int = 0


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0


class CouncilError(RuntimeError):
    """رد لا يمكن البناء عليه (رفض، أو انقطاع عند حد الرموز)."""


T = TypeVar("T", bound=BaseModel)
Kind = Literal["puzzle", "idea"]

_KIND = {
    "puzzle": dict(
        noun="اللغز",
        mission="حل لغز",
        propose="قدّم حلك: الجواب أولاً، ثم التعليل خطوة خطوة.",
    ),
    "idea": dict(
        noun="فكرة المستخدم",
        mission="دراسة فكرة طرحها المستخدم وتقديم حل عملي لها",
        propose="قدّم تحليلك: ما المشكلة الحقيقية خلف الفكرة، وما الحل أو الخطة التي تقترحها، "
        "وما أهم مخاطرها وكيف تُعالج.",
    ),
}


# ---------------------------------------------------------------- المجلس
@dataclass
class Council:
    client: anthropic.Anthropic = field(default_factory=anthropic.Anthropic)
    agents: tuple[Agent, ...] = AGENTS
    model: str = MODEL
    effort: str = EFFORT
    rounds: int = 1  # عدد جولات النقاش بعد الحلول المستقلة
    usage: Usage = field(default_factory=Usage)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    # ---- نداءات النموذج
    def _request(self, system: str, prompt: str) -> dict:
        return dict(
            model=self.model,
            max_tokens=MAX_TOKENS,
            thinking={"type": "adaptive"},
            output_config={"effort": self.effort},
            betas=[FALLBACK_BETA],
            fallbacks="default",
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )

    def _send(self, method, **request):
        try:
            response = method(**request)
        except TypeError as e:  # هكذا تبلّغ المكتبة عن غياب بيانات الاعتماد
            if "authentication" not in str(e):
                raise
            raise CouncilError(
                "لا توجد بيانات اعتماد: اضبط متغير البيئة ANTHROPIC_API_KEY."
            ) from e
        self._check(response)
        return response

    def _check(self, response) -> None:
        with self._lock:  # النداءات تجري في خيوط متوازية
            self.usage.calls += 1
            self.usage.input_tokens += response.usage.input_tokens
            self.usage.output_tokens += response.usage.output_tokens
        if response.stop_reason == "refusal":
            raise CouncilError("رفض النموذج هذا الطلب لأسباب تتعلق بالسلامة.")
        if response.stop_reason == "max_tokens":
            raise CouncilError("انقطع الرد عند حد الرموز؛ جرّب مستوى جهد أقل (PUZZLE_AGENTS_EFFORT).")

    def _ask(self, system: str, prompt: str) -> str:
        response = self._send(self.client.beta.messages.create, **self._request(system, prompt))
        return "\n".join(b.text for b in response.content if b.type == "text").strip()

    def _ask_structured(self, system: str, prompt: str, schema: type[T]) -> T:
        response = self._send(
            self.client.beta.messages.parse, **self._request(system, prompt), output_format=schema
        )
        if response.parsed_output is None:
            raise CouncilError("لم يُرجع النموذج مخرجات بالصيغة المطلوبة.")
        return response.parsed_output

    def _parallel(self, fn, items) -> Iterator:
        """ينفّذ نداءات الوكلاء بالتوازي ويُخرج النتائج بترتيب الوكلاء."""
        with ThreadPoolExecutor(max_workers=len(self.agents)) as pool:
            yield from pool.map(fn, items)

    # ---- المداولة
    def deliberate(
        self,
        task: str,
        *,
        kind: Kind = "puzzle",
        reference: str | None = None,
        user_note: str = "",
    ) -> Iterator[Event]:
        """يدير مداولة كاملة حول `task`.

        `user_note`: فكرة أو تلميح من المستخدم يُعرض على الوكلاء مع المسألة.
        `reference`: الجواب المرجعي؛ إن وُجد يُحكَّم الحكم النهائي عليه (ولا يراه الوكلاء).
        """
        k = _KIND[kind]
        brief = f"## {k['noun']}\n{task}"
        if user_note.strip():
            brief += (
                "\n\n## ملاحظة من المستخدم\n"
                f"{user_note.strip()}\n"
                "(خذها بجدية وناقشها، لكنها قد تكون خاطئة: اقبلها أو ارفضها بالدليل.)"
            )

        def system(agent: Agent) -> str:
            others = "، ".join(a.name for a in self.agents if a is not agent)
            return (
                f"أنت «{agent.name}»، عضو في مجلس خبراء يتعاون على {k['mission']}، "
                f"وزملاؤك فيه: {others}. {agent.persona}\n"
                "غاية المجلس الوصول إلى الصواب لا الانتصار للرأي. اكتب بالعربية وبإيجاز؛ "
                "زملاؤك يقرؤون نصك كما هو ولا يرون ما دار في ذهنك، فاذكر كل ما يلزم للتحقق من كلامك."
            )

        # 1) حلول مستقلة: لا يرى أحد حل غيره، كي لا ينجرّ الجميع وراء أول رأي.
        def propose(agent: Agent) -> str:
            return self._ask(
                system(agent),
                f"{brief}\n\n## المطلوب\nلم ترَ حلول زملائك بعد ولم يروا حلك. {k['propose']}",
            )

        positions: dict[str, str] = {}
        for agent, text in zip(self.agents, self._parallel(propose, self.agents)):
            positions[agent.name] = text
            yield Event("proposal", agent, text)

        # 2) جولات نقاش: كل وكيل يقرأ مواقف زملائه ويردّ ويحدّث موقفه.
        for rnd in range(1, self.rounds + 1):
            snapshot = dict(positions)

            def debate(agent: Agent) -> str:
                others = "\n\n".join(
                    f"### موقف «{name}»\n{text}"
                    for name, text in snapshot.items()
                    if name != agent.name
                )
                return self._ask(
                    system(agent),
                    f"{brief}\n\n## موقفك السابق\n{snapshot[agent.name]}\n\n"
                    f"## مواقف زملائك\n{others}\n\n"
                    "## المطلوب\nناقش زملاءك: أين تتفق معهم وأين تختلف، ولماذا. إن وجدت خطأ عند "
                    "أحدهم فحدده بدقة، وإن أقنعك أحدهم فغيّر رأيك صراحة. "
                    "اختم بفقرة تبدأ بـ«موقفي الآن:» فيها حلك المحدَّث كاملاً بحيث يُفهم دون الرجوع لما سبق.",
                )

            for agent, text in zip(self.agents, self._parallel(debate, self.agents)):
                positions[agent.name] = text
                yield Event("debate", agent, text, round=rnd)

        # 3) مراجعة الأقران: كل وكيل يقيّم الموقف النهائي لكل زميل تقييماً منظَّماً.
        def review(agent: Agent) -> ReviewSet:
            others = "\n\n".join(
                f"### حل «{name}»\n{text}" for name, text in positions.items() if name != agent.name
            )
            return self._ask_structured(
                system(agent),
                f"{brief}\n\n## حلول زملائك بعد النقاش\n{others}\n\n"
                "## المطلوب\nراجع كل حل مراجعة أقران مستقلة: تحقق من كل خطوة بنفسك بدل أن تثق بها، "
                "واختبر الحل على شروط المسألة كلها. لكل زميل أعطِ مراجعة واحدة: target اسمه، والحكم، "
                "ودرجة من 1 إلى 10، ونقاط القوة، والمشكلات (قائمة فارغة إن لم تجد)، واقتراحاً واحداً للتحسين.",
                ReviewSet,
            )

        reviews: dict[str, ReviewSet] = {}
        for agent, result in zip(self.agents, self._parallel(review, self.agents)):
            reviews[agent.name] = result
            yield Event("review", agent, data=result)

        # 4) الحكم النهائي: منسّق يرجّح الحجة التي صمدت أمام المراجعة، لا رأي الأغلبية.
        dossier = "\n\n".join(
            f"### الحل النهائي لـ«{name}»\n{text}" for name, text in positions.items()
        )
        dossier += "\n\n## مراجعات الأقران\n" + "\n".join(
            f"- «{reviewer}» عن «{r.target}»: {r.verdict} ({r.score}/10). "
            f"المشكلات: {'؛ '.join(r.issues) or 'لا شيء'}. الاقتراح: {r.suggestion}"
            for reviewer, rs in reviews.items()
            for r in rs.reviews
        )
        verdict = self._ask_structured(
            "أنت «المنسق»، رئيس مجلس الخبراء. تصوغ القرار النهائي بعد قراءة الحلول ومراجعات الأقران. "
            "لا تحسم بالأغلبية: رجّح الحجة التي صمدت أمام المراجعة، وتحقق منها بنفسك قبل اعتمادها. "
            "اكتب بالعربية لمستخدم لم يقرأ النقاش.",
            f"{brief}\n\n{dossier}\n\n"
            "## المطلوب\nاكتب الحكم النهائي: final_answer الجواب أو الحل المعتمد واضحاً ومكتفياً بنفسه؛ "
            "reasoning لماذا هو صحيح باختصار؛ confidence مدى الثقة؛ "
            "dissent ما بقي من خلاف لم يُحسم (نص فارغ إن أجمع المجلس).",
            Verdict,
        )
        yield Event("verdict", data=verdict)

        # 5) التحكيم (للألغاز ذات الجواب المرجعي فقط).
        if reference:
            judgement = self._ask_structured(
                "أنت حَكَم محايد تقارن جواب المجلس بالجواب المرجعي للغز. الجواب صحيح إذا طابق المرجعي "
                "في المضمون ولو اختلفت الصياغة أو الطريقة؛ وخاطئ إذا خالفه في النتيجة أو أغفل جزءاً مطلوباً.",
                f"## اللغز\n{task}\n\n## الجواب المرجعي\n{reference}\n\n"
                f"## جواب المجلس\n{verdict.final_answer}\n\n{verdict.reasoning}",
                Judgement,
            )
            yield Event("judgement", data=judgement)
