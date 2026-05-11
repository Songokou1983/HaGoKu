"""HaGoKu FastAPI server — REST + WebSocket"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
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


app = FastAPI(title="HaGoKu API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


# ── 项目目录约定（与 Orchestrator 保持一致）──────────────────
def _projects_root() -> Path:
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


@app.post("/api/projects")
async def create_project(req: CreateProjectRequest):
    name = req.name.strip()
    if not name or "/" in name:
        raise HTTPException(400, "Invalid project name")
    proj_dir = _projects_root() / name
    proj_dir.mkdir(parents=True, exist_ok=True)
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


# ── GET /api/reports/{project_name}/{run_id}/{filename} — 返回 run 子目录报告 ──
@app.get("/api/reports/{project_name}/{run_id}/{filename}")
async def get_report_run(project_name: str, run_id: str, filename: str):
    if not filename.endswith(".html") or "/" in filename:
        raise HTTPException(400, "Invalid filename")
    path = _projects_root() / project_name / "runs" / run_id / "output" / filename
    if not path.exists():
        raise HTTPException(404, "Report not found")
    return HTMLResponse(path.read_text(encoding="utf-8"))


# ── GET /api/reports/{project_name}/{filename} — 兼容旧路径 ──
@app.get("/api/reports/{project_name}/{filename}")
async def get_report(project_name: str, filename: str):
    if not filename.endswith(".html") or "/" in filename:
        raise HTTPException(400, "Invalid filename")
    path = _projects_root() / project_name / "output" / filename
    if not path.exists():
        raise HTTPException(404, "Report not found")
    return HTMLResponse(path.read_text(encoding="utf-8"))


# ── GET /api/config — 读取当前前端可见配置 ───────────────────
@app.get("/api/config")
async def get_config():
    from hagoku.config import HaGoKuConfig
    try:
        cfg = HaGoKuConfig.load()
        return {
            "base_url": cfg.llm.base_url or "",
            "model": cfg.llm.model or "",
            "workspace": str(_projects_root()),
        }
    except Exception:
        return {"base_url": "", "model": "", "workspace": str(_projects_root())}


# ── GET /api/knowledge/{project_name} — 列出项目知识库文件 ──
@app.get("/api/knowledge/{project_name}")
async def list_knowledge(project_name: str):
    kb_dir = _projects_root() / project_name / "kb"
    if not kb_dir.exists():
        return {"entries": []}
    files = [f.stem for f in kb_dir.glob("*.md")]
    return {"entries": files}


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
            "message": "HaGoKu API running",
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

    uvicorn.run("hagoku.api.server:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
