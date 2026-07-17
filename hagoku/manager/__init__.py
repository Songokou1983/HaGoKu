"""HaGoKu Studio Manager 编排层"""

__all__ = [
    "Orchestrator",
]


def __getattr__(name: str):
    if name == "Orchestrator":
        from .orchestrator import Orchestrator
        return Orchestrator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
