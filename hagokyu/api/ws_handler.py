"""WebSocket handler — bridges Orchestrator event bus to frontend"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket

from hagokyu.observability.event_bus import EventBus
from hagokyu.observability.events import Event

logger = logging.getLogger(__name__)


# ── Shared event-bus registry ─────────────────────────────────
# The Orchestrator (or test harness) calls set_bus() once.
# The WebSocket handler reads from this to subscribe.
_shared_bus: EventBus | None = None


def set_bus(bus: EventBus) -> None:
    """Register the active orchestrator event bus."""
    global _shared_bus
    _shared_bus = bus


def get_bus() -> EventBus | None:
    return _shared_bus


# ── Serialization ─────────────────────────────────────────────

def _event_to_message(event: Event) -> dict[str, Any]:
    return {
        "type": "event",
        "data": event.to_dict(),
    }


# ── WS ↔ EventBus bridge ──────────────────────────────────────

class WSBridge:
    """Broadcasts events to all connected WebSocket clients."""

    _instance: WSBridge | None = None

    def __init__(self):
        self._clients: dict[str, WebSocket] = {}  # keyed by id()

    @classmethod
    def get(cls) -> WSBridge:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

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
        payload = _event_to_message(event)
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            return
        asyncio.run_coroutine_threadsafe(self.broadcast(payload), loop)


async def ws_handler(ws: WebSocket) -> None:
    """WebSocket lifecycle handler."""
    bridge = WSBridge.get()
    bridge.add_client(ws)

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
                await ws.send_json({
                    "type": "ack",
                    "cmd": "analyze",
                    "message": "Analysis request received (placeholder)"
                })
            else:
                await ws.send_json({"type": "error", "message": f"Unknown command: {cmd}"})

    except Exception:
        logger.debug("WebSocket closed", exc_info=True)
    finally:
        if bus is not None:
            try:
                bus.unsubscribe(bridge.on_event)
            except Exception:
                pass
        bridge.remove_client(ws)