"""WebSocket handler — bridges Orchestrator event bus to frontend"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

from fastapi import WebSocket

from hagoku.observability.event_bus import EventBus
from hagoku.observability.events import Event

if TYPE_CHECKING:
    from hagoku.manager.orchestrator import Orchestrator

logger = logging.getLogger(__name__)


# ── Shared event-bus registry ─────────────────────────────────
# The Orchestrator (or test harness) calls set_bus() once.
# The WebSocket handler reads from this to subscribe.
_shared_bus: EventBus | None = None
_shared_orchestrator: "Orchestrator | None" = None


def set_bus(bus: EventBus) -> None:
    """Register the active orchestrator event bus."""
    global _shared_bus
    _shared_bus = bus


def get_bus() -> EventBus | None:
    return _shared_bus


def get_orchestrator() -> "Orchestrator | None":
    """Return the shared orchestrator instance."""
    return _shared_orchestrator


def set_orchestrator(orchestrator: "Orchestrator") -> None:
    """Set the shared orchestrator instance and register its EventBus."""
    global _shared_orchestrator
    _shared_orchestrator = orchestrator
    set_bus(orchestrator.event_bus)


# ── Serialization ─────────────────────────────────────────────

def _event_to_message(event: Event) -> dict[str, Any]:
    return {
        "type": "event",
        "data": event.to_dict(),
    }


# ── Analysis runner ─────────────────────────────────────────────

def _run_analysis(data_path: str, query: str, project_name: str, phase: str) -> None:
    """
    在后台线程运行 Orchestrator.run()。
    Orchestrator 会自动通过其 event_bus → WSBridge → WebSocket 推送事件到前端。
    """
    from hagoku.config import HaGoKuConfig
    from hagoku.manager.orchestrator import Orchestrator

    global _shared_orchestrator

    # 创建或复用共享的 Orchestrator 实例
    if _shared_orchestrator is None:
        config = HaGoKuConfig.load()
        _shared_orchestrator = Orchestrator(config)
        set_bus(_shared_orchestrator.event_bus)
        # 订阅 WSBridge（uvicorn reload 子进程中 main() 未执行时的兜底）
        bridge = WSBridge.get()
        _shared_orchestrator.event_bus.subscribe(bridge.on_event)

    # 运行分析（同步阻塞，在 executor 线程中执行）
    _shared_orchestrator.run(
        data_path=data_path,
        query=query,
        project_name=project_name,
        phase=phase,
    )


# ── WS ↔ EventBus bridge ──────────────────────────────────────

class WSBridge:
    """Broadcasts events to all connected WebSocket clients."""

    _instance: WSBridge | None = None

    def __init__(self):
        self._clients: dict[str, WebSocket] = {}  # keyed by id()
        self._loop: asyncio.AbstractEventLoop | None = None

    @classmethod
    def get(cls) -> WSBridge:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Register the asyncio event loop. Call from async context (e.g. ws_handler)."""
        self._loop = loop

    def add_client(self, ws: WebSocket) -> str:
        key = str(id(ws))
        self._clients[key] = ws
        return key

    def remove_client(self, ws: WebSocket):
        self._clients.pop(str(id(ws)), None)

    async def broadcast(self, msg: dict):
        dead: list[str] = []
        for key, ws in list(self._clients.items()):
            try:
                await ws.send_json(msg)
            except Exception:
                dead.append(key)
        for key in dead:
            self._clients.pop(key, None)

    def on_event(self, event: Event):
        """Callback subscribed to EventBus, called from orchestrator thread."""
        loop = self._loop
        if loop is None or not loop.is_running():
            return
        payload = _event_to_message(event)
        asyncio.run_coroutine_threadsafe(self.broadcast(payload), loop)


async def ws_handler(ws: WebSocket) -> None:
    """WebSocket lifecycle handler."""
    bridge = WSBridge.get()
    bridge.add_client(ws)
    bridge.set_loop(asyncio.get_running_loop())  # 捕获正确的 event loop

    bus = get_bus()
    if bus is not None:
        bus.subscribe(bridge.on_event)

    try:
        await ws.send_json({"type": "welcome", "message": "HaGoKu connected", "version": "0.1.0"})

        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            cmd = msg.get("cmd", "")
            if cmd == "ping":
                await ws.send_json({"type": "pong"})
            elif cmd == "analyze":
                payload = msg.get("payload", {})
                data_path = payload.get("data_path", "")
                query = payload.get("query", "")
                project_name = payload.get("project_name", "default")
                phase = payload.get("phase", "full")

                if not data_path:
                    await ws.send_json({
                        "type": "error",
                        "cmd": "analyze",
                        "message": "Missing required field: data_path"
                    })
                    continue

                # 发送初始 ack
                await ws.send_json({
                    "type": "ack",
                    "cmd": "analyze",
                    "message": "Analysis started"
                })

                # 在后台线程运行分析（避免阻塞事件循环）
                try:
                    loop = asyncio.get_running_loop()
                    loop.run_in_executor(
                        None,
                        _run_analysis,
                        data_path,
                        query,
                        project_name,
                        phase,
                    )
                except RuntimeError:
                    # 没有运行中的事件循环，使用默认行为
                    pass
            elif cmd == "respond":
                # 用户回复 Agent 的暂停消息，解除分析线程阻塞
                payload = msg.get("payload", {})
                user_text = payload.get("text", payload.get("user_input", ""))
                orch = _shared_orchestrator
                if orch is None:
                    await ws.send_json({"type": "error", "message": "No active orchestrator"})
                elif not orch._is_paused:
                    await ws.send_json({"type": "error", "message": "No agent is waiting for input"})
                else:
                    try:
                        orch.unblock(str(user_text))
                        await ws.send_json({"type": "ack", "cmd": "respond", "message": "已收到回复，继续分析…"})
                    except Exception as e:
                        await ws.send_json({"type": "error", "message": str(e)})
            else:
                await ws.send_json({"type": "error", "message": f"Unknown command: {cmd}"})

    except Exception:
        logger.info("WebSocket closed", exc_info=True)
    finally:
        if bus is not None:
            try:
                bus.unsubscribe(bridge.on_event)
            except Exception:
                pass
        bridge.remove_client(ws)
