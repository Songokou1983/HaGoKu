"""Backward-compatible re-export — canonical: hagoku.memory.projects._manager."""

from hagoku.memory.projects._manager import (  # noqa: F401
    AnalysisPatternDef,
    CleaningPrefDef,
    ColumnSemanticDef,
    MemoryCategory,
    MemoryManager,
    MemorySource,
    ProgressYaml,
)

__all__ = [
    "AnalysisPatternDef",
    "CleaningPrefDef",
    "ColumnSemanticDef",
    "MemoryCategory",
    "MemoryManager",
    "MemorySource",
    "ProgressYaml",
]
