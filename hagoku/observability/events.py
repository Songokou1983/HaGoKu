"""HaGoKu 事件类型定义"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class EventType(Enum):
    """事件类型"""

    # Manager 事件
    PLAN_CREATED = "plan_created"
    TASK_ASSIGNED = "task_assigned"
    QUALITY_CHECK = "quality_check"
    MODE_SWITCHED = "mode_switched"
    PLAN_ADJUSTED = "plan_adjusted"

    # Agent 事件
    AGENT_STARTED = "agent_started"
    AGENT_THINKING = "agent_thinking"
    AGENT_COMPLETED = "agent_completed"
    AGENT_FAILED = "agent_failed"

    # Tool 事件
    TOOL_CALLED = "tool_called"
    TOOL_RESULT = "tool_result"
    TOOL_ERROR = "tool_error"

    # Data 事件
    DATA_PASSED = "data_passed"
    DATA_ARTIFACT_CREATED = "data_artifact_created"

    # User 事件
    USER_INPUT_REQUESTED = "user_input_requested"
    USER_INPUT_RECEIVED = "user_input_received"

    # Run 事件
    RUN_STARTED = "run_started"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"


@dataclass
class Event:
    """事件"""

    event_id: str
    event_type: EventType
    timestamp: datetime
    agent: str
    data: dict[str, Any] = field(default_factory=dict)
    parent_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典"""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "agent": self.agent,
            "data": self.data,
            "parent_id": self.parent_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Event":
        """从字典反序列化"""
        return cls(
            event_id=data["event_id"],
            event_type=EventType(data["event_type"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            agent=data["agent"],
            data=data.get("data", {}),
            parent_id=data.get("parent_id"),
        )
