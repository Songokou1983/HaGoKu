"""HaGoKu Studio FastAPI server — REST + WebSocket"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from hagoku.api.ws_handler import ws_handler


@asynccontextmanager
async def lifespan(app: FastAPI):
    """初始化 Orchestrator，确保每个 uvicorn 工作进程都正确绑定 EventBus。"""
    try:
        from hagoku.api.ws_handler import set_orchestrator
        from hagoku.config import HaGoKuConfig
        from hagoku.manager.orchestrator import Orchestrator

        config = HaGoKuConfig.load()
        orchestrator = Orchestrator(config)
        set_orchestrator(orchestrator)
    except Exception as exc:  # 配置缺失时降级为懒初始化
        import logging
        logging.getLogger(__name__).warning("Orchestrator lifespan init failed: %s", exc)
    yield


app = FastAPI(title="HaGoKu Studio API", version="0.1.0", lifespan=lifespan)

# 环境区分：生产环境锁定 CORS，开发环境开放
_hagoku_env = os.environ.get("HAGOKU_ENV", "").strip().lower()
if _hagoku_env in ("production", "prod"):
    _cors_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
else:
    _cors_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


# ── 项目目录（与 `HaGoKuConfig.output.project_dir` / `HAGOKYU_PROJECT_DIR` 一致）────
def _projects_root() -> Path:
    try:
        from hagoku.config import HaGoKuConfig

        return HaGoKuConfig.load().output.project_dir
    except Exception:
        return Path(os.path.expanduser("~/.hagoku/projects"))


# ── GET /api/projects — 列出所有项目名 ──────────────────────
@app.get("/api/projects")
async def list_projects():
    root = _projects_root()
    if not root.exists():
        return {"projects": []}
    names = [d.name for d in sorted(root.iterdir()) if d.is_dir()]
    return {"projects": names}


# ── POST /api/projects — 创建新项目 ─────────────────────────
class CreateProjectRequest(BaseModel):
    name: str
    description: str = ""


@app.post("/api/projects")
async def create_project(req: CreateProjectRequest):
    import re as _re
    name = req.name.strip()
    if not name or not _re.match(r'^[a-zA-Z0-9_-]+$', name):
        raise HTTPException(400, "项目名称只允许英文字母、数字、下划线和连字符")
    proj_dir = _projects_root() / name
    proj_dir.mkdir(parents=True, exist_ok=True)
    # Persist to metadata DB
    try:
        from hagoku.storage.database import HaGoKuDB
        db = HaGoKuDB.get_instance()
        desc = req.description.strip()
        # create_project uses INSERT OR IGNORE — if row already exists, update description explicitly
        db.create_project(name, description=desc)
        if desc:
            db.update_project(name, description=desc)
    except Exception:
        pass
    return {"project": name, "created": True}


# ── GET /api/reports/{project_name} — 列出该项目所有 run 的报告 ──
@app.get("/api/reports/{project_name}")
async def list_reports(project_name: str):
    project_dir = _projects_root() / project_name
    if not project_dir.exists():
        return {"reports": []}
    # 支持 runs/{run_id}/output/*.html 和 output/*.html 两种路径
    files = sorted(
        list(project_dir.glob("runs/*/output/*.html")) +
        list(project_dir.glob("output/*.html")),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    return {
        "reports": [
            {
                "name": f"{f.parent.parent.name}/{f.name}" if f.parent.parent.name != project_name else f.name,
                "url": f"/api/reports/{project_name}/{f.parent.parent.name}/{f.name}"
                       if f.parent.parent.name != project_name else f"/api/reports/{project_name}/{f.name}",
                "mtime": int(f.stat().st_mtime),
            }
            for f in files
        ]
    }


# ── GET /api/reports/{project_name}/{run_id}/{filename} — 返回 run 子目录报告或护栏说明 ──
@app.get("/api/reports/{project_name}/{run_id}/{filename}")
async def get_report_run(project_name: str, run_id: str, filename: str):
    if "/" in filename:
        raise HTTPException(400, "Invalid filename")
    path = _projects_root() / project_name / "runs" / run_id / "output" / filename
    if not path.exists():
        raise HTTPException(404, "File not found")
    if filename.endswith(".html"):
        return HTMLResponse(path.read_text(encoding="utf-8"))
    # 其他文件（GUARDRAILS_BLOCKED.md 等）按文本返回
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(path.read_text(encoding="utf-8"))


# ── GET /api/reports/{project_name}/{filename} — 兼容旧路径 ──
@app.get("/api/reports/{project_name}/{filename}")
async def get_report(project_name: str, filename: str):
    if not filename.endswith(".html") or "/" in filename:
        raise HTTPException(400, "Invalid filename")
    path = _projects_root() / project_name / "output" / filename
    if not path.exists():
        raise HTTPException(404, "Report not found")
    return HTMLResponse(path.read_text(encoding="utf-8"))


def _hagoku_dotenv_path() -> Path:
    """用户级环境变量文件（与 hagoku.config 加载路径一致）。"""
    return Path.home() / ".hagoku" / ".env"


def _dotenv_set(path: Path, key: str, value: str) -> None:
    from dotenv import set_key

    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.touch()
    set_key(str(path), key, value, quote_mode="always")


# ── GET /api/config — 读取当前前端可见配置 ───────────────────
@app.get("/api/config")
async def get_config():
    from hagoku.config import HaGoKuConfig

    try:
        cfg = HaGoKuConfig.load()
        ak = (cfg.llm.api_key or "").strip()
        api_key_configured = bool(ak and ak.lower() != "none")
        m = (cfg.llm.model or "").strip()
        mq_eff = ((cfg.llm.model_quick or m) or "").strip() or m
        md_eff = ((cfg.llm.model_deep or m) or "").strip() or m
        main_eff = m or md_eff
        sub_display = "" if mq_eff == main_eff else mq_eff
        return {
            "llm": {
                "base_url": cfg.llm.base_url or "",
                "main_model": main_eff,
                "sub_model": sub_display,
                "model": main_eff,
                "model_quick": mq_eff,
                "model_deep": md_eff,
                "api_key_configured": api_key_configured,
            },
        }
    except Exception:
        return {
            "llm": {
                "base_url": "",
                "main_model": "",
                "sub_model": "",
                "model": "",
                "model_quick": "",
                "model_deep": "",
                "api_key_configured": False,
            },
        }


class LlmConfigBody(BaseModel):
    """OpenAI 兼容服务：网址 + 密钥 + 模型名称 + 可选「前面几步」另一模型名；写入 ~/.hagoku/.env。"""

    model_config = ConfigDict(protected_namespaces=())

    base_url: str
    main_model: str
    api_key: str = ""
    sub_model: str = ""


@app.post("/api/config/llm")
async def post_llm_config(req: LlmConfigBody):
    """
    将 LLM 连接参数写入 ~/.hagoku/.env（仅本机开发场景；生产环境应加鉴权或禁用）。
    已运行的 hagoku-api 进程仍使用旧环境变量，需重启后生效。
    模型名称写入 HAGOKYU_LLM_MODEL 与 HAGOKYU_LLM_MODEL_DEEP；可选的「前面几步」模型名
    写入 HAGOKYU_LLM_MODEL_QUICK（留空则与上面相同）。
    """
    path = _hagoku_dotenv_path()
    base_url = req.base_url.strip()
    main = req.main_model.strip()
    sub = req.sub_model.strip() or main
    if not base_url or not main:
        raise HTTPException(status_code=400, detail="网址和模型名称不能为空")
    try:
        _dotenv_set(path, "HAGOKYU_LLM_BASE_URL", base_url)
        _dotenv_set(path, "HAGOKYU_LLM_MODEL", main)
        _dotenv_set(path, "HAGOKYU_LLM_MODEL_DEEP", main)
        _dotenv_set(path, "HAGOKYU_LLM_MODEL_QUICK", sub)
        if req.api_key.strip():
            _dotenv_set(path, "HAGOKYU_LLM_API_KEY", req.api_key.strip())
        from dotenv import dotenv_values

        vals = dotenv_values(path) or {}
        akv = str(vals.get("HAGOKYU_LLM_API_KEY") or "").strip()
        api_key_configured = bool(akv and akv.lower() != "none")
        mq_eff = str(vals.get("HAGOKYU_LLM_MODEL_QUICK") or sub).strip() or main
        md_eff = str(vals.get("HAGOKYU_LLM_MODEL_DEEP") or main).strip() or main
        sub_display = "" if mq_eff == main else mq_eff
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "ok": True,
        "restart_required": True,
        "hint": "已经存到本机配置文件。请重新启动一次后端（运行 hagoku-api 的那个窗口关掉再开），新设置才会用在分析里。",
        "llm": {
            "base_url": str(vals.get("HAGOKYU_LLM_BASE_URL") or base_url),
            "main_model": main,
            "sub_model": sub_display,
            "model": main,
            "model_quick": mq_eff,
            "model_deep": md_eff,
            "api_key_configured": api_key_configured,
        },
    }


# ── POST /api/config/llm/test — 测试模型连接 ────────────────
class LlmTestBody(BaseModel):
    base_url: str
    main_model: str
    api_key: str = ""


@app.post("/api/config/llm/test")
async def test_llm_connection(req: LlmTestBody):
    """
    用当前表单中的参数发送一次最小请求，验证 API 可达、密钥有效、模型存在。
    """
    import os as _os

    base_url = req.base_url.strip()
    model = req.main_model.strip()
    api_key = req.api_key.strip()

    if not base_url or not model:
        raise HTTPException(status_code=400, detail="网址和模型名称不能为空")

    try:
        from openai import OpenAI
        from hagoku.llm.client import _clear_proxy_env

        with _clear_proxy_env():
            client = OpenAI(base_url=base_url, api_key=api_key or "none", timeout=15.0)
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=4,
                temperature=0,
            )

        content = response.choices[0].message.content or ""
        return {
            "ok": True,
            "model": model,
            "base_url": base_url,
            "reply": content[:200],
            "latency_ms": round(response.usage.total_tokens if response.usage else 0, 1),
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"连接失败: {exc}") from exc


# ── GET /api/knowledge/{project_name} — 列出项目知识库文件 ──
@app.get("/api/knowledge/{project_name}")
async def list_knowledge(project_name: str):
    kb_dir = _projects_root() / project_name / "kb"
    if not kb_dir.exists():
        return {"entries": []}
    files = [f.stem for f in kb_dir.glob("*.md")]
    return {"entries": files}


# ── PATCH /api/projects/{project_name} — 更新项目描述 ───────
class UpdateProjectRequest(BaseModel):
    description: str = ""


@app.patch("/api/projects/{project_name}")
async def update_project(project_name: str, req: UpdateProjectRequest):
    proj_dir = _projects_root() / project_name
    if not proj_dir.exists():
        raise HTTPException(404, "Project not found")
    try:
        from hagoku.storage.database import HaGoKuDB
        db = HaGoKuDB.get_instance()
        db.create_project(project_name)
        db.update_project(project_name, description=req.description.strip())
    except Exception as exc:
        raise HTTPException(500, str(exc))
    return {"project": project_name, "updated": True}


# ── DELETE /api/projects/{project_name} — 删除项目 ──────────
@app.delete("/api/projects/{project_name}")
async def delete_project(project_name: str):
    import shutil
    proj_dir = _projects_root() / project_name
    if not proj_dir.exists():
        raise HTTPException(404, "Project not found")
    try:
        shutil.rmtree(proj_dir)
        from hagoku.storage.database import HaGoKuDB
        db = HaGoKuDB.get_instance()
        db.conn.execute("DELETE FROM projects WHERE id = ?", (project_name,))
        db.conn.commit()
    except Exception as exc:
        raise HTTPException(500, str(exc))
    return {"project": project_name, "deleted": True}


# ── GET /api/projects/{project_name}/detail — 项目详情（含最近运行摘要）──
@app.get("/api/projects/{project_name}/detail")
async def get_project_detail(project_name: str):
    import json as _json
    import sqlite3

    proj_dir = _projects_root() / project_name
    if not proj_dir.exists():
        raise HTTPException(404, "Project not found")

    runs_dir = proj_dir / "runs"
    run_dirs = sorted(
        [d for d in runs_dir.iterdir() if d.is_dir()],
        key=lambda d: d.name,
        reverse=True,
    ) if runs_dir.exists() else []
    run_count = len(run_dirs)

    # Last run metadata
    last_query = ""
    last_run_at = ""
    last_status = "none"
    last_guardrails_blocked = False
    if run_dirs:
        latest = run_dirs[0]
        out_dir = latest / "output"
        last_guardrails_blocked = (out_dir / "GUARDRAILS_BLOCKED.md").exists()
        html_exists = (out_dir / "report.html").exists()
        last_run_at = latest.name
        meta_file = latest / "run_meta.json"
        if meta_file.exists():
            try:
                meta = _json.loads(meta_file.read_text(encoding="utf-8"))
                last_query = meta.get("query", "")
                output_path = meta.get("output_path", "")
                if output_path:
                    op = Path(output_path)
                    if op.exists() and op.suffix.lower() == ".html":
                        html_exists = True
            except Exception:
                pass
        if last_guardrails_blocked:
            last_status = "guardrails_blocked"
        elif html_exists:
            last_status = "completed"
        else:
            last_status = "unknown"

    db_path = Path(os.path.expanduser("~/.hagoku/hagoku.db"))
    data_path = ""
    created_at = ""
    description = ""
    if db_path.exists():
        try:
            conn = sqlite3.connect(str(db_path))
            row = conn.execute(
                "SELECT created_at, data_path, description FROM projects WHERE id = ?",
                (project_name,),
            ).fetchone()
            conn.close()
            if row:
                created_at  = row[0] or ""
                data_path   = row[1] or ""
                description = row[2] or ""
        except Exception:
            pass

    return {
        "name": project_name,
        "created_at": created_at,
        "data_path": data_path,
        "description": description,
        "run_count": run_count,
        "last_query": last_query,
        "last_run_at": last_run_at,
        "last_status": last_status,
        "last_guardrails_blocked": last_guardrails_blocked,
    }


# ── GET /api/projects/{project_name}/runs — 运行历史列表 ────
@app.get("/api/projects/{project_name}/runs")
async def get_project_runs(project_name: str):
    import json as _json

    runs_dir = _projects_root() / project_name / "runs"
    if not runs_dir.exists():
        return {"runs": []}

    runs = []
    for run_dir in sorted(runs_dir.iterdir(), key=lambda d: d.name, reverse=True):
        if not run_dir.is_dir():
            continue
        meta_file = run_dir / "run_meta.json"
        if not meta_file.exists():
            continue
        try:
            meta = _json.loads(meta_file.read_text(encoding="utf-8"))
            rid = meta.get("run_id", run_dir.name)
            output_path = meta.get("output_path", "")
            out = run_dir / "output"
            guardrails_blocked = (out / "GUARDRAILS_BLOCKED.md").exists()
            html_exists = (out / "report.html").exists()
            if output_path:
                op = Path(output_path)
                if op.exists() and op.suffix.lower() == ".html":
                    html_exists = True
            if guardrails_blocked:
                status = "guardrails_blocked"
            elif html_exists:
                status = "completed"
            else:
                status = "unknown"
            report_url = None
            if html_exists:
                fname = "report.html"
                if not (out / "report.html").exists() and output_path:
                    op = Path(output_path)
                    if op.exists():
                        fname = op.name
                report_url = f"/api/reports/{project_name}/{rid}/{fname}"
            guardrails_notice_url = (
                f"/api/reports/{project_name}/{rid}/GUARDRAILS_BLOCKED.md"
                if guardrails_blocked else None
            )
            runs.append({
                "run_id": rid,
                "query": meta.get("query", ""),
                "status": status,
                "report_url": report_url,
                "guardrails_notice_url": guardrails_notice_url,
                "guardrails_blocked": guardrails_blocked,
            })
        except Exception:
            runs.append({"run_id": run_dir.name, "query": "", "status": "unknown", "report_url": None, "guardrails_blocked": False})

    return {"runs": runs}


# ── GET /api/projects/{project_name}/files — 列出项目数据文件 ─
_DATA_EXTENSIONS = {".csv", ".tsv", ".json", ".jsonl", ".xlsx", ".xls", ".parquet", ".txt"}

@app.get("/api/projects/{project_name}/files")
async def list_project_files(project_name: str):
    proj_dir = _projects_root() / project_name
    if not proj_dir.exists():
        raise HTTPException(404, "Project not found")
    files = []
    # Scan project root and data/ subdirectory
    for subdir in [proj_dir, proj_dir / "data"]:
        if not subdir.exists():
            continue
        for f in sorted(subdir.iterdir()):
            if f.is_file() and f.suffix.lower() in _DATA_EXTENSIONS:
                files.append({
                    "name": f.name,
                    "path": str(f),
                    "size": f.stat().st_size,
                    "mtime": int(f.stat().st_mtime),
                })
    return {"files": files}


# ── GET /api/projects/{project_name}/kanban/tasks — Scribe 看板任务（Web 流程引导）─
@app.get("/api/projects/{project_name}/kanban/tasks")
async def list_project_kanban_tasks(project_name: str):
    """
    返回当前项目 kanban.db 中的任务。
    每次分析 run 会 init_pipeline 再挂一组 Scout→Reporter 任务；只取**时间上新的一组**（至多 4 条）避免列表无限变长。
    """
    proj_dir = _projects_root() / project_name
    if not proj_dir.is_dir():
        raise HTTPException(404, "Project not found")
    db_path = proj_dir / "kanban.db"
    if not db_path.exists():
        return {"tasks": []}

    from hagoku.storage.kanban import KanbanDB

    kb = KanbanDB.get_instance(proj_dir)
    rows = kb.list_tasks()
    if not rows:
        return {"tasks": []}
    rows.sort(key=lambda t: str(t.get("created_at") or ""), reverse=True)
    latest = rows[:4]
    latest.sort(key=lambda t: str(t.get("created_at") or ""))
    tasks = [
        {
            "id": r["id"],
            "agent": r["agent"],
            "title": r["title"],
            "description": (r.get("description") or ""),
            "status": r["status"],
            "priority": r.get("priority", 0),
            "created_at": r.get("created_at"),
            "updated_at": r.get("updated_at"),
            "completed_at": r.get("completed_at"),
            "result": r.get("result"),
            "comments": [
                {
                    "id": c["id"],
                    "task_id": c["task_id"],
                    "author": c["author"],
                    "body": c["body"],
                    "created_at": c["created_at"],
                }
                for c in kb.get_comments(r["id"])
            ],
        }
        for r in latest
    ]
    return {"tasks": tasks}


# ── POST /api/projects/{project_name}/upload — 上传数据文件 ───
@app.post("/api/projects/{project_name}/upload")
async def upload_project_file(project_name: str, file: UploadFile = File(...)):
    proj_dir = _projects_root() / project_name
    if not proj_dir.exists():
        raise HTTPException(404, "Project not found")
    filename = Path(file.filename or "upload").name
    if not filename or Path(filename).suffix.lower() not in _DATA_EXTENSIONS:
        raise HTTPException(400, f"不支持的文件类型，允许: {', '.join(_DATA_EXTENSIONS)}")
    data_dir = proj_dir / "data"
    data_dir.mkdir(exist_ok=True)
    dest = data_dir / filename
    content = await file.read()
    dest.write_bytes(content)
    # Auto-bind data_path to project in DB
    try:
        from hagoku.storage.database import HaGoKuDB
        db = HaGoKuDB.get_instance()
        db.create_project(project_name)
        db.update_project(project_name, data_path=str(dest))
    except Exception:
        pass
    return {"name": filename, "path": str(dest), "size": len(content)}


# ── GET /api/kb — 全局学术知识库（kb/_registry.yaml） ───────
def _kb_registry_path() -> Path:
    return Path(__file__).resolve().parent.parent / "kb" / "_registry.yaml"


def _kb_load_registry_entries() -> list[dict]:
    import yaml

    registry = _kb_registry_path()
    if not registry.exists():
        return []
    try:
        data = yaml.safe_load(registry.read_text(encoding="utf-8")) or {}
        return list(data.get("entries", []))
    except Exception:
        return []


def _kb_strip_frontmatter(raw: str) -> str:
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
    return raw.strip()


@app.get("/api/kb")
async def list_kb():
    return {"entries": _kb_load_registry_entries()}


@app.get("/api/kb/content")
async def get_kb_content(filename: str):
    """返回注册表内某条 Markdown 的正文（转 HTML），供知识库详情页展示。"""
    import html as html_stdlib
    import re

    fn = (filename or "").strip().replace("\\", "/")
    if not fn or fn.startswith("/") or ".." in fn.split("/"):
        raise HTTPException(400, "Invalid filename")

    entries = _kb_load_registry_entries()
    allowed = {str(e.get("filename", "")).replace("\\", "/") for e in entries if e.get("filename")}
    if fn not in allowed:
        raise HTTPException(404, "Unknown knowledge file")

    kb_root = Path(__file__).resolve().parent.parent / "kb"
    path = (kb_root / fn).resolve()
    kb_resolved = kb_root.resolve()
    if not str(path).startswith(str(kb_resolved)) or not path.is_file():
        raise HTTPException(404, "File not found")

    raw = path.read_text(encoding="utf-8")
    body = _kb_strip_frontmatter(raw)
    meta = next((e for e in entries if str(e.get("filename", "")).replace("\\", "/") == fn), {})

    try:
        import markdown as md_module

        try:
            html = md_module.markdown(
                body,
                extensions=[
                    "markdown.extensions.tables",
                    "markdown.extensions.fenced_code",
                    "markdown.extensions.nl2br",
                ],
            )
        except Exception:
            # 个别正文触发扩展异常时降级，避免 500
            html = (
                '<pre class="kb-detail-html whitespace-pre-wrap break-words">'
                f"{html_stdlib.escape(body)}</pre>"
            )
    except ImportError:
        # 未 pip install markdown 时避免 500，降级为转义纯文本（表格等不渲染）
        html = (
            '<pre class="kb-detail-html whitespace-pre-wrap break-words">'
            f"{html_stdlib.escape(body)}</pre>"
        )

    html = re.sub(r"(?i)<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)

    return {
        "filename": fn,
        "title": meta.get("title", ""),
        "category": meta.get("category", ""),
        "tags": meta.get("tags", []) or [],
        "summary": meta.get("summary", ""),
        "html": html,
    }


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    try:
        await ws_handler(ws)
    except WebSocketDisconnect:
        pass


# ── 静态文件服务（生产环境下前端 dist） ──────────────────────
_web_dist = Path(__file__).resolve().parent.parent.parent / "hagoku_web" / "dist"
if _web_dist.exists():
    app.mount("/", StaticFiles(directory=str(_web_dist), html=True), name="static")
else:
    @app.get("/")
    async def root():
        return {
            "message": "HaGoKu Studio API running",
            "docs": "/docs",
            "hint": "Frontend not built. Run `cd hagoku_web && npm run build` then restart server."
        }


def main():
    """Entry point: hagoku-api"""
    import uvicorn

    from hagoku.api.ws_handler import set_orchestrator
    from hagoku.config import HaGoKuConfig
    from hagoku.manager.orchestrator import Orchestrator

    # 预初始化 Orchestrator（注册 EventBus 到 WS Handler）
    # 确保前端连接时已订阅事件总线
    config = HaGoKuConfig.load()
    orchestrator = Orchestrator(config)
    set_orchestrator(orchestrator)

    uvicorn.run(
        "hagoku.api.server:app",
        host="0.0.0.0",
        port=8000,
        reload=os.environ.get("HAGOKU_API_RELOAD", "").strip().lower() in ("1", "true", "yes"),
    )


if __name__ == "__main__":
    main()
