"""HaGoKu 三层记忆体系：① 方法库 ② 成长记忆 ③ 项目记忆."""

from hagoku.memory.lessons import LESSON_RECALL_WARNING, Lesson, LessonStore

__all__ = [
    "LESSON_RECALL_WARNING",
    "Lesson",
    "LessonStore",
    "MemoryManager",
    "ColumnSemanticDef",
]


def __getattr__(name: str):
    if name == "MemoryManager":
        from hagoku.memory.projects._manager import MemoryManager
        return MemoryManager
    if name == "ColumnSemanticDef":
        from hagoku.memory.projects._manager import ColumnSemanticDef
        return ColumnSemanticDef
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
