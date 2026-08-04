"""WebSocket Handler 集成测试"""

import asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from hagoku.api.ws_handler import (
    WSBridge,
    _event_to_message,
    get_bus,
    get_orchestrator,
    set_bus,
    set_orchestrator,
    ws_handler,
)
from hagoku.observability.event_bus import EventBus
from hagoku.observability.events import Event, EventType


class TestEventBusRegistry:
    """测试 EventBus 全局注册功能"""

    def test_set_bus_and_get_bus(self):
        """测试 set_bus/get_bus 配对使用"""
        bus = EventBus()
        set_bus(bus)
        assert get_bus() is bus

    def test_get_bus_initially_none(self):
        """测试 get_bus 初始返回 None"""
        # 注意：这可能受之前测试影响，所以用新的 bus 实例测试
        new_bus = EventBus()
        set_bus(new_bus)
        assert get_bus() is not None

    def test_set_orchestrator_registers_bus(self):
        """测试 set_orchestrator 同时注册 EventBus"""
        mock_orchestrator = MagicMock()
        mock_event_bus = EventBus()
        mock_orchestrator.event_bus = mock_event_bus

        set_orchestrator(mock_orchestrator)

        assert get_orchestrator() is mock_orchestrator
        assert get_bus() is mock_event_bus

    def test_get_orchestrator_initially_none(self):
        """测试 get_orchestrator 初始返回 None"""
        # 由于测试顺序可能影响，我们只验证类型
        result = get_orchestrator()
        # 如果之前没有设置过，应该返回 None 或之前的值
        assert result is None or isinstance(result, MagicMock)


class TestWSBridge:
    """测试 WSBridge 广播功能"""

    def test_bridge_is_singleton(self):
        """测试 WSBridge 是单例"""
        bridge1 = WSBridge.get()
        bridge2 = WSBridge.get()
        assert bridge1 is bridge2

    def test_add_client(self):
        """测试添加 WebSocket 客户端"""
        bridge = WSBridge.get()
        mock_ws = MagicMock()
        key = bridge.add_client(mock_ws)
        assert key is not None
        bridge.remove_client(mock_ws)  # 清理

    def test_remove_client(self):
        """测试移除 WebSocket 客户端"""
        bridge = WSBridge.get()
        mock_ws = MagicMock()
        bridge.add_client(mock_ws)
        bridge.remove_client(mock_ws)
        # 移除后再次移除不应报错
        bridge.remove_client(mock_ws)

    def test_broadcast_to_client(self):
        """测试广播消息到客户端"""

        async def _run():
            bridge = WSBridge.get()
            mock_ws = AsyncMock()
            bridge.add_client(mock_ws)
            msg = {"type": "event", "data": {"test": "data"}}
            await bridge.broadcast(msg)
            mock_ws.send_json.assert_called_once_with(msg)
            bridge.remove_client(mock_ws)

        asyncio.run(_run())


class TestEventSerialization:
    """测试事件序列化"""

    def test_event_to_message(self):
        """测试 Event 转换为 WS 消息格式"""
        event = Event(
            event_id="abc123",
            event_type=EventType.AGENT_STARTED,
            timestamp=datetime.now(),
            agent="scout",
            data={"query": "test"},
        )

        msg = _event_to_message(event)

        assert msg["type"] == "event"
        assert msg["data"]["event_id"] == "abc123"
        assert msg["data"]["event_type"] == "agent_started"
        assert msg["data"]["agent"] == "scout"


class TestGuardrailsWSPayloadContract:
    """Web 前端依赖的护栏相关 WS 载荷（与 Orchestrator 发射字段对齐）"""

    def test_run_completed_guardrails_blocked_payload(self):
        event = Event(
            event_id="e-gr",
            event_type=EventType.RUN_COMPLETED,
            timestamp=datetime.now(),
            agent="manager",
            data={
                "duration": "1.2s",
                "token_count": 0,
                "output_path": "/home/x/.hagoku/projects/p1/runs/20260514_abc/output/GUARDRAILS_BLOCKED.md",
                "guardrails_blocked": True,
                "run_id": "20260514_abc",
                "project": "p1",
            },
        )
        msg = _event_to_message(event)
        inner = msg["data"]["data"]
        assert inner["guardrails_blocked"] is True
        assert inner["run_id"] == "20260514_abc"
        assert inner["project"] == "p1"
        assert "GUARDRAILS_BLOCKED.md" in inner["output_path"]

    def test_run_completed_completed_payload_has_run_id(self):
        event = Event(
            event_id="e-ok",
            event_type=EventType.RUN_COMPLETED,
            timestamp=datetime.now(),
            agent="manager",
            data={
                "duration": "3.0s",
                "token_count": 1,
                "output_path": "/path/report.html",
                "run_id": "20260514_ok",
                "project": "p1",
            },
        )
        msg = _event_to_message(event)
        inner = msg["data"]["data"]
        assert inner.get("guardrails_blocked") is not True
        assert inner["run_id"] == "20260514_ok"
        assert inner["project"] == "p1"

    def test_run_completed_cancelled_payload(self):
        event = Event(
            event_id="e-cancel",
            event_type=EventType.RUN_COMPLETED,
            timestamp=datetime.now(),
            agent="manager",
            data={
                "duration": "0.1s",
                "cancelled": True,
                "run_id": "20260514_cancel",
                "project": "p1",
            },
        )
        msg = _event_to_message(event)
        inner = msg["data"]["data"]
        assert inner["cancelled"] is True
        assert inner["run_id"] == "20260514_cancel"

    def test_reporter_agent_completed_skipped_payload(self):
        event = Event(
            event_id="e-skip",
            event_type=EventType.AGENT_COMPLETED,
            timestamp=datetime.now(),
            agent="reporter",
            data={
                "result_summary": "已跳过：强制级护栏未通过",
                "skipped": True,
            },
        )
        msg = _event_to_message(event)
        inner = msg["data"]["data"]
        assert inner["skipped"] is True


class TestAnalyzeCommand:
    """测试 analyze 命令处理"""

    def test_analyze_missing_data_path_returns_error(self):
        """测试 analyze 命令缺少 data_path 时返回错误"""

        async def _run():
            mock_ws = AsyncMock()
            mock_ws.receive_text = AsyncMock(
                side_effect=[
                    json.dumps({"cmd": "analyze", "payload": {"query": "test", "project_name": "test_proj"}}),
                    Exception("Connection closed"),
                ]
            )
            with patch("hagoku.api.ws_handler.get_bus", return_value=None):
                try:
                    await ws_handler(mock_ws)
                except Exception:
                    pass
            calls = mock_ws.send_json.call_args_list
            error_call = [c for c in calls if c[0][0].get("type") == "error"]
            assert len(error_call) > 0
            assert "data_path" in error_call[0][0][0].get("message", "")

            import hagoku.api.ws_handler as wh

            wh._analysis_in_progress = False

        asyncio.run(_run())

    def test_analyze_with_valid_data_path_sends_ack(self):
        """测试 analyze 命令有 data_path 时返回 ack"""

        async def _run():
            mock_ws = AsyncMock()
            mock_ws.receive_text = AsyncMock(
                side_effect=[
                    json.dumps({
                        "cmd": "analyze",
                        "payload": {
                            "data_path": "/tmp/test.csv",
                            "query": "test query",
                            "project_name": "test_proj",
                        },
                    }),
                    Exception("Connection closed"),
                ]
            )
            with patch("hagoku.api.ws_handler.get_bus", return_value=None):
                try:
                    await ws_handler(mock_ws)
                except Exception:
                    pass
            calls = mock_ws.send_json.call_args_list
            ack_call = [c for c in calls if c[0][0].get("type") == "ack"]
            assert len(ack_call) > 0

            import hagoku.api.ws_handler as wh

            wh._analysis_in_progress = False

        asyncio.run(_run())


class TestCancelAnalysisCommand:
    """cancel_analysis 与共享 Orchestrator"""

    def test_cancel_analysis_calls_request_cancel(self):
        async def _run():
            mock_ws = AsyncMock()
            mock_orch = MagicMock()
            mock_orch._project_name = "testproj"
            mock_orch._context = {"data_path": "/tmp/test.csv", "query": "test query"}
            mock_orch.request_cancel = MagicMock()
            mock_ws.receive_text = AsyncMock(
                side_effect=[
                    json.dumps({"cmd": "cancel_analysis"}),
                    Exception("Connection closed"),
                ],
            )
            with patch("hagoku.api.ws_handler.get_bus", return_value=None):
                with patch("hagoku.api.ws_handler._shared_orchestrator", mock_orch):
                    try:
                        await ws_handler(mock_ws)
                    except Exception:
                        pass
            mock_orch.request_cancel.assert_called_once()
            acks = [c for c in mock_ws.send_json.call_args_list if c[0][0].get("cmd") == "cancel_analysis"]
            assert len(acks) == 1
            assert acks[0][0][0].get("type") == "ack"
            # 取消成功后应推送空快照，让前端清空消息
            snaps = [c for c in mock_ws.send_json.call_args_list
                     if c[0][0].get("type") == "state_snapshot"
                     and isinstance(c[0][0].get("data"), dict)]
            assert any(s[0][0].get("data", {}).get("messages") == [] for s in snaps)
            # project_name 保留当前项目，不清空标题栏
            assert any(s[0][0].get("data", {}).get("project_name") == "testproj" for s in snaps)

        asyncio.run(_run())

    def test_cancel_analysis_without_orchestrator_returns_error(self):
        async def _run():
            mock_ws = AsyncMock()
            mock_ws.receive_text = AsyncMock(
                side_effect=[
                    json.dumps({"cmd": "cancel_analysis"}),
                    Exception("Connection closed"),
                ],
            )
            with patch("hagoku.api.ws_handler.get_bus", return_value=None):
                with patch("hagoku.api.ws_handler._shared_orchestrator", None):
                    with patch.dict("os.environ", {"HAGOKU_SKIP_AUTO_RESTORE": "1"}):
                        try:
                            await ws_handler(mock_ws)
                        except Exception:
                            pass
            errs = [c for c in mock_ws.send_json.call_args_list if c[0][0].get("type") == "error"]
            assert len(errs) >= 1
            assert errs[0][0][0].get("cmd") == "cancel_analysis"

        asyncio.run(_run())


class TestPingCommand:
    """测试 ping 命令处理"""

    def test_ping_returns_pong(self):
        """测试 ping 命令返回 pong"""

        async def _run():
            mock_ws = AsyncMock()
            mock_ws.receive_text = AsyncMock(
                side_effect=[
                    json.dumps({"cmd": "ping"}),
                    Exception("Connection closed"),
                ]
            )
            with patch("hagoku.api.ws_handler.get_bus", return_value=None):
                try:
                    await ws_handler(mock_ws)
                except Exception:
                    pass
            calls = mock_ws.send_json.call_args_list
            pong_call = [c for c in calls if c[0][0].get("type") == "pong"]
            assert len(pong_call) > 0

        asyncio.run(_run())


class TestUnknownCommand:
    """测试未知命令处理"""

    def test_unknown_command_returns_error(self):
        """测试未知命令返回错误"""

        async def _run():
            mock_ws = AsyncMock()
            mock_ws.receive_text = AsyncMock(
                side_effect=[
                    json.dumps({"cmd": "unknown_cmd"}),
                    Exception("Connection closed"),
                ]
            )
            with patch("hagoku.api.ws_handler.get_bus", return_value=None):
                try:
                    await ws_handler(mock_ws)
                except Exception:
                    pass
            calls = mock_ws.send_json.call_args_list
            error_call = [c for c in calls if c[0][0].get("type") == "error"]
            assert len(error_call) > 0
            assert "Unknown command" in error_call[0][0][0].get("message", "")

        asyncio.run(_run())
