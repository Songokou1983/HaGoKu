"""通道日志系统 — 记录决策链 + LLM 输入输出"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ChannelLogger:
    """每个 run 一个实例。放在 run 目录下，清除历史时随 run 目录一起删除。"""

    _FIELD_EVENT_MAP: dict[str, str] = {
        "used_in_analysis": "uia",
        "suggested_role": "role",
    }

    def __init__(self, run_dir: Path) -> None:
        if run_dir.exists() and not run_dir.is_dir():
            raise NotADirectoryError(
                f"{run_dir} exists but is not a directory"
            )
        run_dir.mkdir(parents=True, exist_ok=True)
        self._run_log = run_dir / "run.log"

    # ── 通道事件 ──

    def log(self, agent: str, event: str, **kwargs: Any) -> None:
        """写一行 JSON 到 run.log"""
        record = {"ts": self._now(), "agent": agent, "event": event, **kwargs}
        self._append_json(self._run_log, record)

    # ── 决策链 ──

    def trace_value(
        self, agent: str, column: str, field: str, value: Any, source: str
    ) -> None:
        """记录一个字段值的来源"""
        mapped = self._FIELD_EVENT_MAP.get(field, field)
        event = (
            f"{mapped}_set"
            if not mapped.startswith("_")
            else mapped.lstrip("_")
        )
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
    def _append_json(path: Path, record: dict) -> None:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
