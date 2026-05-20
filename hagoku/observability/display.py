"""HaGoKu Studio 终端实时显示"""

from __future__ import annotations

from .events import Event, EventType

# Agent 显示名和颜色
AGENT_DISPLAY = {
    "Manager":  ("🧠", "\033[35m"),  # 紫
    "Scout":    ("🔍", "\033[36m"),  # 青
    "Cleaner":  ("🧹", "\033[33m"),  # 黄
    "Analyst":  ("📊", "\033[34m"),  # 蓝
    "Reporter": ("📝", "\033[32m"),  # 绿
}

STATUS_ICONS = {
    "completed": "✅",
    "running": "🔄",
    "pending": "⏳",
    "failed": "❌",
    "warning": "⚠️",
}

RESET = "\033[0m"
DIM = "\033[90m"
BOLD = "\033[1m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"


class TerminalDisplay:
    """订阅 EventBus，实时打印到终端"""

    def __init__(self, verbosity: str = "normal") -> None:
        """
        Args:
            verbosity: quiet / normal / verbose
        """
        self.verbosity = verbosity
        self._agent_status: dict[str, str] = {}

    def __call__(self, event: Event) -> None:
        """EventBus 回调"""
        if self.verbosity == "quiet":
            self._handle_quiet(event)
        elif self.verbosity == "verbose":
            self._handle_verbose(event)
        else:
            self._handle_normal(event)

    def _get_agent_prefix(self, agent: str) -> str:
        """获取 agent 的 emoji 和颜色"""
        icon, color = AGENT_DISPLAY.get(agent, ("●", ""))
        return f"{color}{icon} {agent}{RESET}"

    def _handle_quiet(self, event: Event) -> None:
        """静默模式：只打印完成和失败"""
        if event.event_type == EventType.AGENT_COMPLETED:
            print(f"  ✅ {event.agent} 完成")
        elif event.event_type == EventType.AGENT_FAILED:
            print(f"  ❌ {event.agent} 失败: {event.data.get('error', '')}")
        elif event.event_type == EventType.RUN_COMPLETED:
            print("\n🎉 分析完成！")
            if path := event.data.get("output_path"):
                print(f"📄 报告: {path}")

    def _handle_normal(self, event: Event) -> None:
        """标准模式：打印关键事件"""
        prefix = self._get_agent_prefix(event.agent)

        if event.event_type == EventType.AGENT_STARTED:
            print(f"\n{prefix}: 开始工作...")

        elif event.event_type == EventType.AGENT_COMPLETED:
            duration = event.data.get("duration", "")
            dur_str = f" ({duration})" if duration else ""
            print(f"{prefix}: ✅ 完成{dur_str}")

        elif event.event_type == EventType.AGENT_FAILED:
            error = event.data.get("error", "未知错误")
            print(f"{prefix}: ❌ 失败 - {error}")

        elif event.event_type == EventType.TOOL_CALLED:
            tool_name = event.data.get("tool", "")
            args = event.data.get("args_summary", "")
            args_str = f"({args})" if args else ""
            print(f"   │  🔧 {tool_name}{args_str}")

        elif event.event_type == EventType.TOOL_RESULT:
            result = event.data.get("summary", "")
            if result:
                print(f"   │     → {result}")

        elif event.event_type == EventType.TOOL_ERROR:
            error = event.data.get("error", "")
            print(f"   │     ❌ {error}")

        elif event.event_type == EventType.QUALITY_CHECK:
            verdict = event.data.get("verdict", "")
            icon = "✅" if verdict == "pass" else "⚠️"
            detail = event.data.get("detail", "")
            print(f"   🧠 Manager: {icon} {detail}")

        elif event.event_type == EventType.USER_INPUT_REQUESTED:
            question = event.data.get("question", "")
            print(f"\n   👤 {question}")

        elif event.event_type == EventType.RUN_COMPLETED:
            output = event.data.get("output_path", "")
            duration = event.data.get("duration", "")
            tokens = event.data.get("token_count", "")
            print(f"\n🎉 分析完成！总耗时: {duration} | Token: {tokens}")
            if output:
                print(f"📄 报告: {output}")

    def _handle_verbose(self, event: Event) -> None:
        """详细模式：打印所有事件，包括 AI 思考过程"""
        if event.event_type == EventType.AGENT_THINKING:
            thought = event.data.get("thought", "")
            print(f"   │  💭 {thought}")
        else:
            # 先走标准逻辑
            self._handle_normal(event)
