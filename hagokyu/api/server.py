"""HaGoKu FastAPI server — REST + WebSocket"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from hagokyu.api.ws_handler import ws_handler

app = FastAPI(title="HaGoKu API", version="0.1.0")

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


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    try:
        await ws_handler(ws)
    except WebSocketDisconnect:
        pass


# ── 静态文件服务（生产环境下前端 dist） ──────────────────────
_web_dist = Path(__file__).resolve().parent.parent.parent / "hagokyu_web" / "dist"
if _web_dist.exists():
    app.mount("/", StaticFiles(directory=str(_web_dist), html=True), name="static")
else:
    @app.get("/")
    async def root():
        return {
            "message": "HaGoKu API running",
            "docs": "/docs",
            "hint": "Frontend not built. Run `cd hagokyu_web && npm run build` then restart server."
        }


def main():
    """Entry point: hagokyu-api"""
    import uvicorn

    from hagokyu.api.ws_handler import set_orchestrator
    from hagokyu.config import HaGoKuConfig
    from hagokyu.manager.orchestrator import Orchestrator

    # 预初始化 Orchestrator（注册 EventBus 到 WS Handler）
    # 确保前端连接时已订阅事件总线
    config = HaGoKuConfig.load()
    orchestrator = Orchestrator(config)
    set_orchestrator(orchestrator)

    uvicorn.run("hagokyu.api.server:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
