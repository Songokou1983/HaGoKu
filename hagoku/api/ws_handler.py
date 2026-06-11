"""WebSocket handler — bridges Orchestrator event bus to frontend"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
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

# 同一进程内只允许一条分析线程占用共享 Orchestrator（避免并发 run()）
_analysis_busy_lock = threading.Lock()
_analysis_in_progress = False


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
    # lifespan / main 会先于首次 analyze 创建 Orchestrator；须在此挂上 WSBridge，
    # 否则 _run_analysis 因「实例已存在」跳过 subscribe，前端收不到任何事件。
    bridge = WSBridge.get()
    orchestrator.event_bus.subscribe(bridge.on_event)


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

    # 无论实例是本函数新建还是 lifespan 已创建，都保证 EventBus → WSBridge（subscribe 幂等）
    bridge = WSBridge.get()
    _shared_orchestrator.event_bus.subscribe(bridge.on_event)

    # 运行分析（同步阻塞，在 executor 线程中执行）
    _shared_orchestrator.run(
        data_path=data_path,
        query=query,
        project_name=project_name,
        phase=phase,
    )


def _run_analysis_task(data_path: str, query: str, project_name: str, phase: str) -> None:
    """Executor 入口：保证无论成功失败都会释放 `_analysis_in_progress`。"""
    global _analysis_in_progress
    try:
        result = _shared_orchestrator.run(
            data_path=data_path, query=query,
            project_name=project_name,
        )
        # run() 截断在 Scout → 自动调一次 respond 启动事件循环
        if isinstance(result, dict) and result.get("status") == "scout_review":
            _shared_orchestrator.respond({"text": ""})
    finally:
        with _analysis_busy_lock:
            _analysis_in_progress = False


def _build_state_snapshot(orch: "Orchestrator") -> dict[str, Any] | None:
    """从 Orchestrator 当前状态构建前端可恢复的快照。

    用于 WebSocket 重连时恢复 UI 状态：当前阶段、字段表、对话等。
    """
    from hagoku.manager.payloads.scout_payload import scout_field_review_pause_payload
    try:
        stage = getattr(orch, '_stage', '') or ''
        ctx = getattr(orch, '_context', None) or {}
        snapshot: dict[str, Any] = {
            "stage": stage,
            "project_name": getattr(orch, '_project_name', '') or (
                ctx.get('data_path', '').split('/')[-2] if ctx.get('data_path') else ''
            ),
            "query": ctx.get('query', ''),
            "data_path": ctx.get('data_path', ''),
        }
        # Scout 阶段：发字段核对表
        if stage == "scout" and ctx:
            try:
                field_review = scout_field_review_pause_payload(ctx)
                snapshot["field_review"] = field_review.get("field_review")
            except Exception:
                pass
        # Phase C: pending_ask_user（LLM ask_user 暂停状态恢复）
        ask = ctx.get("_pending_ask_user")
        if ask:
            snapshot["pending_ask_user"] = ask

        # Cleaner 阶段
        if stage == "cleaner" and ctx:
            try:
                from hagoku.manager.payloads.cleaner_payload import cleaning_review_pause_payload
                cleaner_review = cleaning_review_pause_payload(ctx)
                snapshot["cleaning_review"] = cleaner_review
            except Exception:
                pass
        # Analyst 阶段：传最后一条 LLM 回复
        if stage == "analyst" and ctx:
            snapshot["analyst_message"] = ctx.get("_last_llm_reply", "")
        return snapshot
    except Exception:
        return None


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
        """向所有 WS 客户端推送；单客户端慢/死连接不得阻塞整条事件循环（否则 HTTP 也会卡死）。"""
        if not self._clients:
            return
        pairs = list(self._clients.items())
        timeout = float(os.environ.get("HAGOKU_WS_SEND_TIMEOUT", "5"))

        async def _send_one(key: str, ws: WebSocket) -> str | None:
            try:
                await asyncio.wait_for(ws.send_json(msg), timeout=timeout)
                return None
            except Exception:
                return key

        results = await asyncio.gather(
            *(_send_one(k, w) for k, w in pairs),
            return_exceptions=True,
        )
        for r in results:
            if isinstance(r, str) and r:
                self._clients.pop(r, None)

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

    # EventBus → WSBridge 仅在创建共享 Orchestrator 时订阅一次（见 _run_analysis）。
    # 切勿在每个 WebSocket 连接上再次 subscribe(bridge.on_event)，否则同一回调在
    # subscribers 中出现多条，一次 emit 会多次 broadcast，前端进度文案会成对重复。

    try:
        await ws.send_json({"type": "welcome", "message": "HaGoKu Studio connected", "version": "0.1.0"})

        # ── 重连状态恢复：推送当前 pipeline 快照 ──
        orch = _shared_orchestrator
        if orch is not None:
            stage = getattr(orch, '_stage', '') or ''
            if stage:  # pipeline 正在某个阶段（包括暂停等用户输入）
                snapshot = _build_state_snapshot(orch)
                if snapshot:
                    await ws.send_json({"type": "state_snapshot", "data": snapshot})

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
                # 清理整个 payload 中的 null 字节
                payload = {k: (v.replace('\x00', '') if isinstance(v, str) else v) for k, v in payload.items()}
                data_path = payload.get("data_path", "")
                query = payload.get("query", "").strip()
                project_name = payload.get("project_name", "default")
                phase = payload.get("phase", "full")
                if phase in ("analyst_first", "cleaning_first"):
                    phase = "full"
                import logging
                logging.getLogger("hagoku.ws").warning(
                    "WS analyze 收到: query=%r project=%s phase=%s payload_keys=%s",
                    query, project_name, phase, list(payload.keys()),
                )

                if not data_path:
                    await ws.send_json({
                        "type": "error",
                        "cmd": "analyze",
                        "message": "Missing required field: data_path"
                    })
                    continue

                global _analysis_in_progress
                with _analysis_busy_lock:
                    if _analysis_in_progress:
                        await ws.send_json({
                            "type": "error",
                            "cmd": "analyze",
                            "message": "已有分析进行中，请等待结束或点击「重置分析」。",
                        })
                        continue
                    _analysis_in_progress = True

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
                        _run_analysis_task,
                        data_path,
                        query,
                        project_name,
                        phase,
                    )
                except RuntimeError:
                    with _analysis_busy_lock:
                        _analysis_in_progress = False
            elif cmd == "cancel_analysis":
                orch = _shared_orchestrator
                if orch is None:
                    await ws.send_json({
                        "type": "error",
                        "cmd": "cancel_analysis",
                        "message": "当前没有可取消的分析任务",
                    })
                else:
                    try:
                        orch.request_cancel()
                        await ws.send_json({
                            "type": "ack",
                            "cmd": "cancel_analysis",
                            "message": "已请求中止分析",
                        })
                    except Exception as e:
                        await ws.send_json({"type": "error", "message": str(e)})
            elif cmd == "respond":
                payload = msg.get("payload", {})
                payload = {k: (v.replace('\x00', '') if isinstance(v, str) else v) for k, v in payload.items()}
                user_text = payload.get("text", "").strip()
                # Phase C: 空 text 是合法信号（"让 LLM 再想想"），不再 skip
                # R6 防护：连续 3 次空回复 → emit error（不兜底，显式失败，铁律 7）
                orch = _shared_orchestrator
                if orch is None:
                    await ws.send_json({"type": "error", "message": "No active orchestrator"})
                else:
                    try:
                        result = orch.respond({"text": user_text, "stage": getattr(orch, '_stage', '')})
                        await ws.send_json({"type": "ack", "cmd": "respond", "data": result})
                    except Exception as e:
                        await ws.send_json({"type": "error", "message": str(e)})
            else:
                await ws.send_json({"type": "error", "message": f"Unknown command: {cmd}"})

    except Exception:
        logger.info("WebSocket closed", exc_info=True)
    finally:
        bridge.remove_client(ws)
