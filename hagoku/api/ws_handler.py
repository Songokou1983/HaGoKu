"""WebSocket handler — bridges Orchestrator event bus to frontend"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import TYPE_CHECKING, Any

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

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

# FastAPI app reference（set by lifespan，替代 _project_manager 全局）
_fastapi_app: Any = None

# 同一进程内只允许一条分析线程占用共享 Orchestrator（避免并发 run()）
_analysis_busy_lock = threading.Lock()
_analysis_in_progress = False
_analysis_generation = 0  # 每次新分析+1，取消时+1，防止旧任务 finally 误清标志


def set_bus(bus: EventBus) -> None:
    """Register the active orchestrator event bus."""
    global _shared_bus
    _shared_bus = bus


def get_bus() -> EventBus | None:
    return _shared_bus


def get_orchestrator() -> "Orchestrator | None":
    """Return the shared orchestrator instance。优先从 App 获取。"""
    global _fastapi_app
    orch = None
    if _fastapi_app is not None:
        hagoku_app = getattr(_fastapi_app.state, 'hagoku_app', None)
        if hagoku_app is not None and hagoku_app.orch is not None:
            orch = hagoku_app.orch
    if orch is None:
        orch = _shared_orchestrator
    # 确保 WSBridge 已订阅（App 懒创建 or 切换后可能未订阅）
    if orch is not None:
        bridge = WSBridge.get()
        orch.event_bus.subscribe(bridge.on_event)
    return orch


def set_app(app: Any) -> None:
    """Register the FastAPI app（lifespan 调用）。"""
    global _fastapi_app
    _fastapi_app = app


def set_orchestrator(orchestrator: "Orchestrator") -> None:
    """Set the shared orchestrator instance and register its EventBus."""
    global _shared_orchestrator
    _shared_orchestrator = orchestrator
    set_bus(orchestrator.event_bus)
    # 确保 EventBus → WSBridge 订阅
    bridge = WSBridge.get()
    orchestrator.event_bus.subscribe(bridge.on_event)


# ── Serialization ─────────────────────────────────────────────

def _event_to_message(event: Event) -> dict[str, Any]:
    return {
        "type": "event",
        "data": event.to_dict(),
    }


# ── Analysis runner ─────────────────────────────────────────────

def _run_analysis_task(data_path: str, query: str, project_name: str, phase: str, generation: int, sheet_name: int | str = 0, aux_sheets: list[str] | None = None) -> None:
    """Executor 入口：保证无论成功失败都会释放 `_analysis_in_progress`。
    
    generation 参数用于防止已取消的旧任务在 finally 中误清标志。
    """
    global _analysis_in_progress, _analysis_generation
    try:
        orch = get_orchestrator()
        if orch is None:
            return
        # 确保 WSBridge 已订阅（App 懒创建时可能未订阅）
        bridge = WSBridge.get()
        orch.event_bus.subscribe(bridge.on_event)
        result = orch.run(
            data_path=data_path, query=query,
            project_name=project_name,
            sheet_name=sheet_name,
            aux_sheets=aux_sheets or [],
        )
        # run_scout_phase 完成后触发首次 LLM 交互
        if isinstance(result, dict) and result.get("status") == "scout_review":
            orch.respond({"text": ""})
    except Exception as e:
        # LLM 调用失败 → 广播错误给前端
        try:
            import asyncio as _asyncio
            bridge = WSBridge.get()
            loop = bridge._loop
            if loop and loop.is_running():
                _asyncio.run_coroutine_threadsafe(
                    bridge.broadcast({
                        "type": "error",
                        "cmd": "analyze",
                        "message": str(e),
                    }),
                    loop,
                )
        except Exception:
            logger.exception("分析错误广播失败")
    finally:
        with _analysis_busy_lock:
            if _analysis_generation == generation:
                _analysis_in_progress = False


def _respond_task(orch: "Orchestrator", user_text: str) -> dict[str, Any]:
    """Executor 入口：在后台线程调用 respond()，不阻塞事件循环。
    
    对标 _run_analysis_task——确保流式事件在 respond() 执行期间能
    通过 WSBridge → WebSocket 实时推送到前端。
    """
    return orch.respond({"text": user_text})




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
        """向所有 WS 客户端推送。"""
        if not self._clients:
            return
        pairs = list(self._clients.items())

        async def _send_one(key: str, ws: WebSocket) -> str | None:
            try:
                await ws.send_json(msg)
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

    def push_snapshot(self, snap: dict) -> None:
        """从非 asyncio 线程安全推送 state_snapshot 到所有客户端。"""
        import asyncio as _asyncio
        loop = self._loop
        if loop is None or not loop.is_running():
            logger.warning("push_snapshot DROPPED — loop not running")
            return
        _asyncio.run_coroutine_threadsafe(
            self.broadcast({"type": "state_snapshot", "data": snap}),
            loop,
        )

    def on_event(self, event: Event):
        """Callback subscribed to EventBus, called from orchestrator thread."""
        loop = self._loop
        if loop is None or not loop.is_running():
            logger.warning("on_event %s DROPPED — loop=%s running=%s",
                event.event_type.value, loop is not None, loop.is_running() if loop else "N/A")
            return
        logger.info("on_event %s → broadcasting to %d clients",
            event.event_type.value, len(self._clients))
        payload = _event_to_message(event)
        d = event.data or {}
        summary = {}
        if d.get("field_review"):
            fr = d["field_review"]
            summary["field_review"] = f"{fr.get('n_cols','?')}cols"
        if d.get("message"):
            summary["message"] = str(d["message"])[:80]
        logger.info("%s → %d clients %s", event.event_type.value, len(self._clients),
            str(summary) if summary else "")
        asyncio.run_coroutine_threadsafe(self.broadcast(payload), loop)


async def ws_handler(ws: WebSocket) -> None:
    """WebSocket lifecycle handler."""
    bridge = WSBridge.get()
    bridge.add_client(ws)
    bridge.set_loop(asyncio.get_running_loop())

    async def _safe_send(msg: dict) -> bool:
        """安全发送——WS 已关闭时静默跳过，不抛异常。"""
        try:
            await ws.send_json(msg)
            return True
        except RuntimeError as e:
            if "close message" in str(e).lower():
                return False
            raise

    # ── 获取 App 实例 ──
    app = ws.app.state.hagoku_app if hasattr(ws.app.state, 'hagoku_app') else None

    try:
        await _safe_send({"type": "welcome", "message": "HaGoKu Studio connected", "version": "2.3.1"})

        # ── 推送项目列表 ──
        if app:
            projects = app.list_projects()
            await _safe_send({"type": "project_list", "data": projects})

        # ── 状态恢复：优先从 App 恢复当前项目 ──
        global _shared_orchestrator
        orch = None
        if app and app.active_project:
            orch = app.orch
        if orch is None and app:
            restored = app.try_restore_session()
            if restored:
                orch = app.orch
        if orch is None and _shared_orchestrator is not None:
            orch = _shared_orchestrator
        if orch is not None:
            orch.event_bus.subscribe(bridge.on_event)

        # ── 推送当前项目快照 ──
        if orch is not None and app is not None:
            snapshot = app.build_snapshot()
            if snapshot:
                await _safe_send({"type": "state_snapshot", "data": snapshot})

        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await _safe_send({"type": "error", "message": "Invalid JSON"})
                continue

            import logging as _logging
            _wslog = _logging.getLogger("hagoku.ws.recv")
            cmd = msg.get("cmd", "")
            _wslog.info("%s %s", cmd, str({k: str(v)[:100] for k, v in msg.items() if k != 'cmd'})[:200])
            if cmd == "ping":
                await _safe_send({"type": "pong"})
            elif cmd == "__log":
                log_text = (msg.get("payload") or {}).get("text", "")
                from hagoku.config import HaGoKuConfig as _Cfg
                log_path = _Cfg.load().work_dir / "hagoku.log"
                with open(str(log_path), "a") as f:
                    f.write(log_text + "\n")
            elif cmd == "list_projects":
                if app:
                    projects = app.list_projects()
                    await _safe_send({"type": "project_list", "data": projects})
                else:
                    await _safe_send({"type": "error", "message": "App not initialized"})
            elif cmd == "switch_project":
                name = (msg.get("payload") or msg).get("project", "")
                if app is None:
                    await _safe_send({"type": "error", "message": "App not initialized"})
                elif app.is_busy():
                    await _safe_send({"type": "error", "message": "当前项目分析进行中，请等待完成或停止后再切换"})
                else:
                    old_orch = app.orch if app.active_project else None
                    snap = app.switch_project(name)
                    if snap:
                        # 切换 EventBus 订阅
                        if old_orch:
                            old_orch.event_bus.unsubscribe(bridge.on_event)
                        new_orch = app.orch
                        if new_orch:
                            new_orch.event_bus.subscribe(bridge.on_event)
                        await _safe_send({"type": "state_snapshot", "data": snap})
                    else:
                        await _safe_send({"type": "error", "message": f"项目 {name} 不存在或无法加载"})
            elif cmd == "create_project":
                name = (msg.get("payload") or msg).get("project", "")
                ok = app.create_project(name) if app else False
                await _safe_send({"type": "ack", "cmd": "create_project", "data": {"ok": ok}})
            elif cmd == "delete_project":
                name = (msg.get("payload") or msg).get("project", "")
                ok = app.delete_project(name) if app else False
                await _safe_send({"type": "ack", "cmd": "delete_project", "data": {"ok": ok}})
                if ok:
                    # 推送更新后的项目列表 + 空快照，让前端清空分析面板
                    projects = app.list_projects()
                    await _safe_send({"type": "project_list", "data": projects})
                    await _safe_send({"type": "state_snapshot", "data": {
                        "project_name": "", "messages": [], "gate_open": False,
                    }})
            elif cmd == "analyze":
                payload = msg.get("payload", {})
                # 清理整个 payload 中的 null 字节
                payload = {k: (v.replace('\x00', '') if isinstance(v, str) else v) for k, v in payload.items()}
                data_path = payload.get("data_path", "")
                sheet_name = payload.get("sheet_name", 0)
                aux_sheets = payload.get("aux_sheets", [])
                query = payload.get("query", "").strip()
                project_name = (payload.get("project_name") or "").strip()
                if not project_name:
                    await _safe_send({
                        "type": "error", "cmd": "analyze",
                        "message": "请先在项目页面创建或选择项目"
                    })
                    continue
                phase = payload.get("phase", "full")
                if phase in ("analyst_first", "cleaning_first"):
                    phase = "full"
                _logging.getLogger("hagoku.ws").warning(
                    "WS analyze 收到: query=%r project=%s phase=%s payload_keys=%s",
                    query, project_name, phase, list(payload.keys()),
                )

                if not data_path:
                    await _safe_send({
                        "type": "error",
                        "cmd": "analyze",
                        "message": "Missing required field: data_path"
                    })
                    continue

                global _analysis_in_progress, _analysis_generation
                with _analysis_busy_lock:
                    if _analysis_in_progress:
                        await _safe_send({
                            "type": "error",
                            "cmd": "analyze",
                            "message": "已有分析进行中，请等待结束或点击「重置分析」。",
                        })
                        continue
                    _analysis_in_progress = True
                    _analysis_generation += 1
                    gen = _analysis_generation

                # 发送初始 ack
                await _safe_send({
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
                        gen,
                        sheet_name,
                        aux_sheets,
                    )
                except RuntimeError:
                    with _analysis_busy_lock:
                        _analysis_in_progress = False
                    await _safe_send({
                        "type": "error",
                        "cmd": "analyze",
                        "message": "分析启动失败：事件循环异常，请刷新页面重试",
                    })
            elif cmd == "cancel_analysis":
                orch = get_orchestrator()
                if orch is None:
                    await _safe_send({
                        "type": "error",
                        "cmd": "cancel_analysis",
                        "message": "当前没有可取消的分析任务",
                    })
                else:
                    try:
                        orch.request_cancel()
                        # 清除分析上下文，避免旧数据污染新分析
                        ctx = getattr(orch, '_context', None)
                        if ctx:
                            ctx.pop("column_semantics", None)
                            ctx.pop("_report_html_path", None)
                        with _analysis_busy_lock:
                            _analysis_in_progress = False
                            _analysis_generation += 1  # 旧任务的 finally 不会再清除标志
                        await _safe_send({
                            "type": "ack",
                            "cmd": "cancel_analysis",
                            "message": "已中止分析",
                        })
                    except Exception as e:
                        await _safe_send({"type": "error", "message": str(e)})
            elif cmd == "cancel_respond":
                orch = get_orchestrator()
                if orch is not None:
                    orch.request_cancel_respond()
                await _safe_send({"type": "ack", "cmd": "cancel_respond"})
            elif cmd == "respond":
                payload = msg.get("payload", {})
                payload = {k: (v.replace('\x00', '') if isinstance(v, str) else v) for k, v in payload.items()}
                user_text = payload.get("text", "").strip()
                orch = get_orchestrator()
                if orch is None:
                    await _safe_send({"type": "error", "message": "No active orchestrator"})
                else:
                    # 立即确认收到，不阻塞 ws_handler 协程
                    # 否则 ping/pong 堆积在 TCP 缓冲区 → 超时断连
                    await _safe_send({"type": "ack", "cmd": "respond_received"})

                    # ── 用户输入先存 Session，再跑 LLM ──
                    if user_text:
                        ctx = getattr(orch, '_context', None) or {}
                        session = ctx.get("_session") if ctx else None
                        if session:
                            session.add("user", user_text)

                    async def _process():
                        try:
                            loop = asyncio.get_running_loop()
                            result = await loop.run_in_executor(
                                None, _respond_task, orch, user_text,
                            )
                            await _safe_send({"type": "ack", "cmd": "respond", "data": result})
                        except Exception as e:
                            await _safe_send({"type": "error", "message": str(e)})
                    asyncio.create_task(_process())
            else:
                await _safe_send({"type": "error", "message": f"Unknown command: {cmd}"})

    except WebSocketDisconnect as e:
        logger.info("WebSocket closed code=%s reason=%s", e.code, str(e.reason)[:80])
    except Exception:
        logger.info("WebSocket closed", exc_info=True)
    finally:
        bridge.remove_client(ws)
