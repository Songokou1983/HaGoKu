"""HaGoKu Studio 统计分析核心 — 精、准、狠"""

from __future__ import annotations

from typing import Any

from ...config import AnalysisConfig

# 模块级配置（默认值，可由 Orchestrator 通过 set_analysis_config 覆盖）
try:
    from ... import config as _hagoku_config
    _config = AnalysisConfig()
except ImportError:
    _config = AnalysisConfig()


def set_analysis_config(config: AnalysisConfig) -> None:
    """供 Orchestrator 调用，更新模块级分析配置。"""
    global _config
    _config = config


def _insufficient_data(msg: str) -> dict[str, Any]:
    """返回数据不足的标准错误结果"""
    return {"error": "insufficient_data", "message": msg}
