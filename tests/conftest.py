"""测试 conftest — 防止 agent 持久化记忆污染生产

3 个 Agent (Scout/Cleaner/Analyst) 有 _save_memory()，默认写源码树里的
memory.md。测试运行这些 agent 时如果不隔离，会污染
hagoku/agents/{scout,cleaner,analyst}/memory.md。

本 conftest 用 autouse fixture 把 _save_memory 替换为 no-op。
测试如果需要验证 memory 保存行为，应显式 opt-in：
  - 在该测试里 unmock：monkeypatch.undo() 不可逆（autouse 已生效）
  - 更好：直接调用 agent._save_memory() 不会写文件（已 no-op），
    或用 tmp_path fixture 传 memory_path（需 Scout 接受此参数）
"""

from __future__ import annotations

import pytest

from hagoku.agents.scout.agent import ScoutAgent
from hagoku.agents.analyst.agent import AnalystAgent
from hagoku.agents.cleaner.agent import CleanerAgent


@pytest.fixture(autouse=True)
def _isolate_agent_persistent_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    """所有测试自动隔离 agent 持久化记忆。

    把 _save_memory 替换为 no-op。
    _load_memory 保持原行为（仍可读 memory.md 内容，仅不写）。
    """
    for cls in (ScoutAgent, AnalystAgent, CleanerAgent):
        monkeypatch.setattr(cls, "_save_memory", lambda self: None)
