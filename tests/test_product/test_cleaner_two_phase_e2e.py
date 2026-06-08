"""CL-5: Cleaner 对话化端到端冒烟 — 评估→对话→route_to 全链路"""
from unittest.mock import MagicMock, patch
import pandas as pd

from hagoku.config import HaGoKuConfig
from hagoku.manager.orchestrator import Orchestrator


class FakeCleanerAgent:
    """伪装 CleanerAgent，可控制 assess + run_step 行为。"""
    def __init__(self):
        self.llm_config = None
        self.event_bus = None
        self.prompt = "test"
        self.run_step = MagicMock()

    def _load_cleaning_rules(self):
        return "test rules"

    def assess(self, df, context, rules):
        return {"summary": "评估完成", "columns": [
            {"column": "A", "action": "keep", "assessment": "OK"},
            {"column": "B", "action": "winsorize", "assessment": "有极端值"},
        ]}


def test_cleaner_full_flow():
    """完整剧本：首次评估→用户接受→route_to(analyst)"""
    orch = Orchestrator(HaGoKuConfig())
    orch._df_raw = pd.DataFrame({"A": [1, 2], "B": [3, 999]})
    orch._df_clean = orch._df_raw
    context = {
        "column_semantics": [
            {"column_name": "A", "display_name": "列A", "suggested_role": "target", "used_in_analysis": True},
            {"column_name": "B", "display_name": "列B", "suggested_role": "feature", "used_in_analysis": True},
        ],
        "query": "分析",
    }

    fake = FakeCleanerAgent()

    with patch("hagoku.agents.cleaner.CleanerAgent", return_value=fake):
        # Step 1: 首次进入 → 评估
        result1 = orch._handle_cleaner_reply("评估", context)
        assert result1["status"] == "cleaner_review"
        assert orch._cleaner_dialog_open
        assert context.get("_cleaner_assessment") is not None

    # Mock route_to 行为
    orch._cleaner_agent = fake
    orch._cleaner_messages = [{"role": "user", "content": "可以了"}]
    fake.run_step.return_value = {
        "messages": orch._cleaner_messages + [{"role": "assistant", "content": "好的"}],
        "text": "好的",
        "submit_assessment": False,
        "assessment": None,
        "route_to": {"stage": "analyst", "reason": "清洗完成"},
    }

    # Step 2: 用户"可以了" → route_to(analyst)
    result2 = orch._handle_cleaner_reply("可以了", context)
    assert isinstance(result2, tuple)
    assert result2[0] == "switch"
    assert result2[1] == "analyst"


def test_cleaner_user_challenges():
    """用户挑战清洗方案 → LLM 回应 + 留在 cleaner"""
    orch = Orchestrator(HaGoKuConfig())
    orch._df_raw = pd.DataFrame({"A": [1, 2], "B": [3, 999]})
    orch._df_clean = orch._df_raw
    context = {
        "column_semantics": [
            {"column_name": "B", "display_name": "列B", "suggested_role": "feature", "used_in_analysis": True},
        ],
        "query": "分析",
        "_cleaner_assessment": {"summary": "done", "columns": []},
    }

    fake = FakeCleanerAgent()
    orch._cleaner_agent = fake
    orch._cleaner_messages = [{"role": "user", "content": "B列不应该洗"}]
    orch._cleaner_dialog_open = True

    fake.run_step.return_value = {
        "messages": orch._cleaner_messages + [{"role": "assistant", "content": "理解，B列有极端值但可能是有意义的业务数据"}],
        "text": "理解，B列有极端值但可能是有意义的业务数据，建议保留",
        "submit_assessment": False,
        "assessment": None,
        "route_to": None,
    }

    result = orch._handle_cleaner_reply("B列不应该洗，那是有意义的大单", context)
    assert not isinstance(result, tuple)
    assert result["status"] == "cleaner_review"


def test_cleaner_route_to_scout():
    """用户要求重看字段 → route_to(scout)"""
    orch = Orchestrator(HaGoKuConfig())
    orch._df_raw = pd.DataFrame({"A": [1, 2]})
    orch._df_clean = orch._df_raw
    context = {
        "column_semantics": [
            {"column_name": "A", "display_name": "列A", "suggested_role": "target", "used_in_analysis": True},
        ],
        "query": "分析",
        "_cleaner_assessment": {"summary": "done", "columns": []},
    }

    fake = FakeCleanerAgent()
    orch._cleaner_agent = fake
    orch._cleaner_messages = [{"role": "user", "content": "字段理解有问题"}]
    orch._cleaner_dialog_open = True

    fake.run_step.return_value = {
        "messages": orch._cleaner_messages,
        "text": "好的",
        "submit_assessment": False,
        "assessment": None,
        "route_to": {"stage": "scout", "reason": "字段理解有误"},
    }

    result = orch._handle_cleaner_reply("字段理解有问题，回去重看", context)
    assert isinstance(result, tuple)
    assert result[0] == "switch"
    assert result[1] == "scout"
