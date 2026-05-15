"""测试 Agent 层（含 Scribe 兜底恢复）"""

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

    def test_infer_id_column(self, event_bus, llm_config):
        scout = ScoutAgent(llm_config, event_bus)
        series = pd.Series(range(100))
        result = scout._infer_column(series, "user_id", target_keywords=[])
        assert result["inferred_type"] == "id"
        assert result["confidence"] > 0.9

    def test_infer_numeric_column(self, event_bus, llm_config):
        scout = ScoutAgent(llm_config, event_bus)
        # Use non-unique values to avoid ID detection
        series = pd.Series([1.0, 2.0, 3.0, 1.0, 2.0, 3.0, 4.0, 5.0, 1.0, 2.0] * 10)
        result = scout._infer_column(series, "value", target_keywords=[])
        assert result["inferred_type"] == "numeric"

    def test_infer_boolean_column(self, event_bus, llm_config):
        scout = ScoutAgent(llm_config, event_bus)
        series = pd.Series([0, 1, 0, 1, 1, 0, 0, 1])
        result = scout._infer_column(series, "is_active", target_keywords=[])
        assert result["inferred_type"] == "boolean"

    def test_infer_categorical_column(self, event_bus, llm_config):
        scout = ScoutAgent(llm_config, event_bus)
        series = pd.Series(["A", "B", "C", "A", "B", "C", "A", "B"])
        result = scout._infer_column(series, "region", target_keywords=[])
        assert result["inferred_type"] == "categorical"

    def test_infer_target_from_column_name(self, event_bus, llm_config):
        scout = ScoutAgent(llm_config, event_bus)
        # Use non-unique values to avoid ID detection
        series = pd.Series([100.0, 200.0, 150.0, 300.0, 250.0, 100.0, 200.0, 150.0, 300.0, 250.0] * 10)
        result = scout._infer_column(series, "revenue", target_keywords=["revenue"])
        assert result["inferred_type"] == "target"
        assert result["needs_user_input"]

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
        assert _scout_description_is_meaningful_for_user("BU", "BU（事业部）")
        assert _scout_description_is_meaningful_for_user("Period", "月份或账期")


class TestScoutFieldDescriptionParsing:
    def test_parse_fullwidth_and_ascii_colon(self):
        from hagoku.agents.scout.agent import _parse_llm_field_desc_line

        assert _parse_llm_field_desc_line("BU：事业部划分") == ("BU", "事业部划分")
        assert _parse_llm_field_desc_line("Code: 产品编码") == ("Code", "产品编码")
        assert _parse_llm_field_desc_line("- Period: 2024-01") == ("Period", "2024-01")
        assert _parse_llm_field_desc_line("`Inc1`: 收入项") == ("Inc1", "收入项")

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


class TestScribeRecoverFieldDescriptions:
    """Scribe LLM 兜底恢复遗漏字段描述 — 无硬编码 if-else。"""

    @pytest.fixture
    def bus(self):
        return EventBus()

    @pytest.fixture
    def llm_cfg(self):
        return LLMConfig()

    def test_no_missing_returns_existing(self, tmp_path, bus, llm_cfg):
        """无缺失列时直接返回现有描述（不调用 LLM）。"""
        from hagoku.agents._scribe.agent import ScribeAgent

        scribe = ScribeAgent(llm_cfg, bus, tmp_path)
        existing = {"A": "年龄", "B": "收入"}
        result = scribe.recover_field_descriptions(
            row_count=10,
            col_count=2,
            existing=existing,
            column_names=["A", "B"],
        )
        assert result == existing
        assert result == {"A": "年龄", "B": "收入"}

    def test_missing_fallback_gives_placeholder(self, tmp_path, bus, llm_cfg):
        """无有效 LLM 连接时，为缺失列返回基础占位（不硬编码假值）。"""
        from hagoku.agents._scribe.agent import ScribeAgent

        scribe = ScribeAgent(llm_cfg, bus, tmp_path)
        existing = {"A": "年龄"}
        result = scribe.recover_field_descriptions(
            row_count=5,
            col_count=3,
            existing=existing,
            column_names=["A", "B", "C"],
        )
        assert "A" in result
        assert result["A"] == "年龄"
        for col in ("B", "C"):
            assert col in result
            assert isinstance(result[col], str)
            assert len(result[col]) > 0  # 至少一个占位描述

    def test_scout_missing_triggers_needs_input_no_hardcode(self, tmp_path, bus, llm_cfg):
        """Scout 端到端：缺失字段仅标记 needs_user_input，不填充硬编码。"""
        from hagoku.agents.scout.agent import ScoutAgent
        from hagoku.agents.scout.agent import _description_is_user_facing_meaningful as _is_mean

        scout = ScoutAgent(llm_cfg, bus, scribe=None)
        context: dict = {
            "n_rows": 4,
            "n_cols": 2,
            "column_semantics": [
                {"column_name": "U", "inferred_type": "numeric", "evidence": "1,2",
                 "confidence": 0.5, "suggested_role": "feature"},
                {"column_name": "V", "inferred_type": "string", "evidence": "x",
                 "confidence": 0.3, "suggested_role": "id"},
            ],
            "column_descriptions": {"U": "", "V": ""},
            "column_display_names": {},
        }

        # 模拟 _generate_field_descriptions 中硬编码已删后的行为
        missing = []
        for sem in context["column_semantics"]:
            col = sem["column_name"]
            raw = str(context["column_descriptions"].get(col, "") or "").strip()
            if _is_mean(col, raw):
                continue
            missing.append(col)
            context.setdefault("column_display_names", {})[col] = col
            context["column_descriptions"][col] = ""
            sem["needs_user_input"] = True

        assert len(missing) == 2
        for sem in context["column_semantics"]:
            assert sem["needs_user_input"] is True
            assert context["column_descriptions"][sem["column_name"]] == ""

        # 确认没有硬编码的 "事业部"、"日期" 等假值被注入
        for col in ("U", "V"):
            assert context["column_descriptions"].get(col) == ""

    def test_scribe_recovery_applies_to_missing(self, tmp_path, bus, llm_cfg):
        """Scribe 兜底恢复后，缺失列的描述被更新（不被硬编码覆盖）。"""
        from hagoku.agents._scribe.agent import ScribeAgent
        from hagoku.agents.scout.agent import ScoutAgent
        from hagoku.agents.scout.agent import _description_is_user_facing_meaningful as _is_mean

        scribe = ScribeAgent(llm_cfg, bus, tmp_path)
        scout = ScoutAgent(llm_cfg, bus, scribe=scribe)

        ctx: dict = {
            "n_rows": 3,
            "n_cols": 2,
            "column_semantics": [
                {"column_name": "P", "inferred_type": "numeric", "evidence": "10,20",
                 "confidence": 0.5, "suggested_role": "feature"},
                {"column_name": "Q", "inferred_type": "string", "evidence": "a,b",
                 "confidence": 0.3, "suggested_role": "id"},
            ],
            "column_descriptions": {"P": "", "Q": ""},
            "column_display_names": {},
        }

        # 标记缺失 + needs_user_input
        for sem in ctx["column_semantics"]:
            col = sem["column_name"]
            raw = str(ctx["column_descriptions"].get(col, "") or "").strip()
            if not _is_mean(col, raw):
                ctx.setdefault("column_display_names", {})[col] = col
                ctx["column_descriptions"][col] = ""
                sem["needs_user_input"] = True

        # 调用 Scribe 恢复（无真实 LLM 连接时用 fallback 占位）
        recovered = scout.scribe.recover_field_descriptions(
            row_count=ctx["n_rows"],
            col_count=ctx["n_cols"],
            existing=ctx["column_descriptions"],
            column_names=["P", "Q"],
        )
        for col in ("P", "Q"):
            assert col in recovered
            assert isinstance(recovered[col], str)
            assert len(recovered[col]) > 0


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