"""HaGoKu Agent 层"""

# 共享类型（供所有 Agent 使用）
from .types import DataContext, ColumnSemantic, InteractionResult, SemanticType

# Agent 类（从独立包导入）
from .scout import ScoutAgent
from .cleaner import CleanerAgent
from .analyst import AnalystAgent, AnalysisResult
from .reporter import ReporterAgent

# 旧模块（向后兼容，过渡期使用）
from .base import DataAgentBase

__all__ = [
    "AnalysisResult",
    "AnalystAgent",
    "CleanerAgent",
    "ColumnSemantic",
    "DataContext",
    "DataAgentBase",
    "InteractionResult",
    "ReporterAgent",
    "ScoutAgent",
    "SemanticType",
]
