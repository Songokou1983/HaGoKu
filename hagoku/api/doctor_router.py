"""Doctor API — HaGoKu Doctor 审计端点（CO-D09）

提供系统健康检查、方法库/工具箱审计触发、审计报告列表与查看。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/doctor", tags=["doctor"])

AUDIT_DIR = Path.home() / ".hagoku" / "audits"


class HealthResponse(BaseModel):
    """系统健康检查响应模型。"""
    ok: bool
    total: int
    passed: int
    blocking_failed: bool
    checks: list[dict[str, Any]]
    model_available: str
    token_rate_tok_s: float


class AuditTriggerResponse(BaseModel):
    """审计触发响应。"""
    ok: bool
    report_path: str
    summary: dict[str, Any]


class ChatRequest(BaseModel):
    """Doctor 对话请求。"""
    message: str
    history: list[dict[str, str]] = []


class ChatResponse(BaseModel):
    """Doctor 对话响应。"""
    reply: str


@router.get("/health", response_model=HealthResponse)
async def doctor_health() -> dict[str, Any]:
    """执行系统健康检查（LLM 5 步 + 依赖库）。"""
    from hagoku.tools.health import check_system

    results = check_system()
    ok_count = sum(1 for r in results if r.ok)

    # 找到 LLM 检查中的模型和速率信息
    llm_result = next((r for r in results if r.name == "LLM 服务" or "LLM" in r.name), None)
    model_available = ""
    token_rate = 0.0

    # 尝试获取更详细的 LLM 健康报告
    try:
        from hagoku.config import HaGoKuConfig
        from hagoku.tools.health import check_llm_health
        cfg = HaGoKuConfig.load()
        llm_report = check_llm_health(cfg)
        model_available = llm_report.model_available
        token_rate = llm_report.token_rate_tok_s
    except Exception:
        pass

    return {
        "ok": ok_count == len(results),
        "total": len(results),
        "passed": ok_count,
        "blocking_failed": any(not r.ok for r in results[:3]),  # 前三项是阻塞
        "checks": [
            {
                "name": r.name,
                "ok": r.ok,
                "detail": r.detail,
                "suggestions": r.suggestions,
            }
            for r in results
        ],
        "model_available": model_available,
        "token_rate_tok_s": token_rate,
    }


@router.post("/audit/methods", response_model=AuditTriggerResponse)
async def trigger_method_audit() -> dict[str, Any]:
    """触发方法库审计（MethodCurator）。"""
    try:
        from hagoku.agents.method_curator.agent import run_method_audit
        path = run_method_audit()
        return {
            "ok": True,
            "report_path": str(path),
            "summary": {"report": path.name},
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Method audit failed: {e}")


@router.post("/audit/tools", response_model=AuditTriggerResponse)
async def trigger_tool_audit() -> dict[str, Any]:
    """触发工具箱审计（ToolCurator）。"""
    try:
        from hagoku.agents.tool_curator.agent import run_tool_audit
        path = run_tool_audit()
        return {
            "ok": True,
            "report_path": str(path),
            "summary": {"report": path.name},
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Tool audit failed: {e}")


@router.get("/audits")
async def list_audits() -> dict[str, Any]:
    """列出所有审计报告。"""
    if not AUDIT_DIR.exists():
        return {"audits": []}
    reports = []
    for f in sorted(AUDIT_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
        stat = f.stat()
        # 判断报告类型
        if f.name.startswith("method_"):
            rtype = "method"
        elif f.name.startswith("tool_"):
            rtype = "tool"
        elif f.name.startswith("lesson_"):
            rtype = "lesson"
        else:
            rtype = "unknown"
        reports.append({
            "name": f.name,
            "type": rtype,
            "size": stat.st_size,
            "mtime": int(stat.st_mtime),
        })
    return {"audits": reports}


@router.get("/audits/{filename}")
async def get_audit_report(filename: str) -> dict[str, Any]:
    """获取审计报告内容。"""
    # 安全：防止路径穿越
    if ".." in filename or "/" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = AUDIT_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Report not found")
    content = path.read_text(encoding="utf-8")
    return {"name": filename, "content": content, "size": len(content)}


@router.get("/status")
async def doctor_status() -> dict[str, Any]:
    """检查 Doctor 系统状态（LLM 可用性、audits 目录等）。"""
    from hagoku.config import HaGoKuConfig

    try:
        cfg = HaGoKuConfig.load()
        # meta_llm 优先；未配则回退主 LLM（create_meta_client 同样逻辑）
        meta_configured = bool(
            (cfg.meta_llm.base_url and cfg.meta_llm.model)
            or (cfg.llm.base_url and cfg.llm.model)
        )
    except Exception:
        meta_configured = False

    audits_exist = AUDIT_DIR.exists() and any(AUDIT_DIR.glob("*.md"))

    return {
        "meta_llm_configured": meta_configured,
        "audits_dir": str(AUDIT_DIR),
        "audits_exist": audits_exist,
    }


@router.post("/chat", response_model=ChatResponse)
async def doctor_chat(req: ChatRequest) -> dict[str, Any]:
    """Doctor 对话 — 用 meta LLM 回复用户维护问题。

    自动注入当前系统健康状态和最新审计摘要作为上下文。
    """
    from hagoku.config import HaGoKuConfig
    from hagoku.channel import build_messages
    from hagoku.tools.health import check_system

    cfg = HaGoKuConfig.load()

    # 创建 LLM 客户端：meta_llm 优先，否则回退主 LLM
    from openai import OpenAI
    import httpx as _httpx
    if cfg.meta_llm.base_url and cfg.meta_llm.model:
        client = OpenAI(
            base_url=cfg.meta_llm.base_url,
            api_key=cfg.meta_llm.api_key,
            timeout=120.0,
            http_client=_httpx.Client(transport=_httpx.HTTPTransport(retries=1)),
        )
        model = cfg.meta_llm.model
    else:
        client = OpenAI(
            base_url=cfg.llm.base_url,
            api_key=cfg.llm.api_key,
            timeout=120.0,
            http_client=_httpx.Client(transport=_httpx.HTTPTransport(retries=1)),
        )
        model = cfg.llm.model

    # 收集系统上下文
    health_ctx = ""
    try:
        results = check_system()
        ok_count = sum(1 for r in results if r.ok)
        health_ctx = f"系统健康：{ok_count}/{len(results)} 项通过\n"
        for r in results:
            icon = "✅" if r.ok else "❌"
            health_ctx += f"  {icon} {r.name}: {r.detail}\n"
    except Exception:
        health_ctx = "系统健康：无法获取\n"

    # 收集审计上下文
    audit_ctx = ""
    if AUDIT_DIR.exists():
        reports = sorted(AUDIT_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        if reports:
            audit_ctx = f"最近审计报告 ({len(reports)} 份):\n"
            for rp in reports[:3]:
                try:
                    content = rp.read_text(encoding="utf-8")[:300]
                    audit_ctx += f"\n### {rp.name}\n{content}\n"
                except Exception:
                    pass

    # 收集日志上下文
    log_ctx = ""
    try:
        log_path = cfg.work_dir / "hagoku.log"
        if log_path.exists():
            lines = log_path.read_text(encoding="utf-8").strip().split("\n")
            recent = lines[-30:]  # 最近 30 行
            errors = [l for l in recent if "ERROR" in l or "error" in l.lower() or "Traceback" in l]
            if errors:
                log_ctx = f"最近日志中的错误（{len(errors)} 条）:\n" + "\n".join(f"  {e[:200]}" for e in errors[-5:])
            else:
                log_ctx = f"最近 {len(recent)} 行日志无错误"
    except Exception:
        log_ctx = "无法读取日志"

    # 收集预设信息
    preset_ctx = ""
    try:
        active_file = Path.home() / ".hagoku" / "active_preset"
        if active_file.exists():
            pid = active_file.read_text(encoding="utf-8").strip()
            presets_json = Path(__file__).resolve().parent.parent / "agents" / "presets" / "presets.json"
            if presets_json.exists():
                import json as _j
                presets = _j.loads(presets_json.read_text(encoding="utf-8"))
                p = next((x for x in presets if x["id"] == pid), None)
                preset_ctx = f"激活预设: {p['name'] if p else pid}"
            else:
                preset_ctx = f"激活预设: {pid}"
        else:
            preset_ctx = "使用默认提示词 prompt.md"
    except Exception:
        preset_ctx = "无法读取预设信息"

    # 构建 system_extra
    system_extra = f"""你是 HaGoKu Doctor，负责系统诊断和维护。你可以：

- 诊断系统健康问题（LLM 连接、依赖库、配置）
- 分析日志中的错误
- 解读审计报告（方法库、工具箱）
- 建议修复方案——告诉用户具体操作步骤
- 回答 HaGoKu 架构和 prompt 预设的问题

你有以下权限和能力：
- 读取系统健康状态
- 读取最近日志
- 查看审计报告
- 了解当前配置和预设

常见诊断场景和修复建议：

| 症状 | 可能原因 | 操作 |
|------|---------|------|
| LLM 连接失败 | base_url/api_key 错误 | 检查设置页 → Pipeline LLM |
| 分析卡住/无响应 | LLM token 不足或超时 | 检查模型 token 上限 |
| 图表不显示 | Plotly CDN 加载失败 | 检查网络能否访问 cdn.plot.ly |
| 报告中文乱码 | 字体缺失 | 服务器安装中文字体 |
| 预设切换无效 | active_preset 文件损坏 | 删除 ~/.hagoku/active_preset 恢复默认 |
| 知识库不显示 | methods/ 目录为空 | 检查 hagoku/memory/methods/ |
| API 502 | 服务未启动或端口冲突 | 重启 hagoku-api |

## 当前系统状态

{health_ctx}

## 配置信息
Pipeline LLM: {cfg.llm.model} @ {cfg.llm.base_url}
Doctor LLM: {cfg.meta_llm.model or cfg.llm.model} @ {cfg.meta_llm.base_url or cfg.llm.base_url}
{preset_ctx}

## 日志

{log_ctx}

## 审计

{audit_ctx if audit_ctx else "暂无审计报告。"}
"""

    history = req.history or []
    # EXEMPT: 辅助 LLM — Doctor 维护对话，非主分析通道
    messages = build_messages(
        query="HaGoKu Doctor 维护对话",
        user_input=req.message,
        history=[{"role": h.get("role", "user"), "content": h.get("content", "")} for h in history],
        system_extra=system_extra,
    )

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.3,
            max_tokens=2048,
        )
        reply = resp.choices[0].message.content or ""
        return {"reply": reply}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Meta LLM 调用失败: {e}")
