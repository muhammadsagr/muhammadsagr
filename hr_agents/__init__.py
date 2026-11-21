"""فريق Agents للموارد البشرية: منسّق + 5 وكلاء متخصصين يعملون على بيانات اللوحة."""
from .orchestrator import AgentEvent, TeamResult, ask_team

__all__ = ["ask_team", "TeamResult", "AgentEvent"]
