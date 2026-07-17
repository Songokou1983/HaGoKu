"""Backward-compatible re-export — canonical: hagoku.memory.projects._manager."""

from hagoku.memory.projects._manager import (  # noqa: F401
    ColumnSemanticDef,
    MemoryManager,
)

__all__ = [
    "ColumnSemanticDef",
    "MemoryManager",
]
