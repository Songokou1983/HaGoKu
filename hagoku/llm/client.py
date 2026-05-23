"""LLM 客户端工厂

提供共享的 LLM 客户端创建函数，供 Orchestrator 和 Agent 基类共同使用。
使用 instructor 包装 OpenAI 兼容客户端以获得结构化输出能力。
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Generator

from ..config import LLMConfig

# 需要清理的代理环境变量 key 列表，避免 socks:// 等不被 httpx 支持的 scheme
_PROXY_ENV_KEYS = [
    "ALL_PROXY", "all_proxy",
    "HTTP_PROXY", "http_proxy",
    "HTTPS_PROXY", "https_proxy",
]


@contextmanager
def _clear_proxy_env() -> Generator[None, None, None]:
    """清理代理环境变量，避免 httpx 对 socks:// 等不支持 scheme 抛出 ValueError。

    适用于 LLM 服务为本地/内网访问、无需代理的场景。
    退出上下文时自动恢复原始值。
    """
    _saved = {k: os.environ.pop(k, None) for k in _PROXY_ENV_KEYS}
    try:
        yield
    finally:
        for k, v in _saved.items():
            if v is not None:
                os.environ[k] = v
            elif k in os.environ:
                del os.environ[k]


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

        with _clear_proxy_env():
            client = instructor.from_openai(
                OpenAI(
                    base_url=llm_config.base_url,
                    api_key=llm_config.api_key,
                    timeout=120.0,
                ),
                mode=instructor.Mode.JSON,
            )
            return client
    except ImportError:
        # 退回原始 OpenAI（无结构化输出）
        from openai import OpenAI

        with _clear_proxy_env():
            return OpenAI(
                base_url=llm_config.base_url,
                api_key=llm_config.api_key,
                timeout=120.0,
            )


def create_raw_client(config: Any) -> Any:
    """
    创建原始 OpenAI 客户端（不做 instructor 包装）

    适用于需要 raw chat.completions.create() 的场景（如 Scout 的 JSON mode）。
    """
    from openai import OpenAI

    llm = _unwrap_llm(config)

    with _clear_proxy_env():
        return OpenAI(
            base_url=llm.base_url,
            api_key=llm.api_key,
            timeout=120.0,
        )


def _unwrap_llm(config: Any) -> LLMConfig:
    """兼容 HaGoKuConfig（含 .llm 属性）和裸 LLMConfig 两种输入"""
    if isinstance(config, LLMConfig):
        return config
    # 假设是 HaGoKuConfig
    return config.llm


def create_deep_client(config: Any) -> Any:
    """
    创建深度推理客户端（Analyst、仲裁器用）

    模型选择: llm.model_deep or llm.model
    """
    llm = _unwrap_llm(config)
    deep_config = LLMConfig(
        model=llm.model_deep or llm.model,
        base_url=llm.base_url,
        api_key=llm.api_key,
        temperature=llm.temperature,
        max_tokens=llm.max_tokens,
    )
    return create_structured_llm_client(deep_config)


def create_quick_client(config: Any) -> Any:
    """
    创建快速客户端（Scout、Reporter、Scribe 反思用）

    模型选择: llm.model_quick or llm.model
    """
    llm = _unwrap_llm(config)
    quick_config = LLMConfig(
        model=llm.model_quick or llm.model,
        base_url=llm.base_url,
        api_key=llm.api_key,
        temperature=llm.temperature,
        max_tokens=8192,  # 快速模型用较短上下文
    )
    return create_structured_llm_client(quick_config)
