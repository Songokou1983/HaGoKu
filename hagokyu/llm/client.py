"""LLM 客户端工厂

提供共享的 LLM 客户端创建函数，供 Orchestrator 和 Agent 基类共同使用。
使用 instructor 包装 OpenAI 兼容客户端以获得结构化输出能力。
"""

from __future__ import annotations

from typing import Any

from ..config import LLMConfig


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
        )


def create_deep_client(config: Any) -> Any:
    """
    创建深度推理客户端（Analyst、仲裁器用）

    模型选择: config.llm.model_deep or config.llm.model
    """
    deep_config = LLMConfig(
        model=config.llm.model_deep or config.llm.model,
        base_url=config.llm.base_url,
        api_key=config.llm.api_key,
        temperature=config.llm.temperature,
        max_tokens=config.llm.max_tokens,
    )
    return create_structured_llm_client(deep_config)


def create_quick_client(config: Any) -> Any:
    """
    创建快速客户端（Scout、Reporter、Scribe 反思用）

    模型选择: config.llm.model_quick or config.llm.model
    """
    quick_config = LLMConfig(
        model=config.llm.model_quick or config.llm.model,
        base_url=config.llm.base_url,
        api_key=config.llm.api_key,
        temperature=config.llm.temperature,
        max_tokens=4096,  # 快速模型用较短上下文
    )
    return create_structured_llm_client(quick_config)
