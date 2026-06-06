"""测试 Agent 层（Step 4：Scribe 类已删除，4 agent 看板 block/unblock 走 Orchestrator）"""

import pytest
import pandas as pd
import numpy as np

from hagoku.agents.scout import ScoutAgent, ColumnSemantic, SemanticType, DataContext
from hagoku.agents.analyst import AnalystAgent, AnalysisResult
from hagoku.config import LLMConfig
from hagoku.observability.event_bus import EventBus
from hagoku.observability.events import EventType


class TestScoutAgent:
    @pytest.fixture
    def event_bus(self):
        return EventBus()

    @pytest.fixture
    def llm_config(self):
        return LLMConfig()


    def test_infer_all_semantics(self, event_bus, llm_config):
        scout = ScoutAgent(llm_config, event_bus)
        df = pd.DataFrame({
            "id": range(50),
            "value": np.random.randn(50),
            "category": np.random.choice(["A", "B"], 50),
        })
        results = scout._infer_all_semantics(df, query="")
        assert len(results) == 3

    def test_data_context(self, event_bus, llm_config):
        ctx = DataContext(
            data_path="/tmp/test.csv",
            n_rows=100,
            n_cols=5,
            column_semantics=[
                ColumnSemantic("id", SemanticType.ID, 0.95, "100%唯一"),
                ColumnSemantic("value", SemanticType.NUMERIC, 0.90, "数值类型"),
            ],
            quality_score=0.85,
        )
        assert ctx.n_rows == 100
        uncertain = ctx.get_uncertain_columns()
        assert len(uncertain) == 0


class TestScoutUserFacingDescriptionFilter:
    """编排层展示给用户前，过滤 Scout 的「列名（类型）」占位描述。"""

    def test_type_echo_is_not_meaningful(self):
        from hagoku.manager.orchestrator import _scout_description_is_meaningful_for_user

        assert not _scout_description_is_meaningful_for_user("BU", "BU（分类型）")
        assert not _scout_description_is_meaningful_for_user("Code", "Code（未知类型）")
        assert not _scout_description_is_meaningful_for_user("Period", "Period（数值型）")
        assert not _scout_description_is_meaningful_for_user("x", "x")

    def test_business_text_is_meaningful(self):
        from hagoku.manager.orchestrator import _scout_description_is_meaningful_for_user

        assert _scout_description_is_meaningful_for_user("BU", "事业部")
        # 「列名（...）」格式视为结构回显，无论括号内容——语义判断是 LLM 的职责
        assert not _scout_description_is_meaningful_for_user("BU", "BU（事业部）")
        assert _scout_description_is_meaningful_for_user("Period", "月份或账期")


class TestScoutFieldDescriptionParsing:
    # test_parse_fullwidth_and_ascii_colon 已随 commit 07aac73 删除
    # （_parse_llm_field_desc_line 死代码已移除，字段描述统一走 function calling）

    def test_partition_understanding_pipe(self):
        desc = "事业部｜多为事业部/业务线（例：B01, B02）"
        left, sep, right = desc.partition("｜")
        assert sep
        assert left == "事业部"
        assert "多为" in right

    def test_missing_field_marked_needs_input(self):
        """删除硬编码兜底后：缺失描述的字段应被标记为 needs_user_input=True。
        验证 _description_is_user_facing_meaningful 对空/重言描述的判负逻辑不变。"""
        from hagoku.agents.scout.agent import _description_is_user_facing_meaningful

        # 空描述或被判定为无业务含义 → 需要用户输入
        assert not _description_is_user_facing_meaningful("BU", "")
        assert not _description_is_user_facing_meaningful("BU", "BU")
        assert not _description_is_user_facing_meaningful("Inc1", "Inc1（数值型）")
        assert _description_is_user_facing_meaningful("Inc1", "事业部收入金额")


class TestScoutPauseMarkdownTableHelpers:
    def test_md_table_cell_escapes_pipe(self):
        from hagoku.manager.orchestrator import _md_table_cell

        assert _md_table_cell("a|b") == "a｜b"

    def test_display_name_derived_from_meaning(self):
        from hagoku.manager.orchestrator import _scout_display_name_cell

        s = _scout_display_name_cell("BU", "事业部/业务线标识，用于区分不同业务单元", {})
        assert "事业" in s or "业务" in s


class TestAnalystAgent:
    @pytest.fixture
    def event_bus(self):
        return EventBus()

    @pytest.fixture
    def llm_config(self):
        return LLMConfig()

    def test_analysis_result_to_dict(self, event_bus, llm_config):
        result = AnalysisResult(
            result_id="abc123",
            analysis_type="regression",
            question="测试问题",
            conclusion_plain="显著",
            p_value=0.01,
            effect_size=0.5,
            effect_type="f_squared",
            significance="significant",
        )
        d = result.to_dict()
        assert d["analysis_type"] == "regression"
        assert d["p_value"] == 0.01


class TestEventBus:
    def test_emit_and_subscribe(self):
        bus = EventBus()
        received = []
        bus.subscribe(lambda e: received.append(e))

        event = bus.emit(EventType.AGENT_STARTED, "Scout", {"goal": "test"})
        assert len(received) == 1
        assert received[0].agent == "Scout"

    def test_get_timeline(self):
        bus = EventBus()
        bus.emit(EventType.AGENT_STARTED, "Scout")
        bus.emit(EventType.AGENT_COMPLETED, "Scout")
        timeline = bus.get_timeline()
        assert len(timeline) == 2

    def test_get_agent_trace(self):
        bus = EventBus()
        bus.emit(EventType.AGENT_STARTED, "Scout")
        bus.emit(EventType.AGENT_STARTED, "Cleaner")
        scout_trace = bus.get_agent_trace("Scout")
        assert len(scout_trace) == 1
        assert scout_trace[0].agent == "Scout"

    def test_save_and_load(self, tmp_path):
        bus = EventBus()
        bus.emit(EventType.AGENT_STARTED, "Scout", {"goal": "test"})
        bus.emit(EventType.AGENT_COMPLETED, "Scout", {"duration": "5.0s"})

        path = tmp_path / "events.jsonl"
        bus.save_to_file(path)

        loaded = EventBus.load_from_file(path)
        assert len(loaded.events) == 2
        assert loaded.events[0].agent == "Scout"