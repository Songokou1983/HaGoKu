"""F-055 验证：_generate_phase_message 在 LLM 不可达时必须 raise RuntimeError，
不得 silently pass（违反铁律 2 路径 A）。
"""

import pytest
from unittest.mock import patch

from hagoku.config import HaGoKuConfig
from hagoku.manager.orchestrator import Orchestrator


def test_f055_phase_message_raises_on_llm_unreachable_tier1():
    """F-055 红灯：第一层 LLM 不可达时，RuntimeError 必须传播，不能 pass 吞掉。

    当前代码在 orch.py:2695-2696 有 `except RuntimeError: pass`，
    此测试验证修复后 RuntimeError 正确传播。
    """
    orch = Orchestrator(HaGoKuConfig())

    with patch.object(
        orch, "_try_generate_phase_llm",
        side_effect=RuntimeError("LLM不可达（retry=False）。原始错误: ConnectionError"),
    ):
        with pytest.raises(RuntimeError, match="LLM不可达"):
            orch._generate_phase_message(
                phase="analyst_preliminary",
                findings=[{"question": "测试", "p_value": 0.05, "significance": "significant"}],
                power_warnings=[],
                suggested_focus="测试方向",
            )
