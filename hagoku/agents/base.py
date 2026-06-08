"""BaseAgent — Agent 共享基类。

抽取 4 个 Agent（Scout/Cleaner/Analyst/Reporter）的共同代码：
- _load_prompt / _emit / _load_memory / _save_memory
- __init__ 共同字段
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml

from ._interactive import InteractionMixin
from ..observability.events import EventType

logger = logging.getLogger(__name__)


class BaseAgent(InteractionMixin):
    """Agent 共同基类。"""

    role: str = ""
    _memory_yaml_key: str = "fields"  # 子类覆盖：YAML 块中的顶层 key

    def __init__(
        self,
        llm_config: Any = None,
        event_bus: Any = None,
        orchestrator: Any = None,
        llm_client: Any = None,
        **kwargs: Any,
    ) -> None:
        self.llm_config = llm_config
        self.event_bus = event_bus
        self.orchestrator = orchestrator
        self._llm_client = llm_client
        self._channel_logger = kwargs.get("channel_logger")

        self.prompt = self._load_prompt()
        self.memory = self._load_memory()
        self._phase = "begin"

    def _load_prompt(self) -> str:
        path = Path(__file__).parent / self.role / "prompt.md"
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    def _emit(self, event_type: EventType, data: dict | None = None) -> None:
        if self.event_bus:
            self.event_bus.emit(event_type=event_type, agent=self.role, data=data or {})

    def _load_memory(self) -> dict:
        path = Path(__file__).parent / self.role / "memory.md"
        if path.exists():
            content = path.read_text(encoding="utf-8")
            match = re.search(
                rf"```yaml\n({self._memory_yaml_key}.*?)```", content, re.DOTALL
            )
            if match:
                try:
                    return yaml.safe_load(match.group(1)) or {}
                except yaml.YAMLError:
                    return {}
        return {self._memory_yaml_key: {}}

    def _save_memory(self) -> None:
        """子类覆盖以实现各自的序列化格式。基类提供空实现。"""
        pass
