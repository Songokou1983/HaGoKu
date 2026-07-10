"""Prompt Lab API — prompt 模拟器后端（Phase E CO-M2 ✅）"""

from __future__ import annotations

import json as _json
import subprocess
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/prompt-lab", tags=["prompt-lab"])

from hagoku.observability.llm_dump import _get_default_dump_dir
DUMP_DIR = _get_default_dump_dir()
PROMPT_PATH = Path(__file__).resolve().parent.parent / "agents" / "prompt.md"
GATE_SCRIPT = Path(__file__).resolve().parent.parent.parent / "scripts" / "ci" / "prompt_gate.py"


class RunRequest(BaseModel):
    prompt_md: str
    messages: list[dict[str, Any]] = []
    tools: list[dict[str, Any]] | None = None
    model: str = "pipeline"


class CompareRequest(BaseModel):
    baseline_prompt: str
    current_prompt: str
    messages: list[dict[str, Any]] = []
    tools: list[dict[str, Any]] | None = None


class ApplyRequest(BaseModel):
    prompt_md: str


def _build_messages(prompt: str, history: list[dict], query: str = "Prompt Lab") -> list[dict]:
    """走 hagoku.channel.build_messages() 统一通道（Phase B 守门）。"""
    from hagoku.channel import build_messages
    return build_messages(
        query=query,
        user_input=query,
        system_extra=prompt,
        history=history,
    )


def _call_llm(messages: list[dict], tools: list[dict] | None, model_override: str):
    from hagoku.config import HaGoKuConfig

    cfg = HaGoKuConfig.load()
    base_url = cfg.meta_llm.base_url or cfg.llm.base_url
    api_key = cfg.meta_llm.api_key or cfg.llm.api_key
    model = model_override if model_override != "pipeline" else (cfg.meta_llm.model or cfg.llm.model)

    import openai
    client = openai.OpenAI(base_url=base_url, api_key=api_key or "none", timeout=60.0)
    resp = client.chat.completions.create(
        model=model, messages=messages, tools=tools or [],
        temperature=0.0, max_tokens=2048,
    )
    msg = resp.choices[0].message
    return {
        "content": msg.content or "",
        "tool_calls": [
            {"name": tc.function.name, "arguments": tc.function.arguments}
            for tc in (msg.tool_calls or [])
        ],
        "tokens": resp.usage.total_tokens if resp.usage else 0,
        "model": model,
    }


@router.get("/current-prompt")
async def get_current_prompt():
    if not PROMPT_PATH.exists():
        raise HTTPException(404, "prompt.md not found")
    return {"ok": True, "content": PROMPT_PATH.read_text(encoding="utf-8")}


@router.post("/run")
async def run_prompt(req: RunRequest):
    try:
        msgs = _build_messages(req.prompt_md, req.messages)
        result = _call_llm(msgs, req.tools, req.model)
        return {"ok": True, **result}
    except Exception as e:
        raise HTTPException(502, f"LLM 调用失败: {e}")


@router.post("/compare")
async def compare_prompts(req: CompareRequest):
    try:
        msgs = req.messages
        tools = req.tools or []
        baseline = _call_llm(_build_messages(req.baseline_prompt, msgs), tools, "pipeline")
        current = _call_llm(_build_messages(req.current_prompt, msgs), tools, "pipeline")
        b_tc = {tc["name"] for tc in baseline.get("tool_calls", [])}
        c_tc = {tc["name"] for tc in current.get("tool_calls", [])}
        changed = b_tc.symmetric_difference(c_tc)
        similarity = 1 - len(changed) / max(len(b_tc | c_tc), 1)
        return {
            "ok": True, "baseline": baseline, "current": current,
            "diff": {
                "changed_paths": sorted(changed),
                "similarity": round(similarity, 3),
                "baseline_tokens": baseline["tokens"],
                "current_tokens": current["tokens"],
            },
        }
    except Exception as e:
        raise HTTPException(502, f"LLM 调用失败: {e}")


@router.post("/apply")
async def apply_prompt(req: ApplyRequest):
    """应用 prompt.md: 先跑 prompt_gate → 返回 diff → 写盘（用户确认在 UI 做）。"""
    if not PROMPT_PATH.exists():
        raise HTTPException(404, "prompt.md not found")

    # 跑 prompt_gate 对比 baseline vs new
    baseline = PROMPT_PATH.read_text(encoding="utf-8")
    try:
        result = subprocess.run(
            [sys.executable, str(GATE_SCRIPT), str(PROMPT_PATH), "/dev/stdin"],
            input=req.prompt_md, capture_output=True, text=True, timeout=30,
            cwd=PROMPT_PATH.parent.parent,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(500, "prompt_gate 超时")
    except FileNotFoundError:
        raise HTTPException(500, "prompt_gate 脚本未找到")

    gate_output = result.stdout.strip()
    # 写盘
    PROMPT_PATH.write_text(req.prompt_md, encoding="utf-8")
    return {
        "ok": True,
        "gate_output": gate_output,
        "message": "prompt.md 已更新。gate 输出见 gate_output 字段。",
    }


@router.post("/audit-lessons")
async def audit_lessons():
    """触发 LessonAuditor 即时质量审（Meta-3.3 UI 按钮）。"""
    from hagoku.agents.lesson_auditor.agent import run_ad_hoc_audit
    path = run_ad_hoc_audit()
    return {"ok": True, "report_path": str(path)}

# ── 预设管理 ─────────────────────────────────────────────────────
import json as _json2
from pathlib import Path as _Path2

PRESETS_DIR = _Path2(__file__).resolve().parent.parent / "agents" / "presets"
ACTIVE_PRESET_FILE = _Path2.home() / ".hagoku" / "active_preset"


@router.get("/presets")
async def list_presets():
    manifest = PRESETS_DIR / "presets.json"
    if not manifest.exists():
        return {"presets": []}
    presets = _json2.loads(manifest.read_text(encoding="utf-8"))
    # 标记当前激活的
    active = ""
    if ACTIVE_PRESET_FILE.exists():
        active = ACTIVE_PRESET_FILE.read_text(encoding="utf-8").strip()
    for p in presets:
        p["active"] = (p["id"] == active)
    return {"presets": presets}


@router.post("/presets/activate")
async def activate_preset(data: dict):
    preset_id = data.get("id", "").strip()
    if preset_id:
        preset_path = PRESETS_DIR / f"{preset_id}.md"
        if not preset_path.exists():
            raise HTTPException(404, f"预设 {preset_id} 不存在")
        ACTIVE_PRESET_FILE.parent.mkdir(parents=True, exist_ok=True)
        ACTIVE_PRESET_FILE.write_text(preset_id, encoding="utf-8")
    else:
        # 传空 = 恢复默认
        if ACTIVE_PRESET_FILE.exists():
            ACTIVE_PRESET_FILE.unlink()
    return {"ok": True}


@router.get("/presets/{preset_id}/content")
async def get_preset_content(preset_id: str):
    path = PRESETS_DIR / f"{preset_id}.md"
    if not path.exists():
        raise HTTPException(404, f"预设 {preset_id} 不存在")
    return {"ok": True, "content": path.read_text(encoding="utf-8")}


@router.get("/dumps")
async def list_dumps(limit: int = 20):
    files = sorted(
        DUMP_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True
    )[:limit] if DUMP_DIR.exists() else []
    return {
        "dumps": [
            {"filename": f.name, "seq": i + 1, "mtime": int(f.stat().st_mtime)}
            for i, f in enumerate(files)
        ]
    }


@router.get("/dump/{filename}")
async def get_dump(filename: str):
    path = DUMP_DIR / filename
    if not path.exists():
        raise HTTPException(404, "Dump not found")
    try:
        data = _json.loads(path.read_text(encoding="utf-8"))
        return {"ok": True, **data}
    except Exception:
        raise HTTPException(500, "Dump parse error")
