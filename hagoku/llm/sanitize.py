"""LLM 输出清洗 — 用户可见文本过滤。"""
from __future__ import annotations

import json as _json
import re
from typing import Any

_THINK_PATTERNS = (
    re.compile(r"<\s*think\s*>.*?<\s*/\s*think\s*>", re.DOTALL | re.IGNORECASE),
    re.compile(r"<\s*reasoning\s*>.*?<\s*/\s*reasoning\s*>", re.DOTALL | re.IGNORECASE),
    re.compile(r"<\s*thinking\s*>.*?<\s*/\s*thinking\s*>", re.DOTALL | re.IGNORECASE),
)

# DSML 标签（独立管理，不混入 THINK_PATTERNS——function calls 需要提取而非删除）
_DSML_TOOL_CALLS = re.compile(
    r"<\s*[|｜]?\s*tool[ _]calls?\s*[|｜]?\s*>(.*?)<\s*/\s*[|｜]?\s*tool[ _]calls?\s*[|｜]?\s*>",
    re.DOTALL | re.IGNORECASE,
)
_DSML_TOOL_RESULTS = re.compile(
    r"<\s*[|｜]?\s*tool[ _]results?\s*[|｜]?\s*>(.*?)<\s*/\s*[|｜]?\s*tool[ _]results?\s*[|｜]?\s*>",
    re.DOTALL | re.IGNORECASE,
)
_DSML_BLOCK = re.compile(
    r"<\s*[|｜]?\s*DSML\s*[|｜]?\s*>.*?<\s*/\s*[|｜]?\s*DSML\s*[|｜]?\s*>",
    re.DOTALL | re.IGNORECASE,
)
_DSML_TAG = re.compile(r"<\s*/?\s*[|｜]?\s*DSML\s*[|｜]?\s*>", re.IGNORECASE)

# 检测未闭合的 think 标签（流式中间态）
_OPEN_THINK = re.compile(r"<\s*(think|reasoning|thinking)\s*>", re.IGNORECASE)
_CLOSE_THINK = re.compile(r"<\s*/\s*(think|reasoning|thinking)\s*>", re.IGNORECASE)


def _strip_dsml(text: str) -> str:
    """移除 DSML 标签（非 function-call 部分），保留纯净文本。"""
    out = _DSML_TOOL_RESULTS.sub("", text)
    out = _DSML_BLOCK.sub("", out)
    out = _DSML_TAG.sub("", out)
    return out


def extract_dsml_tool_calls(text: str) -> list[dict[str, Any]]:
    """从 DSML <|tool_calls|> 中提取 OpenAI 格式的 tool_calls。"""
    result: list[dict[str, Any]] = []
    for match in _DSML_TOOL_CALLS.finditer(text):
        body = match.group(1).strip()
        if not body:
            continue
        try:
            parsed = _json.loads(body)
        except _json.JSONDecodeError:
            continue
        if isinstance(parsed, list):
            for i, tc in enumerate(parsed):
                if isinstance(tc, dict):
                    fn = tc.get("function", tc)
                    name = fn.get("name", "")
                    arguments = fn.get("arguments", {})
                    if isinstance(arguments, dict):
                        arguments = _json.dumps(arguments, ensure_ascii=False)
                    result.append({
                        "id": f"dsml_{len(result)}",
                        "type": "function",
                        "function": {"name": name, "arguments": str(arguments)},
                    })
        elif isinstance(parsed, dict):
            name = parsed.get("name", "")
            arguments = parsed.get("arguments", {})
            if isinstance(arguments, dict):
                arguments = _json.dumps(arguments, ensure_ascii=False)
            result.append({
                "id": f"dsml_{len(result)}",
                "type": "function",
                "function": {"name": name, "arguments": str(arguments)},
            })
    return result


def strip_llm_think(text: str) -> str:
    """移除模型 CoT / think 块 + DSML 标签，防止泄露到 UI。"""
    out = text or ""
    for pat in _THINK_PATTERNS:
        out = pat.sub("", out)
    out = _strip_dsml(out)
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
    若 accumulated 超过 500 字符仍未闭合，强制 emit（防止截断）。
    """
    combined = (full_text or "") + (chunk or "")
    if _has_unclosed_think(combined) and len(combined) < 2000:
        return combined, "", emitted_len
    safe = strip_llm_think(combined)
    if len(safe) <= emitted_len:
        return combined, "", emitted_len
    delta = safe[emitted_len:]
    return combined, delta, len(safe)
