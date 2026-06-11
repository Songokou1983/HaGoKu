"""HaGoKu Studio 数据持久化"""

from .artifact import ArtifactManager, DataArtifact
from .database import HaGoKuDB
from .output import OutputManager

__all__ = [
    "ArtifactManager",
    "DataArtifact",
    "HaGoKuDB",
    "MemoryManager",
    "OutputManager",
]


def __getattr__(name: str):
    if name == "MemoryManager":
        from .memory import MemoryManager
        return MemoryManager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
