"""مجلس وكلاء يحل الألغاز ويناقش أفكار المستخدم مع مراجعة أقران."""

from .council import AGENTS, Agent, Council, CouncilError, Event, Judgement, Review, ReviewSet, Verdict
from .puzzles import LEVEL_NAMES, MAX_LEVEL, PUZZLES, Puzzle, pick, puzzles_for

__all__ = [
    "AGENTS", "Agent", "Council", "CouncilError", "Event", "Judgement", "Review", "ReviewSet",
    "Verdict", "LEVEL_NAMES", "MAX_LEVEL", "PUZZLES", "Puzzle", "pick", "puzzles_for",
]
