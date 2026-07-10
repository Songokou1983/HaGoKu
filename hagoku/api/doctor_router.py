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

# ── 灾备：通用提示词备份（文件恢复失败时的最后兜底）───────────────
_DEFAULT_PROMPT = """你是数据分析师。数据分析按五阶段推进：

理解字段：逐列给出中文名、业务含义、是否参与分析，展示为表格后调用 ask_user 请用户确认。用户确认后进入评估清洗；用户纠正字段含义则更新表格并调用 ask_user 重新确认。
评估清洗：检查数据质量问题，给出处理建议，展示为表格后调用 ask_user 请用户确认。用户确认后进入统计分析；用户有异议则更新评估并调用 ask_user 重新确认。
统计分析：根据分析目标和数据特征选择方法，跑检验，产出有统计支撑的发现后调用 ask_user 展示发现并请用户确认。
撰写报告：将确认的分析发现整理为正式报告。先在统计分析阶段调用 create_plot 生成图表，再在生成报告时将图表的 html_snippet 传入 sections 的 charts 字段。生成后调用 ask_user 请用户确认。
持续交互：报告生成后，对话进入自由交互模式。可根据用户追问做补充分析、深入某个发现、或调整结论。

每次回复都要让用户知道：你做了什么、结果是什么、接下来可以做什么。
不要只描述过程——要展示结果。不确定就问用户。
用户说的就是事实，冲突时以用户最新说的为准。"""


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

# ── 修复端点 ──────────────────────────────────────────────────────

class FixRequest(BaseModel):
    action: str  # reset_active_preset / restore_default_prompt / delete_preset


@router.post("/fix")
async def doctor_fix(req: FixRequest):
    """Doctor 执行修复操作。仅限安全的、可逆的操作。"""
    from pathlib import Path as _P

    if req.action == "reset_active_preset":
        # 清除激活预设 → 恢复默认 prompt.md
        af = _P.home() / ".hagoku" / "active_preset"
        if af.exists():
            af.unlink()
            return {"ok": True, "message": "已恢复默认提示词，下次分析生效"}
        return {"ok": True, "message": "当前已是默认提示词，无需操作"}

    if req.action == "restore_default_prompt":
        # 用 presets/general.md 覆盖 prompt.md
        prompt_path = _P(__file__).resolve().parent.parent / "agents" / "prompt.md"
        general_path = _P(__file__).resolve().parent.parent / "agents" / "presets" / "general.md"
        # 优先从 presets/general.md 恢复，文件缺失则用内置灾备
        if general_path.exists():
            content = general_path.read_text(encoding="utf-8")
        else:
            content = _DEFAULT_PROMPT
        prompt_path.write_text(content, encoding="utf-8")
        # 同时清除激活预设
        af = _P.home() / ".hagoku" / "active_preset"
        if af.exists():
            af.unlink()
        return {"ok": True, "message": "prompt.md 已从默认预设恢复"}

    if req.action == "delete_preset":
        raise HTTPException(400, "请通过「分析能力」面板删除预设，Doctor 不直接删除文件")

    raise HTTPException(400, f"未知修复操作: {req.action}")


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


# ── 代码层：操作手册匹配 ──────────────────────────────────────────

_OPS_MANUAL_RULES = [
    # (关键词列表, 操作, 回复模板)
    (
        ["分析结果不对", "分析不按预期", "预设出问题", "重置预设", "恢复默认提示词",
         "恢复默认预设", "active_preset", "预设有问题"],
        "reset_active_preset",
        "检测到预设相关问题。正在清除激活的预设，恢复默认提示词…"
    ),
    (
        ["prompt被改坏", "提示词坏了", "提示词被改", "改提示词后", "prompt.md",
         "分析崩溃", "改坏了", "不能用了"],
        "restore_default_prompt",
        "检测到提示词文件可能损坏。正在从灾备恢复默认提示词…"
    ),
    (
        ["连不上", "LLM不通", "502", "连接失败", "请求失败", "服务不可用"],
        "check_llm_connection",
        "检测到连接问题。正在检查 LLM 连通性…"
    ),
]


def _execute_fix(action: str) -> dict:
    """执行修复操作（同步，文件 I/O 不需要异步）。"""
    from pathlib import Path as _P

    if action == "reset_active_preset":
        af = _P.home() / ".hagoku" / "active_preset"
        existed = af.exists()
        if existed:
            af.unlink()
        return {"ok": True, "message": "已清除激活预设，恢复默认提示词" if existed else "当前已是默认提示词"}

    if action == "restore_default_prompt":
        prompt_path = _P(__file__).resolve().parent.parent / "agents" / "prompt.md"
        general_path = _P(__file__).resolve().parent.parent / "agents" / "presets" / "general.md"
        content = general_path.read_text(encoding="utf-8") if general_path.exists() else _DEFAULT_PROMPT
        prompt_path.write_text(content, encoding="utf-8")
        af = _P.home() / ".hagoku" / "active_preset"
        if af.exists():
            af.unlink()
        return {"ok": True, "message": "已从灾备恢复默认提示词"}

    if action == "check_llm_connection":
        try:
            from hagoku.tools.health import check_llm_health
            results = check_llm_health()
            passed = sum(1 for r in results if r.ok)
            details = "\n".join(f"{"✅" if r.ok else "❌"} {r.name}: {r.detail}" for r in results)
            return {"ok": True, "message": f"LLM 健康检查：{passed}/{len(results)} 通过\n{details}"}
        except Exception as e:
            return {"ok": False, "message": f"健康检查失败：{e}"}

    return {"ok": False, "message": f"未知操作: {action}"}


def _match_ops_manual(user_message: str) -> str | None:
    """代码层匹配操作手册。命中→直接执行修复；未命中→返回 None 交给 LLM。"""
    msg = user_message.lower()
    for keywords, action, intro in _OPS_MANUAL_RULES:
        if any(kw in msg for kw in keywords):
            result = _execute_fix(action)
            ok = "✅" if result["ok"] else "❌"
            return f"{intro}\n\n{ok} {result['message']}\n\n还有其他问题吗？"
    return None


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
            # 最新一份完整报告给 Doctor 分析
            try:
                content = reports[0].read_text(encoding="utf-8")
                audit_ctx = f"最新审计报告（{reports[0].name}）:\n{content[:3000]}\n"
                if len(content) > 3000:
                    audit_ctx += f"\n(报告共 {len(content)} 字，以上为前 3000 字)"
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

    # 读取操作手册
    ops_path = Path(__file__).resolve().parent.parent.parent / "docs" / "doctor-operations.md"
    try:
        ops_manual = ops_path.read_text(encoding="utf-8")
    except Exception:
        ops_manual = "操作手册不可用。reset_active_preset 用于预设/提示词问题；restore_default_prompt 用于 prompt.md 损坏。"

    # 构建 system_extra
    system_extra = f"""你是 HaGoKu Doctor，负责系统诊断和修复。
严格按照下方「操作手册」执行——不要自行发挥，不要建议用户手动编辑文件。

## 操作手册

{ops_manual}

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

    # ── 代码层：先用操作手册匹配用户问题 ──
    # 手册覆盖的场景由代码直接响应，不需要调 LLM
    code_reply = _match_ops_manual(req.message)
    if code_reply:
        return {"reply": code_reply}

    # ── LLM 兜底：手册没覆盖的复杂问题交给 LLM ──
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
