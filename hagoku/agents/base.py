"""HaGoKu Studio Agent 基类"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from ..config import LLMConfig
from ..observability.event_bus import EventBus
from ..observability.events import Event, EventType


class DataAgentBase:
    """
    HaGoKu Studio 的 Agent 基类

    不直接继承 CrewAI Agent，而是提供统一的事件发射、LLM 调用接口。
    CrewAI Agent 在需要时按需创建。
    """

    def __init__(
        self,
        role: str,
        goal: str,
        backstory: str,
        llm_config: LLMConfig,
        event_bus: EventBus,
        *,
        tools: list[Any] | None = None,
        llm_client: Any | None = None,
    ) -> None:
        self.role = role
        self.goal = goal
        self.backstory = backstory
        self.llm_config = llm_config
        self.event_bus = event_bus
        self.tools = tools or []
        self._start_time: datetime | None = None
        self._crewai_agent: Any | None = None
        self._llm_client = llm_client  # 外部传入的 LLM 客户端（双层策略用）

    def emit_event(self, event_type: EventType, data: dict[str, Any] | None = None) -> Event:
        """发射事件"""
        return self.event_bus.emit(
            event_type=event_type,
            agent=self.role,
            data=data or {},
        )

    def start(self) -> None:
        """标记 agent 开始工作"""
        self._start_time = datetime.now()
        self.emit_event(EventType.AGENT_STARTED, {"goal": self.goal})

    def complete(self, result: dict[str, Any] | None = None) -> None:
        """标记 agent 完成工作"""
        duration = ""
        if self._start_time:
            elapsed = datetime.now() - self._start_time
            duration = f"{elapsed.total_seconds():.1f}s"
        self.emit_event(EventType.AGENT_COMPLETED, {
            "duration": duration,
            "result_summary": str(result)[:200] if result else "",
        })

    def fail(self, error: str) -> None:
        """标记 agent 失败"""
        self.emit_event(EventType.AGENT_FAILED, {"error": error})

    def emit_thinking(self, thought: str) -> None:
        """发射思考过程（verbose 模式用）"""
        self.emit_event(EventType.AGENT_THINKING, {"thought": thought})

    def emit_tool_call(self, tool_name: str, args_summary: str = "") -> Event:
        """发射工具调用事件"""
        return self.emit_event(EventType.TOOL_CALLED, {
            "tool": tool_name,
            "args_summary": args_summary,
        })

    def emit_tool_result(self, summary: str) -> Event:
        """发射工具结果事件"""
        return self.emit_event(EventType.TOOL_RESULT, {"summary": summary})

    def emit_tool_error(self, error: str) -> Event:
        """发射工具错误事件"""
        return self.emit_event(EventType.TOOL_ERROR, {"error": error})

    def create_llm_client(self) -> Any:
        """
        创建 LLM 客户端（OpenAI 兼容 API）

        使用 instructor 包装以获得结构化输出
        """
        from ..llm.client import create_structured_llm_client

        return create_structured_llm_client(self.llm_config)

    def get_crewai_agent(self) -> Any:
        """
        获取 CrewAI Agent（延迟创建）

        需要 crewai 和 langchain_openai 安装
        """
        if self._crewai_agent is not None:
            return self._crewai_agent

        try:
            from crewai import Agent
            from langchain_openai import ChatOpenAI

            llm = ChatOpenAI(
                base_url=self.llm_config.base_url,
                model=self.llm_config.model,
                api_key=self.llm_config.api_key,
                temperature=self.llm_config.temperature,
            )

            self._crewai_agent = Agent(
                role=self.role,
                goal=self.goal,
                backstory=self.backstory,
                tools=self.tools,
                llm=llm,
                verbose=False,
            )
            return self._crewai_agent
        except ImportError as e:
            raise ImportError(
                f"CrewAI Agent 需要 crewai 和 langchain_openai: {e}\n"
                "pip install crewai langchain-openai"
            ) from e

    async def ask_llm(self, prompt: str, system: str = "") -> str:
        """
        直接调用 LLM（不通过 CrewAI）

        Args:
            prompt: 用户提示
            system: 系统提示

        Returns:
            LLM 回复文本
        """
        # 优先使用外部传入的客户端，否则创建新的
        client = self._llm_client if self._llm_client else self.create_llm_client()

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        # instructor 包装的客户端和原始 OpenAI 客户端调用方式一致
        try:
            response = client.chat.completions.create(
                model=self.llm_config.model,
                messages=messages,
                temperature=self.llm_config.temperature,
                max_tokens=self.llm_config.max_tokens,
            )
            return response.choices[0].message.content or ""
        except TypeError:
            # instructor 客户端可能需要 response_model=None
            response = client.chat.completions.create(
                model=self.llm_config.model,
                messages=messages,
                temperature=self.llm_config.temperature,
                max_tokens=self.llm_config.max_tokens,
                response_model=None,
            )
            return response.choices[0].message.content or ""

    def call_llm(self, prompt: str, system: str = "") -> str:
        """
        同步调用 LLM（内部封装 asyncio.run）
        """
        try:
            return asyncio.run(self.ask_llm(prompt, system))
        except Exception as e:
            self.emit_thinking(f"[LLM 调用失败] {e}")
            return ""

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(role={self.role!r})"
