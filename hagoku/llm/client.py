"""LLM 客户端工厂

提供共享的 LLM 客户端创建函数，供 Orchestrator 和 Agent 基类共同使用。
使用 instructor 包装 OpenAI 兼容客户端以获得结构化输出能力。

CH-7e（2026-06-07）：_clear_proxy_env 全局 os.environ.pop 替换为 per-client
httpx transport。每个客户端持有独立的 HTTPTransport，禁用代理以避免 socks://
等不被 httpx 支持的 scheme 抛出 ValueError。不再污染进程级环境变量。
"""

from __future__ import annotations

from typing import Any

import httpx

from ..config import LLMConfig


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
        instructor 包装的 OpenAI 客户端，支持 response_model 参数

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
            mode=instructor.Mode.JSON,
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
