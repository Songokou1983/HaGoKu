"""LLM 客户端工厂

提供共享的 LLM 客户端创建函数，供 Orchestrator 和 Agent 基类共同使用。
使用 instructor 包装 OpenAI 兼容客户端以获得结构化输出能力。

CH-7e（2026-06-07）：_clear_proxy_env 全局 os.environ.pop 替换为 per-client
httpx transport。每个客户端持有独立的 HTTPTransport，禁用代理以避免 socks://
等不被 httpx 支持的 scheme 抛出 ValueError。不再污染进程级环境变量。
"""

from __future__ import annotations

import logging
import os
from typing import Any, Generator

import httpx

from ..config import LLMConfig

logger = logging.getLogger("hagoku.llm")


def _create_http_client() -> httpx.Client:
    """创建不读代理环境变量的 httpx 客户端（per-client transport）。

    替换旧 _clear_proxy_env 的全局 os.environ.pop 方案——
    旧方案永久污染进程环境，影响同进程内其他网络调用。
    """
    return httpx.Client(
        transport=httpx.HTTPTransport(retries=1),
    )


def create_meta_client(config: Any) -> Any:
    """HaGoKu Doctor 独立 LLM 客户端。未配置时回退到 pipeline。"""
    from ..config import HaGoKuConfig

    if isinstance(config, HaGoKuConfig) and config.meta_llm.base_url and config.meta_llm.model:
        cfg = LLMConfig(
            model=config.meta_llm.model,
            base_url=config.meta_llm.base_url,
            api_key=config.meta_llm.api_key,
            temperature=0.0,
            max_tokens=8192,
        )
    else:
        cfg = _unwrap_llm(config)
    return create_structured_llm_client(cfg)


def create_structured_llm_client(llm_config: LLMConfig) -> Any:
    """
    创建 instructor 包装的 OpenAI 客户端（结构化输出）

    Args:
        llm_config: LLM 连接配置

    Returns:
        instructor 包装的 OpenAI 客户端，兼容所有支持 function calling 的模型

    Raises:
        ImportError: 如果 openai 未安装
    """
    try:
        import instructor
        from openai import OpenAI

        client = instructor.from_openai(
            OpenAI(
                base_url=llm_config.base_url,
                api_key=llm_config.api_key,
                timeout=120.0,
                http_client=_create_http_client(),
            ),
            mode=instructor.Mode.TOOLS,
        )
        return client
    except ImportError:
        # 退回原始 OpenAI（无结构化输出）
        from openai import OpenAI

        return OpenAI(
            base_url=llm_config.base_url,
            api_key=llm_config.api_key,
            timeout=120.0,
            http_client=_create_http_client(),
        )


def create_raw_client(config: Any) -> Any:
    """
    创建原始 OpenAI 客户端（不做 instructor 包装）

    适用于需要 raw chat.completions.create() 的场景（如 Scout 的 JSON mode）。
    """
    from openai import OpenAI

    llm = _unwrap_llm(config)

    return OpenAI(
        base_url=llm.base_url,
        api_key=llm.api_key,
        timeout=120.0,
        http_client=_create_http_client(),
    )


def _unwrap_llm(config: Any) -> LLMConfig:
    """兼容 HaGoKuConfig（含 .llm 属性）和裸 LLMConfig 两种输入"""
    if isinstance(config, LLMConfig):
        return config
    # 假设是 HaGoKuConfig
    return config.llm



# 全局 AsyncOpenAI 客户端单例（连接复用）
_async_client: Any = None
_async_client_config: tuple[str, str] | None = None  # (base_url, api_key)


def _get_async_client() -> Any:
    """获取或创建全局 AsyncOpenAI 客户端，复用底层 HTTP 连接池。"""
    global _async_client, _async_client_config

    from openai import AsyncOpenAI
    from ..config import HaGoKuConfig

    config = HaGoKuConfig.load()
    llm = config.llm
    cache_key = (llm.base_url, llm.api_key)

    if _async_client is None or _async_client_config != cache_key:
        _async_client = AsyncOpenAI(
            base_url=llm.base_url,
            api_key=llm.api_key,
            timeout=30.0,
            http_client=_create_http_client(),
        )
        _async_client_config = cache_key

    return _async_client


async def chat_completion(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.0,
    max_tokens: int = 256,
) -> dict[str, str]:
    """轻量异步 chat completion，用于意图分类等无状态场景。

    不依赖 instructor，直接调用 OpenAI chat.completions.create。
    复用全局 AsyncOpenAI 客户端以复用底层 HTTP 连接池。

    Returns:
        dict with keys "content" and "role"（兼容 resp.get("content") 访问方式）
    """
    from ..config import HaGoKuConfig

    config = HaGoKuConfig.load()
    llm = config.llm

    client = _get_async_client()
    response = await client.chat.completions.create(
        model=llm.model,
        messages=messages,  # type: ignore[arg-type]
        temperature=temperature,
        max_tokens=max_tokens,
    )

    choice = response.choices[0]
    return {
        "content": choice.message.content or "",
        "role": choice.message.role,
    }


def _dump_debug_context(
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
) -> None:
    """通道诊断：HAGOKU_DUMP_DEBUG_CONTEXT=1 时，dump 完整的 messages + tools。

    绝不做摘要/截断/修改——原样 JSON 写入 run_dir/llm_dumps/debug_context_N.json。
    用于验证上下文保真律：LLM 实际收到的内容是否与 to_messages_for_llm() 输出一致。
    """
    if os.environ.get("HAGOKU_DUMP_DEBUG_CONTEXT", "").strip() != "1":
        return
    import json as _json
    from pathlib import Path as _Path
    try:
        from hagoku.observability.llm_dump import get_dump_dir
        out_dir = get_dump_dir()
    except Exception:
        from hagoku.observability.llm_dump import _get_default_dump_dir
        out_dir = _get_default_dump_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    # 取现有最大序号 + 1
    existing = list(out_dir.glob("debug_context_*.json"))
    seq = len(existing) + 1
    payload = {
        "model": model,
        "messages": messages,
        "tools": tools,
    }
    path = out_dir / f"debug_context_{seq:04d}.json"
    path.write_text(_json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    import logging
    logging.getLogger("hagoku.llm").info("debug_context dumped: %s (%d messages, %d tools)",
                                         path, len(messages), len(tools or []))


def stream_chat_completion(
    client: Any,
    model: str,
    messages: list[dict[str, Any]],
    *,
    temperature: float = 0.0,
    max_tokens: int = 4096,
    tools: list[dict[str, Any]] | None = None,
) -> Generator[dict[str, Any], None, None]:
    """同步流式 chat completion 生成器（CO-18）。

    每次 yield 一个 dict，类型为 "delta" 或 "end" 或 "error"。
    - delta: {"type": "delta", "content": str}  — 逐 token 文本增量
    - tool_call: {"type": "tool_call", "tool_calls": [...]} — 流结束时的完整 tool_calls
    - end: {"type": "end", "content": str, "tool_calls": [...]} — 流结束，完整内容
    - error: {"type": "error", "message": str} — 流式失败（铁律 7：不静默兜底）

    Args:
        client: 已创建的 OpenAI 客户端（同步）
        model: 模型名称
        messages: 消息列表
        temperature: 生成温度
        max_tokens: 最大 token 数
        tools: 可选工具列表
    """
    full_content = ""
    final_tool_calls: list[dict[str, Any]] = []

    # ── 通道诊断：dump 完整 context（HAGOKU_DUMP_DEBUG_CONTEXT=1）──
    _dump_debug_context(model, messages, tools)

    try:
        stream = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice="auto" if tools else None,
            stream=True,
        )
    except Exception as e:
        # 网络瞬时错误重试一次
        import time as _time
        _time.sleep(1)
        try:
            stream = client.chat.completions.create(
                model=model, messages=messages,
                temperature=temperature, max_tokens=max_tokens,
                tools=tools, tool_choice="auto" if tools else None,
                stream=True,
            )
        except Exception:
            raise RuntimeError(f"LLM 流式请求失败（重试后）：{e}") from e

    tool_call_buffers: dict[int, dict[str, Any]] = {}

    try:
        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta is None:
                continue

            # 文本增量
            if delta.content:
                full_content += delta.content
                yield {"type": "delta", "content": delta.content}

            # 工具调用增量（缓冲，流结束后统一 emit）
            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_call_buffers:
                        tool_call_buffers[idx] = {
                            "id": tc_delta.id or "",
                            "function": {"name": "", "arguments": ""},
                        }
                    buf = tool_call_buffers[idx]
                    if tc_delta.id:
                        buf["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            buf["function"]["name"] += tc_delta.function.name
                        if tc_delta.function.arguments:
                            buf["function"]["arguments"] += tc_delta.function.arguments
    except Exception as e:
        raise RuntimeError(f"LLM 流式中断：{e}") from e

    # 整理 tool_calls
    final_tool_calls = [
        tool_call_buffers[i] for i in sorted(tool_call_buffers.keys())
    ]
    # 兼容 DSML 格式：部分模型将 function calls 放在 content 而非 delta.tool_calls
    if not final_tool_calls and full_content:
        from hagoku.llm.sanitize import extract_dsml_tool_calls as _extract
        final_tool_calls = _extract(full_content)
    yield {
        "type": "end",
        "content": full_content,
        "tool_calls": final_tool_calls if final_tool_calls else None,
    }
