"""HaGoKu 健康检查 — LLM 连接和系统状态"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class HealthCheckResult:
    """健康检查结果"""
    ok: bool
    name: str
    detail: str
    suggestions: list[str]


def check_llm(config: Any) -> HealthCheckResult:
    """
    检查 LLM 连接是否可用

    Returns:
        HealthCheckResult: 包含检查结果和建议
    """
    base_url = config.llm.base_url
    api_key = config.llm.api_key

    # 1. 基础连接测试
    try:
        with httpx.Client(timeout=5.0) as client:
            # 先测 /models 端点（大多数兼容 API 都支持）
            headers = {}
            if api_key and api_key != "none":
                headers["Authorization"] = f"Bearer {api_key}"

            resp = client.get(f"{base_url.rstrip('/v1')}/models", headers=headers)
            if resp.status_code in (200, 401, 403):
                # 401/403 说明服务可达，只是认证问题
                return HealthCheckResult(
                    ok=True,
                    name="LLM 服务",
                    detail=f"✅ LLM 服务可达 ({base_url})",
                    suggestions=[],
                )
            elif resp.status_code == 404:
                # 尝试 /v1/models
                resp2 = client.get(f"{base_url}/models", headers=headers)
                if resp2.status_code in (200, 401, 403):
                    return HealthCheckResult(
                        ok=True,
                        name="LLM 服务",
                        detail=f"✅ LLM 服务可达 ({base_url})",
                        suggestions=[],
                    )
    except httpx.ConnectError:
        pass
    except httpx.TimeoutException:
        return HealthCheckResult(
            ok=False,
            name="LLM 服务",
            detail=f"❌ LLM 服务连接超时: {base_url}",
            suggestions=[
                "检查 LLM 服务是否正在运行",
                "确认 base_url 配置正确（默认: http://localhost:8000/v1）",
                "如果是远程服务，检查网络连接",
            ],
        )
    except httpx.RequestError as e:
        return HealthCheckResult(
            ok=False,
            name="LLM 服务",
            detail=f"❌ 无法连接到 LLM 服务: {e}",
            suggestions=[
                f"检查 base_url 是否正确（当前: {base_url}）",
                "确认 LLM 服务已启动",
                "检查防火墙/代理设置",
            ],
        )

    # 2. 连接失败的情况
    return HealthCheckResult(
        ok=False,
        name="LLM 服务",
        detail=f"❌ 无法连接到 LLM 服务: {base_url}",
        suggestions=[
            "检查 LLM 服务是否正在运行",
            "确认 base_url 配置正确（默认: http://localhost:8000/v1）",
            "如果是本地模型（如 vLLM/llama.cpp），确认服务已启动",
            f"使用 `hagokyu config` 查看当前配置，或设置 HAGOKYU_LLM_BASE_URL 环境变量",
        ],
    )


def check_system() -> list[HealthCheckResult]:
    """
    系统健康检查：LLM + 依赖库

    Returns:
        检查结果列表
    """
    from ..config import HaGoKuConfig

    results: list[HealthCheckResult] = []

    # LLM 检查
    config = HaGoKuConfig.load()
    results.append(check_llm(config))

    # 依赖库检查
    critical_deps = {
        "pandas": "数据处理",
        "numpy": "数值计算",
        "scipy": "统计检验",
        "pingouin": "高级统计",
    }
    for lib, purpose in critical_deps.items():
        try:
            __import__(lib)
            results.append(HealthCheckResult(
                ok=True,
                name=lib,
                detail=f"✅ {lib} 已安装（{purpose}）",
                suggestions=[],
            ))
        except ImportError:
            results.append(HealthCheckResult(
                ok=False,
                name=lib,
                detail=f"❌ {lib} 未安装（{purpose}）",
                suggestions=[f"运行: pip install {lib}"],
            ))

    return results


def format_health_report(results: list[HealthCheckResult]) -> str:
    """格式化健康检查报告（不含标题，由调用方控制）"""
    lines = ["=" * 40]
    for r in results:
        lines.append(f"\n{'✅' if r.ok else '❌'} {r.name}")
        lines.append(f"   {r.detail}")
        if r.suggestions:
            lines.append("   修复建议:")
            for s in r.suggestions:
                lines.append(f"     • {s}")

    ok_count = sum(1 for r in results if r.ok)
    total = len(results)
    lines.append(f"\n{'✅' if ok_count == total else '⚠️'} 检查完成: {ok_count}/{total} 项通过")
    return "\n".join(lines)
