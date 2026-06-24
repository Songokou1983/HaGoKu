"""CL-5: Cleaner 纯通道端到端冒烟（Phase D 扁平化）

_handle_cleaner_reply 现为存根，直接 delegate 到 _handle_reply。
"""
from unittest.mock import MagicMock, patch
import pandas as pd

from hagoku.config import HaGoKuConfig
from hagoku.manager.orchestrator import Orchestrator


class FakeCleanerAgent:
    """伪装 CleanerAgent，可控制 run_step 行为。"""
    def __init__(self):
        self.llm_config = None
        self.event_bus = None
        self.prompt = "test"
        self.run_step = MagicMock()

    def _load_cleaning_rules(self):
        return "test rules"

    def assess(self, df, context):
        return {"summary": "评估完成", "columns": [
            {"column": "A", "action": "keep", "assessment": "OK"},
            {"column": "B", "action": "winsorize", "assessment": "有极端值"},
        ]}


def test_cleaner_full_flow():
    """纯通道剧本：_handle_cleaner_reply 返回 scout_review。"""
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
    orch._agent = fake
    fake.run_step.return_value = {
        "text": "好的",
        "submit_assessment": False,
        "assessment": None,
        "route_to": {"stage": "analyst", "reason": "清洗完成"},
    }

    result = orch._handle_cleaner_reply("可以了", context)
    assert isinstance(result, dict)
    assert result["status"] == "scout_review"


def test_cleaner_user_challenges():
    """用户挑战清洗方案 → LLM 回应 + 留在当前"""
    orch = Orchestrator(HaGoKuConfig())
    orch._df_raw = pd.DataFrame({"A": [1, 2], "B": [3, 999]})
    orch._df_clean = orch._df_raw
    context = {
        "column_semantics": [
            {"column_name": "B", "display_name": "列B", "suggested_role": "feature", "used_in_analysis": True},
        ],
        "query": "分析",
    }

    fake = FakeCleanerAgent()
    orch._agent = fake
    fake.run_step.return_value = {
        "text": "理解，B列有极端值但可能是有意义的业务数据，建议保留",
        "submit_assessment": False,
        "assessment": None,
        "route_to": None,
    }

    result = orch._handle_cleaner_reply("B列不应该洗，那是有意义的大单", context)
    assert not isinstance(result, tuple)
    assert result["status"] == "scout_review"


def test_cleaner_route_to_scout():
    """用户要求重看字段 → route_to 在纯通道中被忽略"""
    orch = Orchestrator(HaGoKuConfig())
    orch._df_raw = pd.DataFrame({"A": [1, 2]})
    orch._df_clean = orch._df_raw
    context = {
        "column_semantics": [
            {"column_name": "A", "display_name": "列A", "suggested_role": "target", "used_in_analysis": True},
        ],
        "query": "分析",
    }

    fake = FakeCleanerAgent()
    orch._agent = fake
    fake.run_step.return_value = {
        "text": "好的",
        "submit_assessment": False,
        "assessment": None,
        "route_to": {"stage": "scout", "reason": "字段理解有误"},
    }

    result = orch._handle_cleaner_reply("字段理解有问题，回去重看", context)
    assert isinstance(result, dict)
    assert result["status"] == "scout_review"
