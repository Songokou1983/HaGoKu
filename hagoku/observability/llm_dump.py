"""LLM messages 诊断 dump — 由 HAGOKU_DUMP_LLM=1 环境变量控制。

落盘所有 LLM 调用的完整 messages，用于诊断通道污染与衔接断点。
失败不影响主流程。
"""
from __future__ import annotations

import json as _json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_log = logging.getLogger("hagoku.llm_dump")

DUMP_DIR = Path.home() / ".hagoku" / "llm_dumps"


def _is_enabled() -> bool:
    return os.environ.get("HAGOKU_DUMP_LLM", "").strip() == "1"


def dump_messages(
    stage: str,
    messages: list[dict[str, Any]],
    model: str,
    *,
    run_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """落盘 LLM 调用的完整 messages。

    Args:
        stage: 阶段标识，如 "scout_infer_all_semantics"
        messages: LLM 调用的完整 messages 列表
        model: 模型名称
        run_id: 当前 run_id，用于目录组织
        extra: 额外上下文（query / via_project_ctx / tools 等）
    """
    if not _is_enabled():
        return

    try:
        seq_file = DUMP_DIR / ".seq"
        DUMP_DIR.mkdir(parents=True, exist_ok=True)

        # 读取/递增序号
        seq = 1
        if seq_file.exists():
            seq = int(seq_file.read_text().strip()) + 1
        seq_file.write_text(str(seq))

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        seq_str = f"{seq:03d}"
        filename = f"{seq_str}_{stage}_{ts}.json"

        if run_id:
            out_dir = DUMP_DIR / run_id
        else:
            out_dir = DUMP_DIR
        out_dir.mkdir(parents=True, exist_ok=True)

        payload: dict[str, Any] = {
            "seq": seq,
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
