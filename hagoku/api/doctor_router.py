"""Doctor API — HaGoKu Doctor 审计端点（CO-D09）

提供系统健康检查、方法库/工具箱审计触发、审计报告列表与查看。
"""

from __future__ import annotations

import json as _json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/doctor", tags=["doctor"])

AUDIT_DIR = Path.home() / ".hagoku" / "audits"
CASES_PATH = Path.home() / ".hagoku" / "doctor" / "cases.jsonl"
PRESETS_DIR = Path(__file__).resolve().parent.parent / "agents" / "presets"

# 默认预设清单（从 presets.json 动态加载，与 prompt_lab.py:22 同模式）
default_presets = _json.loads(
    (PRESETS_DIR / "presets.json").read_text(encoding="utf-8")
)

# ── 病历 ──────────────────────────────────────────────────────────

def _record_case(symptom: str, fix: str, ok: bool, detail: str) -> None:
    """追加一条病历。"""
    import json as _j
    CASES_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "symptom": symptom,
        "fix": fix,
        "ok": ok,
        "detail": detail,
    }
    with open(CASES_PATH, "a", encoding="utf-8") as f:
        f.write(_j.dumps(entry, ensure_ascii=False) + "\n")


def _recent_cases(limit: int = 20) -> str:
    """读取最近病历，格式化为 Markdown 表格。"""
    if not CASES_PATH.exists():
        return ""
    lines = []
    try:
        import json as _j
        with open(CASES_PATH, encoding="utf-8") as f:
            all_cases = [_j.loads(line) for line in f if line.strip()]
    except Exception:
        return ""
    if not all_cases:
        return ""
    recent = all_cases[-limit:]
    lines.append("## 历史病历（最近修复记录）")
    lines.append("| 时间 | 症状 | 修复 | 结果 |")
    lines.append("|------|------|------|------|")
    for c in reversed(recent):
        ts = c.get("timestamp", "")[:16].replace("T", " ")
        symptom = (c.get("symptom", "") or "")[:50]
        fix = c.get("fix", "")
        icon = "✅" if c.get("ok") else "❌"
        lines.append(f"| {ts} | {symptom} | {fix} | {icon} |")
    return "\n".join(lines)

# ── 灾备：通用提示词备份（文件恢复失败时的最后兜底）───────────────
_DEFAULT_PROMPT = """你是数据分析师。数据分析按五阶段推进：

理解字段：逐列给出中文名、业务含义，展示为表格后等待用户确认。
评估清洗：检查数据质量问题，给出处理建议，展示为表格后等待用户确认。
统计分析：根据分析目标和数据特征选择方法，跑检验，产出有统计支撑的发现后等待用户确认。
撰写报告：将确认的分析发现整理为正式报告。先在统计分析阶段调用 create_plot 生成图表，再在生成报告时将图表的 html_snippet 传入 sections 的 charts 字段。生成后等待用户确认。
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
    from hagoku.tools.health import check_dependencies_only
    import asyncio

    # 依赖库检查（同步，轻量）
    results = check_dependencies_only()
    ok_count = sum(1 for r in results if r.ok)

    # 找到 LLM 检查中的模型和速率信息
    llm_result = next((r for r in results if r.name == "LLM 服务" or "LLM" in r.name), None)
    model_available = ""
    token_rate = 0.0

    # 尝试获取更详细的 LLM 健康报告（用线程池避免阻塞事件循环）
    try:
        from hagoku.config import HaGoKuConfig
        from hagoku.tools.health import check_llm_health
        import asyncio
        cfg = HaGoKuConfig.load()
        loop = asyncio.get_running_loop()
        llm_report = await loop.run_in_executor(None, check_llm_health, cfg)
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

@router.post("/full-check")
async def full_health_check() -> dict[str, Any]:
    """全面健康检查——系统健康 + 方法库 + 工具箱一次跑完，返回统一报告。"""
    from hagoku.tools.health import check_system
    from hagoku.agents.method_curator.agent import MethodCurator
    from hagoku.agents.tool_curator.agent import ToolCurator

    report_lines = ["# HaGoKu 全面健康检查报告", ""]

    # 1. 系统健康
    report_lines.append("## 系统健康")
    try:
        results = check_system()
        passed = sum(1 for r in results if r.ok)
        report_lines.append(f"通过: {passed}/{len(results)}")
        for r in results:
            icon = "✅" if r.ok else "❌"
            report_lines.append(f"- {icon} {r.name}: {r.detail}")
    except Exception as e:
        report_lines.append(f"❌ 系统检查失败: {e}")
    report_lines.append("")

    # 2. 方法库审计
    report_lines.append("## 方法库")
    try:
        curator = MethodCurator()
        report = curator.audit()
        report_lines.append(f"- 方法文档: {report.total_methods}")
        report_lines.append(f"- 全部有 frontmatter: {'✅' if len(report.missing_frontmatter) == 0 else '❌ ' + str(len(report.missing_frontmatter)) + ' 缺失'}")
        report_lines.append(f"- 工具引用全部已注册: {'✅' if len(report.missing_tools) == 0 else '❌ ' + str(len(report.missing_tools)) + ' 未注册'}")
        report_lines.append(f"- 被引用工具(去重): {len(report.tools_referenced)}")
        report_lines.append(f"- 孤儿工具: {len(report.orphan_tools)}")
    except Exception as e:
        report_lines.append(f"❌ 方法库审计失败: {e}")
    report_lines.append("")

    # 3. 工具箱审计
    report_lines.append("## 工具箱")
    try:
        from hagoku.agents.tool_curator.agent import ToolCurator as TC
        tc = TC()
        treport = tc.audit()
        report_lines.append(f"- 已注册工具: {treport.total_tools}")
        report_lines.append(f"- 有测试: {treport.tools_with_tests}")
        report_lines.append(f"- 有方法文档: {treport.tools_with_docs}")
        if treport.prompt_fake_tools:
            report_lines.append(f"- ⚠️ prompt 引用但未注册: {', '.join(treport.prompt_fake_tools)}")
    except Exception as e:
        report_lines.append(f"❌ 工具箱审计失败: {e}")
    report_lines.append("")

    # 4. 预设状态
    report_lines.append("## 预设")
    try:
        import json as _j
        presets_path = Path(__file__).resolve().parent.parent / "agents" / "presets" / "presets.json"
        active_file = Path.home() / ".hagoku" / "active_preset"
        presets = _j.loads(presets_path.read_text(encoding="utf-8")) if presets_path.exists() else []
        active = active_file.read_text(encoding="utf-8").strip() if active_file.exists() else "默认(general)"
        report_lines.append(f"- 可用预设: {len(presets)}")
        report_lines.append(f"- 当前激活: {active}")
        for p in presets:
            report_lines.append(f"  - {p['name']} ({p['id']})")
    except Exception as e:
        report_lines.append(f"❌ 预设检查失败: {e}")

    report_text = "\n".join(report_lines)
    return {"ok": True, "report": report_text}


class FixRequest(BaseModel):
    action: str  # reset_active_preset / restore_default_prompt / delete_preset


# ── Fix 动作注册表 ──────────────────────────────────────────────────

def _fix_reset_active_preset(_params: str) -> dict:
    af = Path.home() / ".hagoku" / "active_preset"
    if af.exists():
        af.unlink()
        return {"ok": True, "message": "已恢复默认提示词，下次分析生效"}
    return {"ok": True, "message": "当前已是默认提示词，无需操作"}


def _fix_restore_default_prompt(_params: str) -> dict:
    prompt_path = Path(__file__).resolve().parent.parent / "agents" / "prompt.md"
    general_path = Path(__file__).resolve().parent.parent / "agents" / "presets" / "general.md"
    content = general_path.read_text(encoding="utf-8") if general_path.exists() else _DEFAULT_PROMPT
    prompt_path.write_text(content, encoding="utf-8")
    af = Path.home() / ".hagoku" / "active_preset"
    if af.exists():
        af.unlink()
    return {"ok": True, "message": "prompt.md 已从默认预设恢复"}


def _fix_check_llm_connection(_params: str) -> dict:
    try:
        from hagoku.tools.health import check_llm_health
        from hagoku.config import HaGoKuConfig
        report = check_llm_health(HaGoKuConfig.load())
        passed = sum(1 for r in report.checks if r.ok)
        details = " | ".join(f"{'✅' if r.ok else '❌'} {r.name}" for r in report.checks)
        return {"ok": True, "message": f"LLM 健康检查：{passed}/{len(report.checks)} 通过 — {details}"}
    except Exception as e:
        return {"ok": False, "message": f"健康检查失败：{e}"}


def _fix_full_system_check(_params: str) -> dict:
    try:
        from hagoku.tools.health import check_system
        results = check_system()
        passed = sum(1 for r in results if r.ok)
        details = "\n".join(f"  {'✅' if r.ok else '❌'} {r.name}: {r.detail}" for r in results)
        return {"ok": True, "message": f"系统健康：{passed}/{len(results)} 通过\n{details}"}
    except Exception as e:
        return {"ok": False, "message": f"系统检查失败：{e}"}


def _fix_clear_project_memory(_params: str) -> dict:
    return {"ok": False, "message": "请通过 Doctor chat 告诉我项目名，我会自动清除"}


def _fix_clear_active_state(_params: str) -> dict:
    af = Path.home() / ".hagoku" / "active_preset"
    if af.exists():
        af.unlink()
    return {"ok": True, "message": "已清除活跃状态和激活预设，刷新页面后重新开始"}


def _fix_restore_custom_preset(_params: str) -> dict:
    return {"ok": False, "message": "请通过分析能力面板删除损坏的预设，然后新建"}


def _fix_emergency_recovery(_params: str) -> dict:
    results = []
    prompt_path = Path(__file__).resolve().parent.parent / "agents" / "prompt.md"
    general_path = Path(__file__).resolve().parent.parent / "agents" / "presets" / "general.md"
    try:
        content = general_path.read_text(encoding="utf-8") if general_path.exists() else _DEFAULT_PROMPT
        prompt_path.write_text(content, encoding="utf-8")
        results.append("✅ prompt.md 已恢复")
    except Exception as e:
        results.append(f"❌ prompt.md 恢复失败: {e}")
    af = Path.home() / ".hagoku" / "active_preset"
    if af.exists():
        af.unlink()
        results.append("✅ 激活预设已清除")
    if not general_path.exists():
        general_path.parent.mkdir(parents=True, exist_ok=True)
        general_path.write_text(_DEFAULT_PROMPT, encoding="utf-8")
        results.append("✅ presets/general.md 已从灾备恢复")
    presets_json = Path(__file__).resolve().parent.parent / "agents" / "presets" / "presets.json"
    presets_json.write_text(_json.dumps(default_presets, ensure_ascii=False, indent=2), encoding="utf-8")
    results.append("✅ presets.json 已重置为默认")
    msg = "紧急恢复完成:\n" + "\n".join(results) + "\n\n请刷新页面，分析功能已恢复出厂状态。"
    return {"ok": True, "message": msg}


def _fix_create_kb_entry(params_str: str) -> dict:
    import json as _j
    try:
        params = _j.loads(params_str) if params_str else {}
    except Exception:
        return {"ok": False, "message": "参数格式错误，请提供有效的 JSON"}
    category = params.get("category", "statistics")
    filename = params.get("filename", "").strip()
    if not filename:
        return {"ok": False, "message": "filename 不能为空"}
    methods_root = Path(__file__).resolve().parent.parent / "memory" / "methods"
    target_dir = methods_root / category
    target_dir.mkdir(parents=True, exist_ok=True)
    lines = ["---"]
    if params.get("title"): lines.append(f"title: {params['title']}")
    if params.get("summary"): lines.append(f"summary: {params['summary']}")
    lines.append(f"category: {category}")
    if params.get("tags"): lines.append(f"tags: [{', '.join(params['tags'])}]")
    if params.get("tools"):
        lines.append("tools:")
        for t in params["tools"]:
            lines.append(f"  - {t}")
    lines.append("---")
    lines.append("")
    if params.get("content"):
        lines.append(params["content"])
    (target_dir / filename).write_text("\n".join(lines), encoding="utf-8")
    return {"ok": True, "message": f"已创建知识库条目: {category}/{filename}"}


def _fix_fix_kb_frontmatter(params_str: str) -> dict:
    import json as _j, re
    try:
        params = _j.loads(params_str) if params_str else {}
    except Exception:
        return {"ok": False, "message": "参数格式错误"}
    kb_path = params.get("path", "").strip()
    if not kb_path:
        return {"ok": False, "message": "path 不能为空"}
    methods_root = Path(__file__).resolve().parent.parent / "memory" / "methods"
    target = (methods_root / kb_path).resolve()
    if not str(target).startswith(str(methods_root.resolve())):
        return {"ok": False, "message": "非法路径"}
    if not target.exists():
        return {"ok": False, "message": f"文件不存在: {kb_path}"}
    content = target.read_text(encoding="utf-8")
    field = params.get("field", "")
    value = params.get("value")
    if field == "tools" and isinstance(value, list):
        if re.search(r'^tools:', content, re.MULTILINE):
            content = re.sub(
                r'^tools:.*(\n(?:  - .*\n)*)?',
                'tools:\n' + '\n'.join(f'  - {t}' for t in value) + '\n',
                content, flags=re.MULTILINE,
            )
        else:
            content = re.sub(
                r'^(---\n)',
                f'---\ntools:\n' + '\n'.join(f'  - {t}' for t in value) + '\n',
                content,
            )
        target.write_text(content, encoding="utf-8")
        return {"ok": True, "message": f"已修复 {kb_path} 的 tools 字段"}
    return {"ok": False, "message": f"不支持的字段: {field}"}


def _fix_register_tool(params_str: str) -> dict:
    import json as _j
    try:
        params = _j.loads(params_str) if params_str else {}
    except Exception:
        return {"ok": False, "message": "参数格式错误"}
    tool_name = params.get("name", "").strip()
    tool_file = params.get("file", "").strip()
    if not tool_name or not tool_file:
        return {"ok": False, "message": "name 和 file 不能为空"}
    tools_dir = Path(__file__).resolve().parent.parent / "tools"
    target = (tools_dir / tool_file).resolve()
    if not str(target).startswith(str(tools_dir.resolve())):
        return {"ok": False, "message": "非法路径"}
    if not target.exists():
        return {"ok": False, "message": f"文件不存在: {tool_file}"}
    handler = params.get("handler", f"_handle_{tool_name}")
    desc = params.get("description") or tool_name
    params_schema = _j.dumps(params.get("parameters", {"type": "object", "properties": {}, "required": []}))
    phase = _j.dumps(params.get("phase_tag", ["跑统计"]))
    reg_block = (
        f'\n# Doctor: registered {tool_name}\n'
        f'agent_tools.register(Tool(\n'
        f'    name="{tool_name}",\n'
        f'    description="{desc}",\n'
        f'    parameters={params_schema},\n'
        f'    handler={handler},\n'
        f'    phase_tag={phase},\n'
        f'))\n'
    )
    with open(target, 'a') as f:
        f.write(reg_block)
    return {"ok": True, "message": f"已注册工具 {tool_name} 到 {tool_file}"}


def _fix_unregister_tool(params_str: str) -> dict:
    import json as _j, re
    try:
        params = _j.loads(params_str) if params_str else {}
    except Exception:
        return {"ok": False, "message": "参数格式错误"}
    tool_name = params.get("name", "").strip()
    tool_file = params.get("file", "").strip()
    if not tool_name or not tool_file:
        return {"ok": False, "message": "name 和 file 不能为空"}
    tools_dir = Path(__file__).resolve().parent.parent / "tools"
    target = (tools_dir / tool_file).resolve()
    if not str(target).startswith(str(tools_dir.resolve())):
        return {"ok": False, "message": "非法路径"}
    if not target.exists():
        return {"ok": False, "message": f"文件不存在: {tool_file}"}
    content = target.read_text(encoding="utf-8")
    pattern = rf"(agent_tools\.register\(Tool\(\s*\n\s*name=\"{re.escape(tool_name)}\".*?\)\s*\)\s*)"
    if re.search(pattern, content, re.DOTALL):
        content = re.sub(pattern, r"# Doctor: disabled \1", content, flags=re.DOTALL)
        target.write_text(content, encoding="utf-8")
        return {"ok": True, "message": f"已禁用工具 {tool_name}"}
    return {"ok": False, "message": f"未找到工具 {tool_name} 的注册代码"}


def _fix_create_tool_stub(params_str: str) -> dict:
    import json as _j
    try:
        params = _j.loads(params_str) if params_str else {}
    except Exception:
        return {"ok": False, "message": "参数格式错误"}
    tool_name = params.get("name", "").strip()
    if not tool_name:
        return {"ok": False, "message": "name 不能为空"}
    handler_name = params.get("handler", f"_handle_{tool_name}")
    desc = params.get("description") or tool_name
    params_schema = _j.dumps(params.get("parameters", {"type": "object", "properties": {}, "required": []}))
    phase = _j.dumps(params.get("phase_tag", ["跑统计"]))
    implementation = params.get("implementation", "").strip()
    reason = params.get("reason", "预设扩展需要")
    tools_dir = Path(__file__).resolve().parent.parent / "tools"
    stub_file = tools_dir / "_doctor_tools.py"
    if not stub_file.exists():
        stub_file.write_text(
            "from __future__ import annotations\n"
            + '"""Doctor 创建的工具。"""\n'
            + "from typing import Any\n"
            + "import pandas as pd\n"
            + "from hagoku.tools.registry import Tool, agent_tools\n\n",
            encoding="utf-8",
        )
    if implementation:
        code = (
            f"\n# Doctor: {tool_name} — {reason}\n{implementation}\n\n"
            f"agent_tools.register(Tool(\n"
            f'    name="{tool_name}",\n    description="{desc}",\n'
            f"    parameters={params_schema},\n    handler={handler_name},\n"
            f"    phase_tag={phase},\n))\n"
        )
    else:
        code = (
            f'\n# Doctor: stub for "{tool_name}" — {reason}\n'
            f"def {handler_name}(args: dict, ctx: dict, df: pd.DataFrame | None) -> dict:\n"
            f'    return {{"error": "{tool_name} 桩——替换为真实实现"}}\n'
            f"\nagent_tools.register(Tool(\n"
            f'    name="{tool_name}",\n'
            f'    description="{desc}",\n'
            f"    parameters={params_schema},\n"
            f"    handler={handler_name},\n"
            f"    phase_tag={phase},\n"
            f"))\n"
        )
    with open(stub_file, 'a') as f:
        f.write(code)
    kind = "已创建" if implementation else "已创建桩"
    return {"ok": True, "message": f"{kind}工具 {tool_name} → tools/_doctor_tools.py"}


_FIX_ACTIONS: dict[str, Any] = {
    "reset_active_preset":    _fix_reset_active_preset,
    "restore_default_prompt": _fix_restore_default_prompt,
    "check_llm_connection":   _fix_check_llm_connection,
    "full_system_check":      _fix_full_system_check,
    "clear_project_memory":   _fix_clear_project_memory,
    "clear_active_state":     _fix_clear_active_state,
    "restore_custom_preset":  _fix_restore_custom_preset,
    "emergency_recovery":     _fix_emergency_recovery,
    "create_kb_entry":        _fix_create_kb_entry,
    "fix_kb_frontmatter":     _fix_fix_kb_frontmatter,
    "register_tool":          _fix_register_tool,
    "unregister_tool":        _fix_unregister_tool,
    "create_tool_stub":       _fix_create_tool_stub,
}

# 需要 admin 权限才能执行的操作（后续设置页面控制）
_ADMIN_ACTIONS = {
    "clear_project_memory", "emergency_recovery",
    "register_tool", "unregister_tool", "create_tool_stub",
}


def _run_fix(action: str, params: str = "") -> dict:
    """执行修复操作。两个入口（API + chat）共用。"""
    fn = _FIX_ACTIONS.get(action)
    if fn is None:
        return {"ok": False, "message": f"未知操作: {action}"}
    return fn(params)


@router.post("/fix")
async def doctor_fix(req: FixRequest):
    if req.action == "delete_preset":
        raise HTTPException(400, "请通过「分析能力」面板删除预设，Doctor 不直接删除文件")
    return _run_fix(req.action)


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


def _doctor_do_fix(action: str, _fix_params: str = "") -> dict:
    """执行 Doctor 修复操作。两个入口共用 _run_fix。"""
    return _run_fix(action, _fix_params)


@router.post("/chat", response_model=ChatResponse)
async def doctor_chat(req: ChatRequest) -> dict[str, Any]:
    """Doctor 对话 — 用 meta LLM 回复用户维护问题。

    自动注入当前系统健康状态和最新审计摘要作为上下文。
    """
    from hagoku.config import HaGoKuConfig
    from hagoku.channel import build_messages
    from hagoku.tools.health import check_system
    import json as _json

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

    # 收集审计上下文——方法库和工具箱各取最新一份
    audit_ctx = ""
    if AUDIT_DIR.exists():
        method_reports = sorted(AUDIT_DIR.glob("method_audit_*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        tool_reports = sorted(AUDIT_DIR.glob("tool_audit_*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        parts = []
        if method_reports:
            try:
                content = method_reports[0].read_text(encoding="utf-8")
                parts.append(f"## 方法库审计（{method_reports[0].name}）\n{content[:2000]}")
            except Exception:
                pass
        if tool_reports:
            try:
                content = tool_reports[0].read_text(encoding="utf-8")
                parts.append(f"## 工具箱审计（{tool_reports[0].name}）\n{content[:1500]}")
            except Exception:
                pass
        if parts:
            audit_ctx = "\n\n".join(parts)

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
需要执行修复操作时，调用 execute_fix 工具（传入 action 和可选的 params），不要在正文中写 [fix:xxx] 标记。

## 操作手册

{ops_manual}

## 当前系统状态

{health_ctx}

## 配置信息
Pipeline LLM（主分析）: {cfg.llm.model} @ {cfg.llm.base_url}
Doctor LLM（云端，用于诊断修复，不分析数据）: {cfg.meta_llm.model or cfg.llm.model} @ {cfg.meta_llm.base_url or cfg.llm.base_url}
{preset_ctx}

## 日志

{log_ctx}

## 审计

{audit_ctx if audit_ctx else "暂无审计报告。"}

## 历史病历

{_recent_cases() if _recent_cases() else "暂无历史病历。"}
"""

    history = req.history or []

    # LLM 读操作手册 → 理解问题 → 决定修复操作
    # EXEMPT: 辅助 LLM — Doctor 维护对话，非主分析通道
    messages = build_messages(
        query="HaGoKu Doctor 维护对话",
        user_input=req.message,
        history=[{"role": h.get("role", "user"), "content": h.get("content", "")} for h in history],
        system_extra=system_extra,
    )

    try:
        # ── 构建 execute_fix 工具 ──
        execute_fix_tool = {
            "type": "function",
            "function": {
                "name": "execute_fix",
                "description": "执行系统修复操作。先描述问题和诊断结果，再调用此工具执行修复。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": list(_FIX_ACTIONS.keys()),
                            "description": "要执行的修复操作",
                        },
                        "params": {
                            "type": "object",
                            "description": "操作的附加参数（JSON 对象，可选）",
                        },
                    },
                    "required": ["action"],
                },
            },
        }

        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.3,
            max_tokens=2048,
            tools=[execute_fix_tool],
            tool_choice="auto",
        )
        msg = resp.choices[0].message

        # ── 优先走 tool_calls ──
        fix_results: list[dict] = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                if tc.function.name != "execute_fix":
                    continue
                try:
                    args = _json.loads(tc.function.arguments) if tc.function.arguments else {}
                except (_json.JSONDecodeError, TypeError):
                    fix_results.append({"ok": False, "message": "参数解析失败"})
                    continue
                action = args.get("action", "")
                params = _json.dumps(args.get("params", {}), ensure_ascii=False) if args.get("params") else ""
                result = _run_fix(action, params)
                fix_results.append(result)
                _record_case(
                    symptom=req.message,
                    fix=action,
                    ok=result["ok"],
                    detail=result.get("message", ""),
                )

            # 将 tool 结果回传给 LLM 生成最终回复
            messages.append({"role": "assistant", "content": msg.content, "tool_calls": [
                {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls if tc.function.name == "execute_fix"
            ]})
            for i, tc in enumerate(msg.tool_calls):
                if tc.function.name != "execute_fix":
                    continue
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": _json.dumps(fix_results[i] if i < len(fix_results) else {"ok": False, "message": "未知错误"}, ensure_ascii=False),
                })
            resp2 = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.3,
                max_tokens=1024,
            )
            reply = resp2.choices[0].message.content or ""
        else:
            reply = msg.content or ""

        # ── 降级：正则兼容旧格式 [fix:xxx] ──
        import re as _re
        fix_match = _re.search(r"\[fix:(\w+)\s*(\{[^}]+\})?\]", reply)
        if fix_match:
            action = fix_match.group(1)
            params = fix_match.group(2) or ""
            result = _doctor_do_fix(action, params)
            reply = _re.sub(r"\[fix:\w+\]", "", reply).strip()
            icon = "✅" if result["ok"] else "❌"
            reply += f"\n\n---\n{icon} 已执行 {action}：{result['message']}"
            # 记录病历
            _record_case(
                symptom=req.message,
                fix=action,
                ok=result["ok"],
                detail=result.get("message", ""),
            )

        return {"reply": reply}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Meta LLM 调用失败: {e}")
