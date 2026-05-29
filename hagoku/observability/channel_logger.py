"""通道日志系统 — 记录决策链 + LLM 输入输出"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ChannelLogger:
    """每个 run 一个实例。放在 run 目录下，清除历史时随 run 目录一起删除。"""

    def __init__(self, run_dir: Path) -> None:
        run_dir.mkdir(parents=True, exist_ok=True)
        self._run_log = run_dir / "run.log"
        self._llm_log = run_dir / "llm.log"

    # ── 通道事件 ──

    def log(self, agent: str, event: str, **kwargs: Any) -> None:
        """写一行 JSON 到 run.log"""
        record = {"ts": self._now(), "agent": agent, "event": event, **kwargs}
        with open(self._run_log, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    # ── LLM 调用录制 ──

    def log_llm(
        self,
        agent: str,
        model: str,
        system_prompt: str,
        user_prompt: str,
        response_tool_calls: list[dict] | None = None,
        response_content: str = "",
        tokens: int = 0,
        duration_ms: int = 0,
    ) -> None:
        """写一条 LLM 完整记录到 llm.log"""
        record = {
            "ts": self._now(),
            "agent": agent,
            "model": model,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "response_tool_calls": response_tool_calls or [],
            "response_content": response_content,
            "tokens": tokens,
            "duration_ms": duration_ms,
        }
        with open(self._llm_log, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, default=str)

    # ── 决策链 ──

    def trace_value(
        self, agent: str, column: str, field: str, value: Any, source: str
    ) -> None:
        """记录一个字段值的来源"""
        event = f"{field}_set" if not field.startswith("_") else field.lstrip("_")
        self.log(agent, event, column=column, value=value, source=source)

    # ── 通道健康摘要 ──

    def summary(
        self, query_arrived: bool, uia_breakdown: str, warnings: list[str]
    ) -> None:
        """写通道健康摘要"""
        self.log(
            "orchestrator",
            "channel_summary",
            query_arrived=query_arrived,
            uia_breakdown=uia_breakdown,
            warnings=warnings,
        )

    # ── 内部 ──

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
