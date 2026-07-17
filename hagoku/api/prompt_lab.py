"""Prompt Lab API — prompt 实验与预设管理（Phase E CO-M2 ✅）"""

from __future__ import annotations

import hashlib
import json as _json
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/prompt-lab", tags=["prompt-lab"])

PRESETS_DIR = Path(__file__).resolve().parent.parent / "agents" / "presets"
ACTIVE_PRESET_FILE = Path.home() / ".hagoku" / "active_preset"


@router.get("/presets")
async def list_presets():
    manifest = PRESETS_DIR / "presets.json"
    if not manifest.exists():
        return {"presets": []}
    presets = _json.loads(manifest.read_text(encoding="utf-8"))
    # 标记当前激活的。无预设时"通用商业分析"即为默认生效
    active = ""
    if ACTIVE_PRESET_FILE.exists():
        active = ACTIVE_PRESET_FILE.read_text(encoding="utf-8").strip()
    if not active:
        active = "general"
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

# ── 创建预设 ──────────────────────────────────────────────────────

class CreatePresetRequest(BaseModel):
    name: str
    icon: str = "bar-chart"
    description: str = ""
    prompt: str = ""


@router.post("/presets/create")
async def create_preset(req: CreatePresetRequest):
    if not req.name.strip():
        raise HTTPException(400, "名称不能为空")
    # 生成安全的 ID（纯中文名用 hash）
    preset_id = re.sub(r"[^a-z0-9_]", "", req.name.lower().replace(" ", "_"))
    if not preset_id:
        preset_id = "p" + hashlib.md5(req.name.encode()).hexdigest()[:7]
    # 避免重名
    existing_ids = {p["id"] for p in _load_presets_manifest()}
    base_id = preset_id
    n = 1
    while preset_id in existing_ids:
        preset_id = f"{base_id}{n}"
        n += 1
    # 写 .md
    preset_path = PRESETS_DIR / f"{preset_id}.md"
    preset_path.write_text(req.prompt, encoding="utf-8")
    # 更新 manifest
    manifest = _load_presets_manifest()
    manifest.append({
        "id": preset_id,
        "name": req.name.strip(),
        "icon": req.icon,
        "description": req.description.strip(),
    })
    _write_presets_manifest(manifest)
    return {"ok": True, "id": preset_id}


# ── 删除预设 ──────────────────────────────────────────────────────

@router.delete("/presets/{preset_id}")
async def delete_preset(preset_id: str):
    if preset_id == "general":
        raise HTTPException(400, "默认预设不可删除")
    preset_path = PRESETS_DIR / f"{preset_id}.md"
    if not preset_path.exists():
        raise HTTPException(404, f"预设 {preset_id} 不存在")
    preset_path.unlink()
    # 从 manifest 移除
    manifest = [p for p in _load_presets_manifest() if p["id"] != preset_id]
    _write_presets_manifest(manifest)
    # 如果删除的是激活预设，清除
    if ACTIVE_PRESET_FILE.exists():
        active = ACTIVE_PRESET_FILE.read_text(encoding="utf-8").strip()
        if active == preset_id:
            ACTIVE_PRESET_FILE.unlink()
    return {"ok": True}


# ── 更新预设（编辑已有预设的 prompt） ─────────────────────────────

class UpdatePresetRequest(BaseModel):
    name: str = ""
    icon: str = ""
    description: str = ""
    prompt: str = ""


@router.put("/presets/{preset_id}")
async def update_preset(preset_id: str, req: UpdatePresetRequest):
    if preset_id == "general":
        raise HTTPException(400, "默认预设不可修改")
    preset_path = PRESETS_DIR / f"{preset_id}.md"
    if not preset_path.exists():
        raise HTTPException(404, f"预设 {preset_id} 不存在")
    # 更新 .md
    if req.prompt.strip():
        preset_path.write_text(req.prompt, encoding="utf-8")
    # 更新 manifest
    manifest = _load_presets_manifest()
    for p in manifest:
        if p["id"] == preset_id:
            if req.name.strip():
                p["name"] = req.name.strip()
            if req.icon.strip():
                p["icon"] = req.icon.strip()
            if req.description.strip():
                p["description"] = req.description.strip()
            break
    _write_presets_manifest(manifest)
    return {"ok": True}


# ── manifest 读写辅助 ─────────────────────────────────────────────

def _load_presets_manifest() -> list[dict]:
    manifest = PRESETS_DIR / "presets.json"
    if not manifest.exists():
        return []
    return _json.loads(manifest.read_text(encoding="utf-8"))


def _write_presets_manifest(manifest: list[dict]) -> None:
    PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    (PRESETS_DIR / "presets.json").write_text(
        _json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


