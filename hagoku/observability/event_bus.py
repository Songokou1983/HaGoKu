"""HaGoKu Studio 事件总线"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Callable
from uuid import uuid4

from .events import Event, EventType

logger = logging.getLogger(__name__)


class EventBus:
    """全局事件总线，所有 agent 和工具的事件都经过这里"""

    def __init__(self) -> None:
        self.events: list[Event] = []
        self.subscribers: list[Callable[[Event], None]] = []

    def emit(self, event_type: EventType, agent: str, data: dict | None = None, parent_id: str | None = None) -> Event:
        """发射事件并通知所有订阅者"""
        event = Event(
            event_id=uuid4().hex[:8],
            event_type=event_type,
            timestamp=datetime.now(),
            agent=agent,
            data=data or {},
            parent_id=parent_id,
        )
        self.events.append(event)
        for callback in self.subscribers:
            try:
                callback(event)
            except Exception as e:
                logger.warning(f"EventBus subscriber {callback.__name__} failed: {e}")
        return event

    def subscribe(self, callback: Callable[[Event], None]) -> None:
        """订阅事件（同一 callback 只注册一次，避免 WS 桥接等重复订阅）"""
        if callback in self.subscribers:
            return
        self.subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[Event], None]) -> None:
        """取消订阅"""
        self.subscribers.remove(callback)

    def get_timeline(self) -> list[Event]:
        """获取完整时间线（按时间排序）"""
        return sorted(self.events, key=lambda e: e.timestamp)

    def get_agent_trace(self, agent: str) -> list[Event]:
        """获取某个 agent 的完整事件链"""
        return [e for e in self.events if e.agent == agent]

    def get_tool_trace(self, agent: str) -> list[Event]:
        """获取某个 agent 的工具调用链"""
        tool_types = {EventType.TOOL_CALLED, EventType.TOOL_RESULT, EventType.TOOL_ERROR}
        return [e for e in self.events if e.agent == agent and e.event_type in tool_types]

    def get_events_by_type(self, event_type: EventType) -> list[Event]:
        """按类型筛选事件"""
        return [e for e in self.events if e.event_type == event_type]

    def save_to_file(self, path: Path) -> None:
        """保存事件日志到文件（JSONL 格式）"""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            for event in self.events:
                f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")

    @classmethod
    def load_from_file(cls, path: Path) -> "EventBus":
        """从文件加载事件日志（用于 replay）"""
        bus = cls()
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    event = Event.from_dict(json.loads(line))
                    bus.events.append(event)
        return bus

    def clear(self) -> None:
        """清空事件"""
        self.events.clear()
