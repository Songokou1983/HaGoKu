"""LLM messages 诊断 dump — 默认开启（HAGOKU_DUMP_LLM=0 可关闭）。

每个 run 一份 dump 写入 run_dir/llm_dumps/，与 events.jsonl 同目录。
用于诊断通道污染与衔接断点。失败不影响主流程。

契约变更（2026-06-07 CH-4）：
- HAGOKU_DUMP_LLM 语义反转：原 "=1" 才写 → 现默认写，"=0" 才关闭
- 路径：~/.hagoku/llm_dumps/ → run_dir/llm_dumps/（与 events.jsonl 同目录）
"""
from __future__ import annotations

import json as _json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_log = logging.getLogger("hagoku.llm_dump")

# 历史遗留（仅作 get_dump_dir() fallback），新路径由 set_run_dir 设置
_DEFAULT_DUMP_DIR: Path | None = None  # lazy from config
_run_dump_dir: Path | None = None
_run_dump_seq: int = 0  # per-run 递增序号


def _get_default_dump_dir() -> Path:
    global _DEFAULT_DUMP_DIR
    if _DEFAULT_DUMP_DIR is None:
        from hagoku.config import HaGoKuConfig
        _DEFAULT_DUMP_DIR = HaGoKuConfig.load().work_dir / "llm_dumps"
    return _DEFAULT_DUMP_DIR


def set_run_dir(run_dir: Path) -> None:
    """由 Orchestrator 在 pipeline 启动时调用，设置当前 run 的 dump 目录。"""
    global _run_dump_dir, _run_dump_seq
    _run_dump_dir = run_dir / "llm_dumps"
    _run_dump_seq = 0


def reset_run_dir() -> None:
    """测试 teardown：清空 _run_dump_dir，防止测试 dump 污染生产 run 目录。"""
    global _run_dump_dir, _run_dump_seq
    _run_dump_dir = None
    _run_dump_seq = 0


def _is_enabled() -> bool:
    v = os.environ.get("HAGOKU_DUMP_LLM", "").strip()
    return v != "0"  # 默认开，仅显式设 0 才关


def get_dump_dir() -> Path:
    """返回当前 dump 输出目录。"""
    return _run_dump_dir or _get_default_dump_dir()


def dump_messages(
    stage: str,
    messages: list[dict[str, Any]],
    model: str,
    *,
    run_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """落盘 LLM 调用的完整 messages + 可选 response（extra）。

    Args:
        stage: 阶段标识，如 "scout_infer_all_semantics"
        messages: LLM 调用的完整 messages 列表
        model: 模型名称
        run_id: 当前 run_id，用于目录组织（_run_dump_dir 优先）
        extra: 额外上下文（query / tools / response_tool_calls / response_content 等）
    """
    if not _is_enabled():
        return

    try:
        global _run_dump_seq
        out_dir = _run_dump_dir or _get_default_dump_dir()
        out_dir.mkdir(parents=True, exist_ok=True)

        _run_dump_seq += 1
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S%f")[:17]
        filename = f"{_run_dump_seq:03d}_{stage}_{ts}.json"

        payload: dict[str, Any] = {
            "seq": _run_dump_seq,
            "stage": stage,
            "model": model,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": run_id,
            "messages": _serialize_messages(messages),
        }
        if extra:
            payload["extra"] = extra

        (out_dir / filename).write_text(
            _json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    except Exception:
        _log.warning("LLM dump 写入失败", exc_info=True)


def _serialize_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """序列化 messages，截断过长内容防止 dump 文件过大。"""
    out: list[dict[str, Any]] = []
    for m in messages:
        role = m.get("role", "unknown")
        content = m.get("content", "")
        if isinstance(content, str) and len(content) > 8000:
            content = content[:8000] + f"\n…[truncated, total {len(content)} chars]"
        entry: dict[str, Any] = {"role": role, "content": content}
        if "name" in m:
            entry["name"] = m["name"]
        if "tool_calls" in m:
            entry["tool_calls"] = m["tool_calls"]
        if "tool_call_id" in m:
            entry["tool_call_id"] = m["tool_call_id"]
        out.append(entry)
    return out
