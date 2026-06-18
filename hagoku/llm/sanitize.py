"""LLM 输出清洗 — 用户可见文本过滤。"""
from __future__ import annotations

import re

_THINK_PATTERNS = (
    re.compile(r"<\s*think\s*>.*?<\s*/\s*think\s*>", re.DOTALL | re.IGNORECASE),
    re.compile(r"<\s*reasoning\s*>.*?<\s*/\s*reasoning\s*>", re.DOTALL | re.IGNORECASE),
    re.compile(r"<\s*thinking\s*>.*?<\s*/\s*thinking\s*>", re.DOTALL | re.IGNORECASE),
    # DeepSeek DSML function-call 标签（<|tool_calls|> / <|DSML|> / <|tool_results|>）
    re.compile(r"<\s*\|?\s*tool[ _]calls?\s*\|?\s*>.*?<\s*/\s*\|?\s*tool[ _]calls?\s*\|?\s*>", re.DOTALL | re.IGNORECASE),
    re.compile(r"<\s*\|?\s*tool[ _]results?\s*\|?\s*>.*?<\s*/\s*\|?\s*tool[ _]results?\s*\|?\s*>", re.DOTALL | re.IGNORECASE),
    re.compile(r"<\s*\|?\s*DSML\s*\|?\s*>.*?<\s*/\s*\|?\s*DSML\s*\|?\s*>", re.DOTALL | re.IGNORECASE),
    # 未闭合的孤立 DSML 开/闭标签（流式中间态残留）
    re.compile(r"<\s*\|?\s*DSML\s*\|?\s*>", re.IGNORECASE),
    re.compile(r"<\s*/\s*\|?\s*DSML\s*\|?\s*>", re.IGNORECASE),
)

# 检测未闭合的 think 标签（流式中间态）
_OPEN_THINK = re.compile(r"<\s*(think|reasoning|thinking)\s*>", re.IGNORECASE)
_CLOSE_THINK = re.compile(r"<\s*/\s*(think|reasoning|thinking)\s*>", re.IGNORECASE)


def strip_llm_think(text: str) -> str:
    """移除模型 CoT / think 块，防止泄露到 UI。"""
    out = text or ""
    for pat in _THINK_PATTERNS:
        out = pat.sub("", out)
    return out.strip()


def _has_unclosed_think(text: str) -> bool:
    """检查是否有已打开但未关闭的 think 标签。"""
    opens = len(_OPEN_THINK.findall(text))
    closes = len(_CLOSE_THINK.findall(text))
    return opens > closes


def stream_safe_append(
    full_text: str,
    chunk: str,
    emitted_len: int,
) -> tuple[str, str, int]:
    """流式增量：只 emit 已剥离 think 后的新增安全文本。
    
    如果存在未闭合的 think 标签，暂不 emit，等闭合后再出。
    """
    combined = (full_text or "") + (chunk or "")
    if _has_unclosed_think(combined):
        return combined, "", emitted_len
    safe = strip_llm_think(combined)
    if len(safe) <= emitted_len:
        return combined, "", emitted_len
    delta = safe[emitted_len:]
    return combined, delta, len(safe)
