"""LLM 输出清洗 — 用户可见文本过滤。"""
from __future__ import annotations

import re

# 用拼接避免部分编辑器/管道吞掉 XML 形标签
_THINK_ALT_OPEN = chr(60) + "think" + chr(62)
_THINK_ALT_CLOSE = chr(60) + "/" + "think" + chr(62)

_THINK_PATTERNS = (
    re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE),
    re.compile(
        re.escape(_THINK_ALT_OPEN) + r".*?" + re.escape(_THINK_ALT_CLOSE),
        re.DOTALL | re.IGNORECASE,
    ),
)


def strip_llm_think(text: str) -> str:
    """移除模型 CoT / think 块，防止泄露到 UI。"""
    out = text or ""
    for pat in _THINK_PATTERNS:
        out = pat.sub("", out)
    return out.strip()


def stream_safe_append(
    full_text: str,
    chunk: str,
    emitted_len: int,
) -> tuple[str, str, int]:
    """流式增量：只 emit 已剥离 think 后的新增安全文本。"""
    combined = (full_text or "") + (chunk or "")
    safe = strip_llm_think(combined)
    if len(safe) <= emitted_len:
        return combined, "", emitted_len
    delta = safe[emitted_len:]
    return combined, delta, len(safe)
