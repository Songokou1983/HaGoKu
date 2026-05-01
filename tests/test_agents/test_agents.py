"""测试 Agent 层"""

import pytest
import pandas as pd
import numpy as np

from hagokyu.agents.scout import ScoutAgent, ColumnSemantic, SemanticType, DataContext
from hagokyu.agents.cleaner import CleanerAgent
from hagokyu.agents.analyst import AnalystAgent, AnalysisResult
from hagokyu.agents.base import DataAgentBase
from hagokyu.config import LLMConfig
from hagokyu.observability.event_bus import EventBus
from hagokyu.observability.events import EventType


class TestScoutAgent:
    @pytest.fixture
    def event_bus(self):
        return EventBus()

    @pytest.fixture
    def llm_config(self):
        return LLMConfig()

    def test_infer_id_column(self, event_bus, llm_config):
        scout = ScoutAgent(llm_config, event_bus)
        series = pd.Series(range(100))
        result = scout._infer_column(series, "user_id")
        assert result.inferred_type == SemanticType.ID
        assert result.confidence > 0.9

    def test_infer_numeric_column(self, event_bus, llm_config):
        scout = ScoutAgent(llm_config, event_bus)
        # Use non-unique values to avoid ID detection
        series = pd.Series([1.0, 2.0, 3.0, 1.0, 2.0, 3.0, 4.0, 5.0, 1.0, 2.0] * 10)
        result = scout._infer_column(series, "value")
        assert result.inferred_type == SemanticType.NUMERIC

    def test_infer_boolean_column(self, event_bus, llm_config):
        scout = ScoutAgent(llm_config, event_bus)
        series = pd.Series([0, 1, 0, 1, 1, 0, 0, 1])
        result = scout._infer_column(series, "is_active")
        assert result.inferred_type == SemanticType.BOOLEAN

    def test_infer_categorical_column(self, event_bus, llm_config):
        scout = ScoutAgent(llm_config, event_bus)
        series = pd.Series(["A", "B", "C", "A", "B", "C", "A", "B"])
        result = scout._infer_column(series, "region")
        assert result.inferred_type == SemanticType.CATEGORICAL

    def test_infer_target_from_column_name(self, event_bus, llm_config):
        scout = ScoutAgent(llm_config, event_bus)
        # Use non-unique values to avoid ID detection
        series = pd.Series([100.0, 200.0, 150.0, 300.0, 250.0, 100.0, 200.0, 150.0, 300.0, 250.0] * 10)
        result = scout._infer_column(series, "revenue", target_keywords=["revenue"])
        assert result.inferred_type == SemanticType.TARGET
        assert result.needs_user_input

    def test_infer_all_semantics(self, event_bus, llm_config):
        scout = ScoutAgent(llm_config, event_bus)
        df = pd.DataFrame({
            "id": range(50),
            "value": np.random.randn(50),
            "category": np.random.choice(["A", "B"], 50),
        })
        results = scout._infer_all_semantics(df)
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

    def test_apply_user_feedback(self, event_bus, llm_config):
        ctx = DataContext(
            data_path="/tmp/test.csv",
            n_rows=100,
            n_cols=5,
            column_semantics=[
                ColumnSemantic("value", SemanticType.TARGET, 0.5, "列名含关键词", needs_user_input=True),
            ],
        )
        # 用户确认这确实是目标变量
        updated = ScoutAgent(llm_config, event_bus).apply_user_feedback(
            ctx, "value", SemanticType.TARGET, "target"
        )
        sem = next(s for s in updated.column_semantics if s.column_name == "value")
        assert sem.confidence == 1.0
        assert not sem.needs_user_input


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
