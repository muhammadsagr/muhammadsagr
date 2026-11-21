"""إعدادات فريق الـ Agents: النموذج، المفتاح، والحدود."""
import os

# النموذج الافتراضي، ويمكن تغييره بمتغير البيئة HR_AGENTS_MODEL
MODEL = os.getenv("HR_AGENTS_MODEL", "claude-sonnet-5-5")

# مستوى الجهد (effort): low | medium | high | xhigh | max
ORCHESTRATOR_EFFORT = os.getenv("HR_AGENTS_ORCHESTRATOR_EFFORT", "medium")
AGENT_EFFORT = os.getenv("HR_AGENTS_EFFORT", "medium")

MAX_TOOL_ROUNDS = 8          # أقصى عدد جولات استدعاء أدوات لكل Agent
REQUEST_TIMEOUT = 120.0      # مهلة كل طلب بالثواني
MAX_TOKENS = 16000
MAX_PARALLEL = 5             # أقصى عدد أدوات/Agents تعمل بالتوازي
HISTORY_TURNS = 6            # عدد رسائل المحادثة السابقة التي تُرسل للمنسّق

# عند رفض الطلب لأسباب السلامة يُعاد تشغيله تلقائياً على نموذج بديل (من جهة الخادم).
# مفعّل فقط للنماذج التي تدعم ذلك.
FALLBACK_BETA = "server-side-fallback-2026-07-01"
FALLBACK_MODELS = {"claude-sonnet-5-5", "claude-opus-5-5", "claude-opus-5", "claude-fable-5-2", "claude-fable-5-1"}

HUMAN_REVIEW_NOTE = "تتطلب مراجعة بشرية"


def find_api_key(secrets=None) -> str | None:
    """يبحث عن المفتاح في متغيرات البيئة ثم في st.secrets. لا يُكتب المفتاح في الكود أبداً."""
    key = os.getenv("ANTHROPIC_API_KEY")
    if key:
        return key
    if secrets is not None:
        try:
            return secrets.get("ANTHROPIC_API_KEY")
        except Exception:  # لا يوجد ملف secrets.toml
            return None
    return None
