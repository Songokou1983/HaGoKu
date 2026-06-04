"""F-055 验证（已 RESOLVED）：_generate_phase_message / _try_generate_phase_llm
已在事件驱动重构（F-078）中随旧 phase 分支一同删除。

F-055 原问题：LLM 不可达时 `except RuntimeError: pass` 静默吞错误。
修复方向已从"改方法内部"升级为"删整个方法"——事件驱动架构下不再需要
phase-based message generation，LLM 失败统一走 RuntimeError 传播。
"""

import pytest

from hagoku.config import HaGoKuConfig
from hagoku.manager.orchestrator import Orchestrator


def test_f055_methods_no_longer_exist():
    """F-055：_generate_phase_message 和 _try_generate_phase_llm 已被删除。
    事件驱动架构下不再需要这些方法，LLM 失败由各 handler 独立处理。
    """
    orch = Orchestrator(HaGoKuConfig())
    assert not hasattr(orch, "_generate_phase_message"), (
        "_generate_phase_message 应已随旧 phase 分支删除"
    )
    assert not hasattr(orch, "_try_generate_phase_llm"), (
        "_try_generate_phase_llm 应已随旧 phase 分支删除"
    )
