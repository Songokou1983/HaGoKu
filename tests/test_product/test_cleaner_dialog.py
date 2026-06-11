"""CL-2: 验证 Cleaner 对话化 — 首次评估展示 + 对话循环 + route_to"""
from unittest.mock import MagicMock, patch
import json as _json
import pandas as pd

from hagoku.config import HaGoKuConfig
from hagoku.manager.orchestrator import Orchestrator


def _setup_cleaner_context():
    return {
        "column_semantics": [
            {"column_name": "A", "display_name": "列A", "suggested_role": "target", "used_in_analysis": True},
        ],
        "query": "分析",
    }


class FakeCleanerAgent:
    """伪装 CleanerAgent 用于测试 _handle_cleaner_reply。"""
    def __init__(self):
        self.llm_config = None
        self.event_bus = None
        self.prompt = "test"
        self.run_step = MagicMock()

    def _load_cleaning_rules(self):
        return "test rules"

    def assess(self, df, context, rules):
        return {"summary": "评估完成", "columns": []}


def test_first_call_runs_assessment_and_opens_dialog():
    """首次进入 Cleaner → 运行评估 + 设置 _cleaner_dialog_open=True + 返回 cleaner_review"""
    orch = Orchestrator(HaGoKuConfig())
    orch._df_raw = pd.DataFrame({"A": [1, 2]})
    orch._df_clean = orch._df_raw
    context = _setup_cleaner_context()

    fake = FakeCleanerAgent()
    orch._agent = fake
    result = orch._handle_cleaner_reply("评估", context)

    assert result["status"] == "cleaner_review"
    assert orch._cleaner_dialog_open, "首次评估后应设置 _cleaner_dialog_open=True"
    assert context.get("_cleaner_assessment") is not None


def test_second_call_uses_dialog_mode():
    """第二次进入 Cleaner → 使用 run_step 对话模式（不重新评估）"""
    orch = Orchestrator(HaGoKuConfig())
    orch._df_raw = pd.DataFrame({"A": [1, 2]})
    orch._df_clean = orch._df_raw
    context = _setup_cleaner_context()
    context["_cleaner_assessment"] = {"summary": "已有评估", "columns": []}

    fake = FakeCleanerAgent()
    orch._agent = fake
    orch._cleaner_messages = [{"role": "user", "content": "你好"}]
    orch._cleaner_dialog_open = True

    fake.run_step.return_value = {
        "messages": orch._cleaner_messages + [{"role": "assistant", "content": "收到"}],
        "text": "收到",
        "submit_assessment": False,
        "assessment": None,
        "route_to": None,
    }

    result = orch._handle_cleaner_reply("换个方案", context)

    fake.run_step.assert_called_once()
    assert result["status"] == "cleaner_review"


def test_cleaner_route_to_analyst():
    """LLM 调 route_to(stage="analyst") → switch"""
    orch = Orchestrator(HaGoKuConfig())
    orch._df_raw = pd.DataFrame({"A": [1, 2]})
    orch._df_clean = orch._df_raw
    context = _setup_cleaner_context()
    context["_cleaner_assessment"] = {"summary": "done", "columns": []}

    fake = FakeCleanerAgent()
    orch._agent = fake
    orch._cleaner_messages = [{"role": "user", "content": "可以了"}]
    orch._cleaner_dialog_open = True

    fake.run_step.return_value = {
        "messages": orch._cleaner_messages,
        "text": "好的",
        "submit_assessment": False,
        "assessment": None,
        "route_to": {"stage": "analyst", "reason": "清洗完成"},
    }

    result = orch._handle_cleaner_reply("可以了", context)
    assert isinstance(result, tuple)
    assert result[0] == "switch"
    assert result[1] == "analyst"


def test_cleaner_confirmation_text_no_longer_triggers_switch():
    """Phase C: 用户说"确认"但无 route_to → 留在 cleaner（不再硬编码切 analyst）。"""
    orch = Orchestrator(HaGoKuConfig())
    orch._df_raw = pd.DataFrame({"A": [1, 2]})
    orch._df_clean = orch._df_raw
    context = _setup_cleaner_context()
    context["_cleaner_assessment"] = {"summary": "done", "columns": []}

    fake = FakeCleanerAgent()
    orch._agent = fake
    orch._cleaner_dialog_open = True

    fake.run_step.return_value = {
        "text": "ok",
        "submit_assessment": False,
        "assessment": None,
        "route_to": None,
    }

    result = orch._handle_cleaner_reply("确认", context)
    # Phase C: 留在 cleaner，不再自动切 analyst
    assert isinstance(result, dict)
    assert result["status"] == "cleaner_review"
