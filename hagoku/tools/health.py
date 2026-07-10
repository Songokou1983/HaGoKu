"""HaGoKu Studio 健康检查 — LLM 连接和系统状态"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class HealthCheckResult:
    """健康检查结果"""
    ok: bool
    name: str
    detail: str
    suggestions: list[str]


@dataclass
class LlmHealthReport:
    """LLM 健康检查综合报告 — 区分阻塞 vs 警告"""
    all_passed: bool = True
    blocking_failed: bool = False
    checks: list[HealthCheckResult] = field(default_factory=list)
    model_available: str = ""
    token_rate_tok_s: float = 0.0


def check_llm(config: Any) -> HealthCheckResult:
    """
    检查 LLM 连接是否可用（简化版，仅判断可达性）。
    如需完整 5 步检查，请使用 check_llm_health()。
    """
    result = check_llm_health(config)
    # 取第一个检查项作为兼容结果
    return result.checks[0] if result.checks else HealthCheckResult(
        ok=False,
        name="LLM 服务",
        detail="❌ 未执行检查",
        suggestions=["请检查配置"],
    )


def check_llm_health(config: Any) -> LlmHealthReport:
    """
    LLM 5 步前置健康检查。

    检查步骤：
      1. HTTP 可达性 (GET /models, timeout=5s)  → **阻塞**
      2. 模型存在（model）→ **阻塞**
      3. Chat completion 可用 ("ping")           → **阻塞**
      4. Token 速率 (< 5 tok/s → 警告)           → 警告
      5. JSON mode 可用性                         → 警告

    Returns:
        LlmHealthReport: 包含所有步骤结果、阻塞/警告区分。
    """
    base_url = config.llm.base_url.rstrip("/")
    api_key = (config.llm.api_key or "").strip()
    model = (config.llm.model or "").strip()

    headers = {"Authorization": f"Bearer {api_key}"} if api_key and api_key != "none" else {}
    report = LlmHealthReport()
    checks: list[HealthCheckResult] = []

    # --- 1. HTTP 可达性 ---
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{base_url}/models", headers=headers)
            if resp.status_code not in (200, 401, 403):
                checks.append(HealthCheckResult(
                    ok=False,
                    name="1. LLM 服务可达",
                    detail=f"❌ GET /models 返回 HTTP {resp.status_code}",
                    suggestions=["检查 LLM 服务是否运行", f"确认 base_url: {base_url}"],
                ))
                report.blocking_failed = True
                report.all_passed = False
                report.checks = checks
                return report
    except httpx.ConnectError:
        checks.append(HealthCheckResult(
            ok=False,
            name="1. LLM 服务可达",
            detail=f"❌ 无法连接: {base_url}",
            suggestions=["检查 LLM 服务是否运行", f"确认 base_url 配置正确"],
        ))
        report.blocking_failed = True
        report.all_passed = False
        report.checks = checks
        return report
    except httpx.TimeoutException:
        checks.append(HealthCheckResult(
            ok=False,
            name="1. LLM 服务可达",
            detail=f"❌ 连接超时: {base_url}",
            suggestions=["检查网络连接", "确认 LLM 服务负载正常"],
        ))
        report.blocking_failed = True
        report.all_passed = False
        report.checks = checks
        return report
    except httpx.RequestError as e:
        checks.append(HealthCheckResult(
            ok=False,
            name="1. LLM 服务可达",
            detail=f"❌ 请求错误: {e}",
            suggestions=["检查 base_url 格式", "确认 LLM 服务已启动"],
        ))
        report.blocking_failed = True
        report.all_passed = False
        report.checks = checks
        return report

    checks.append(HealthCheckResult(
        ok=True,
        name="1. LLM 服务可达",
        detail=f"✅ {base_url} 连接正常",
        suggestions=[],
    ))

    try:
        with httpx.Client(timeout=10.0) as client:
            # --- 2. 模型存在 ---
            try:
                models_resp = client.get(f"{base_url}/models", headers=headers)
                models_data = models_resp.json() if models_resp.status_code == 200 else {}
                available_models: set[str] = set()
                if "data" in models_data:
                    for item in models_data["data"]:
                        mid = item.get("id", "")
                        if mid:
                            available_models.add(mid)
                elif "models" in models_data:
                    for item in models_data["models"]:
                        if isinstance(item, dict):
                            mid = item.get("id", item.get("name", ""))
                        else:
                            mid = str(item)
                        if mid:
                            available_models.add(mid)

                missing_models = []
                for label, m in [("model", model)]:
                    if m and m not in available_models:
                        missing_models.append(f"{label}={m}")

                if missing_models:
                    checks.append(HealthCheckResult(
                        ok=False,
                        name="2. 模型存在",
                        detail=f"❌ 缺失: {', '.join(missing_models)}",
                        suggestions=["检查模型名拼写", f"可用模型: {sorted(available_models)[:10] if available_models else '无'}"],
                    ))
                    report.blocking_failed = True
                    report.all_passed = False
                else:
                    checks.append(HealthCheckResult(
                        ok=True,
                        name="2. 模型存在",
                        detail=f"✅ {model} 在列表中",
                        suggestions=[],
                    ))
            except Exception as e:
                checks.append(HealthCheckResult(
                    ok=False,
                    name="2. 模型存在",
                    detail=f"❌ 解析 /models 响应失败: {e}",
                    suggestions=["检查 LLM 服务是否兼容 OpenAI API"],
                ))
                report.blocking_failed = True
                report.all_passed = False

            # --- 3. Chat completion 可用 ---
            if not report.blocking_failed:
                try:
                    ping_body = {
                        "model": model,
                        "messages": [{"role": "user", "content": "hi"}],
                        "max_tokens": 64,
                        "temperature": 0,
                    }
                    ping_resp = client.post(
                        f"{base_url}/chat/completions",
                        headers={**headers, "Content-Type": "application/json"},
                        json=ping_body,
                    )
                    if ping_resp.status_code == 200:
                        data = ping_resp.json()
                        choices = data.get("choices", [])
                        # 通用判断：API 返回 200 + 有 choices 即为正常，
                        # 不检查 content 是否为空（不同模型行为不同）
                        if choices:
                            report.model_available = model
                            # 提取 token 用量
                            usage = data.get("usage", {})
                            completion_tokens = usage.get("completion_tokens", 0)
                            total_time = usage.get("total_time", None)
                            if total_time and total_time > 0:
                                report.token_rate_tok_s = completion_tokens / total_time
                            elif completion_tokens > 0:
                                report.token_rate_tok_s = completion_tokens / 1.0  # 估算
                            checks.append(HealthCheckResult(
                                ok=True,
                                name="3. Chat completion",
                                detail=f"✅ ping 通过 (model={model})",
                                suggestions=[],
                            ))
                        else:
                            checks.append(HealthCheckResult(
                                ok=False,
                                name="3. Chat completion",
                                detail="❌ 返回无 content",
                                suggestions=["检查模型是否支持 chat completion"],
                            ))
                            report.blocking_failed = True
                            report.all_passed = False
                    else:
                        checks.append(HealthCheckResult(
                            ok=False,
                            name="3. Chat completion",
                            detail=f"❌ HTTP {ping_resp.status_code}",
                            suggestions=["检查 API key", "确认模型名正确"],
                        ))
                        report.blocking_failed = True
                        report.all_passed = False
                except Exception as e:
                    checks.append(HealthCheckResult(
                        ok=False,
                        name="3. Chat completion",
                        detail=f"❌ 请求失败: {e}",
                        suggestions=["检查网络", "确认 LLM 服务负载正常"],
                    ))
                    report.blocking_failed = True
                    report.all_passed = False

            # --- 4. Token 速率 ---
            if not report.blocking_failed and report.token_rate_tok_s > 0:
                if report.token_rate_tok_s < 5:
                    checks.append(HealthCheckResult(
                        ok=False,
                        name="4. Token 速率",
                        detail=f"⚠️ {report.token_rate_tok_s:.1f} tok/s (< 5 tok/s)",
                        suggestions=["LLM 响应较慢，分析可能耗时较长", "考虑切换更快模型"],
                    ))
                    # 警告不设为 blocking
                else:
                    checks.append(HealthCheckResult(
                        ok=True,
                        name="4. Token 速率",
                        detail=f"✅ {report.token_rate_tok_s:.1f} tok/s",
                        suggestions=[],
                    ))
            else:
                checks.append(HealthCheckResult(
                    ok=True,
                    name="4. Token 速率",
                    detail="⚠️ 未能测量（不影响使用）",
                    suggestions=[],
                ))

            # --- 5. JSON mode（可选能力，始终标记为 ok）---
            # JSON mode 是 provider 特定功能，HaGoKu 使用 function calling 不需要它
            if not report.blocking_failed:
                try:
                    json_body = {
                        "model": model,
                        "messages": [{"role": "user", "content": 'Reply exactly: {"ok":true}'}],
                        "max_tokens": 32,
                        "temperature": 0,
                        "response_format": {"type": "json_object"},
                    }
                    json_resp = client.post(
                        f"{base_url}/chat/completions",
                        headers={**headers, "Content-Type": "application/json"},
                        json=json_body,
                    )
                    if json_resp.status_code == 200:
                        import json as _json
                        content = json_resp.json()["choices"][0]["message"]["content"]
                        _json.loads(content)  # 验证可解析
                        checks.append(HealthCheckResult(
                            ok=True,
                            name="5. JSON mode",
                            detail="✅ 可用",
                            suggestions=[],
                        ))
                    else:
                        checks.append(HealthCheckResult(
                            ok=True,
                            name="5. JSON mode",
                            detail=f"⚠️ HTTP {json_resp.status_code}",
                            suggestions=["部分功能可能降级"],
                        ))
                except Exception:
                    checks.append(HealthCheckResult(
                        ok=True,
                        name="5. JSON mode",
                        detail="⚠️ 不支持",
                    ))
            else:
                checks.append(HealthCheckResult(
                    ok=True,
                    name="5. JSON mode",
                    detail="⚠️ 跳过",
                ))

    except Exception as e:
        checks.append(HealthCheckResult(
            ok=False,
            name="LLM 综合检查",
            detail=f"❌ 异常: {e}",
            suggestions=["检查 LLM 服务状态"],
        ))
        report.blocking_failed = True
        report.all_passed = False

    report.checks = checks
    report.all_passed = all(c.ok for c in checks)
    return report


def check_system() -> list[HealthCheckResult]:
    """
    系统健康检查：LLM + 依赖库

    Returns:
        检查结果列表
    """
    from ..config import HaGoKuConfig

    results: list[HealthCheckResult] = []

    # LLM 检查（5 步）
    config = HaGoKuConfig.load()
    llm_report = check_llm_health(config)
    results.extend(llm_report.checks)

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