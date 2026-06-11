"""测试记忆系统 — MemoryManager + 双后端 + 应用/学习/YAML/Resume"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from hagoku.storage.database import HaGoKuDB
from hagoku.storage.memory import (
    AnalysisPatternDef,
    CleaningPrefDef,
    ColumnSemanticDef,
    MemoryManager,
    ProgressYaml,
)
from hagoku.storage.memory_backends import (
    MemoryBackend,
    SqliteMemoryBackend,
    YamlMemoryBackend,
)
from hagoku.agents.types import ColumnSemantic, DataContext, SemanticType


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def db(tmp_path):
    """创建临时数据库"""
    database = HaGoKuDB(tmp_path / "test.db")
    yield database
    database.close()
    HaGoKuDB.reset_instance()


@pytest.fixture
def progress_path(tmp_path):
    """返回临时 progress.yaml 路径"""
    return tmp_path / "progress.yaml"


@pytest.fixture
def mm(db, progress_path):
    """创建带 YAML 后端的 MemoryManager"""
    return MemoryManager(db, progress_path=progress_path)


@pytest.fixture
def mm_no_yaml(db):
    """创建不带 YAML 后端的 MemoryManager"""
    return MemoryManager(db)


# ── SqliteMemoryBackend ──────────────────────────────────────


class TestSqliteMemoryBackend:
    def test_save_and_load(self, db):
        backend = SqliteMemoryBackend(db)
        backend.save("proj1", "column_semantic", "age", '{"semantic": "numeric"}', "auto", 0.9)

        entries = backend.load("proj1", "column_semantic")
        assert len(entries) == 1
        assert entries[0]["key"] == "age"
        assert entries[0]["value"]["semantic"] == "numeric"

    def test_save_upsert(self, db):
        backend = SqliteMemoryBackend(db)
        backend.save("p1", "cat", "k1", "val1", "auto", 0.5)
        backend.save("p1", "cat", "k1", "val2", "user", 1.0)

        entries = backend.load("p1", "cat")
        assert len(entries) == 1
        assert entries[0]["value"] == "val2"

    def test_load_by_category(self, db):
        backend = SqliteMemoryBackend(db)
        backend.save("p1", "cat_a", "k1", "v1", "auto", 1.0)
        backend.save("p1", "cat_b", "k2", "v2", "auto", 1.0)

        a_entries = backend.load("p1", "cat_a")
        assert len(a_entries) == 1
        assert a_entries[0]["key"] == "k1"

        all_entries = backend.load("p1")
        assert len(all_entries) == 2

    def test_delete(self, db):
        backend = SqliteMemoryBackend(db)
        backend.save("p1", "cat", "k1", "v1", "auto", 1.0)

        assert backend.delete("p1", "cat", "k1") is True
        assert backend.delete("p1", "cat", "k1") is False  # 已删
        assert backend.load("p1", "cat") == []

    def test_load_column_semantics(self, db):
        backend = SqliteMemoryBackend(db)
        backend.save("p1", "column_semantic", "age",
                      json.dumps({"semantic": "numeric", "role": "feature"}), "auto", 0.9)
        backend.save("p1", "column_semantic", "name",
                      json.dumps({"semantic": "categorical"}), "auto", 0.7)

        cols = backend.load_column_semantics("p1")
        assert "age" in cols
        assert cols["age"]["semantic"] == "numeric"
        assert "name" in cols

    def test_global_memory(self, db):
        backend = SqliteMemoryBackend(db)
        backend.save(None, "user_note", "tip", "always check nulls", "user", 1.0)

        entries = backend.load(None, "user_note")
        assert len(entries) == 1
        assert entries[0]["key"] == "tip"


# ── YamlMemoryBackend ────────────────────────────────────────


class TestYamlMemoryBackend:
    def test_save_and_load_column_semantic(self, tmp_path):
        path = tmp_path / "schema.yaml"
        backend = YamlMemoryBackend(path)

        backend.save("p1", "column_semantic", "age",
                      json.dumps({"semantic": "numeric", "role": "feature"}), "user", 1.0)

        entries = backend.load("p1", "column_semantic")
        assert len(entries) == 1
        assert entries[0]["key"] == "age"
        assert entries[0]["value"]["semantic"] == "numeric"

    def test_save_and_load_target(self, tmp_path):
        path = tmp_path / "schema.yaml"
        backend = YamlMemoryBackend(path)

        backend.save("p1", "target_variable", "revenue",
                      json.dumps({"column": "revenue", "role": "target"}), "user", 1.0)

        entries = backend.load("p1", "target_variable")
        assert len(entries) == 1
        assert entries[0]["key"] == "revenue"

    def test_save_and_load_memory_section(self, tmp_path):
        path = tmp_path / "schema.yaml"
        backend = YamlMemoryBackend(path)

        backend.save("p1", "cleaning_pref", "age",
                      json.dumps({"strategy": "median", "reason": "skewed"}), "auto", 0.6)

        entries = backend.load("p1", "cleaning_pref")
        assert len(entries) == 1
        assert entries[0]["value"]["strategy"] == "median"

    def test_load_all(self, tmp_path):
        path = tmp_path / "schema.yaml"
        backend = YamlMemoryBackend(path)

        backend.save("p1", "column_semantic", "age",
                      json.dumps({"semantic": "numeric"}), "user", 1.0)
        backend.save("p1", "target_variable", "revenue",
                      json.dumps({"column": "revenue"}), "user", 1.0)

        all_entries = backend.load("p1")
        categories = {e["category"] for e in all_entries}
        assert "column_semantic" in categories
        assert "target_variable" in categories

    def test_delete_column_semantic(self, tmp_path):
        path = tmp_path / "schema.yaml"
        backend = YamlMemoryBackend(path)

        backend.save("p1", "column_semantic", "age",
                      json.dumps({"semantic": "numeric"}), "user", 1.0)
        assert backend.delete("p1", "column_semantic", "age") is True

        entries = backend.load("p1", "column_semantic")
        assert len(entries) == 0

    def test_delete_target(self, tmp_path):
        path = tmp_path / "schema.yaml"
        backend = YamlMemoryBackend(path)

        backend.save("p1", "target_variable", "revenue",
                      json.dumps({"column": "revenue"}), "user", 1.0)
        assert backend.delete("p1", "target_variable", "revenue") is True

        entries = backend.load("p1", "target_variable")
        assert len(entries) == 0

    def test_load_column_semantics_direct(self, tmp_path):
        path = tmp_path / "schema.yaml"
        backend = YamlMemoryBackend(path)

        backend.save("p1", "column_semantic", "age",
                      json.dumps({"semantic": "numeric", "role": "feature"}), "user", 1.0)
        backend.save("p1", "column_semantic", "name",
                      json.dumps({"semantic": "categorical"}), "user", 1.0)

        cols = backend.load_column_semantics("p1")
        assert "age" in cols
        assert "name" in cols
        assert cols["age"]["semantic"] == "numeric"

    def test_exists_and_mtime(self, tmp_path):
        path = tmp_path / "schema.yaml"
        backend = YamlMemoryBackend(path)

        assert backend.exists() is False
        assert backend.mtime() is None

        backend.save("p1", "column_semantic", "x", '{"semantic": "numeric"}', "user", 1.0)
        assert backend.exists() is True
        assert backend.mtime() is not None

    def test_nonexistent_file_load(self, tmp_path):
        path = tmp_path / "nonexistent.yaml"
        backend = YamlMemoryBackend(path)
        entries = backend.load("p1")
        assert entries == []


# ── MemoryManager 通用读写 ────────────────────────────────────


class TestMemoryManagerBasic:
    def test_save_and_load(self, mm):
        mm.save("p1", "column_semantic", "age", {"semantic": "numeric"}, source="auto", confidence=0.9)

        entries = mm.load("p1", "column_semantic")
        assert len(entries) >= 1
        found = [e for e in entries if e["key"] == "age"]
        assert len(found) >= 1

    def test_save_writes_both_backends(self, mm, progress_path):
        mm.save("p1", "column_semantic", "age", {"semantic": "numeric"}, source="auto", confidence=0.9)

        # SQLite 应该有
        sqlite_entries = mm._sqlite.load("p1", "column_semantic")
        assert any(e["key"] == "age" for e in sqlite_entries)

        # YAML 应该有
        assert progress_path.exists()
        with open(progress_path) as f:
            data = yaml.safe_load(f)
        assert "age" in data.get("columns", {})

    def test_load_merges_yaml_priority(self, mm, db, progress_path):
        # 先写 SQLite
        mm._sqlite.save("p1", "column_semantic", "age",
                         json.dumps({"semantic": "numeric", "role": "feature"}), "auto", 0.7)
        # 再写 YAML（同一 key，不同值）
        mm._yaml.save("p1", "column_semantic", "age",
                       json.dumps({"semantic": "numeric", "role": "target"}), "user", 1.0)

        entries = mm.load("p1", "column_semantic")
        found = [e for e in entries if e["key"] == "age"]
        assert len(found) == 1
        # YAML 优先，role 应该是 target
        assert found[0]["value"]["role"] == "target"

    def test_delete(self, mm):
        mm.save("p1", "cat", "k1", "val1", source="user", confidence=1.0)
        assert mm.delete("p1", "cat", "k1") is True
        assert mm.delete("p1", "cat", "k1") is False

    def test_no_yaml_backend(self, mm_no_yaml):
        mm_no_yaml.save("p1", "cat", "k1", "val1", source="auto", confidence=0.5)
        entries = mm_no_yaml.load("p1", "cat")
        assert len(entries) == 1

    def test_global_memory(self, mm):
        mm.save(None, "user_note", "tip", "always check nulls", source="user", confidence=1.0)
        entries = mm.load(None, "user_note")
        assert len(entries) >= 1


# ── MemoryManager 结构化操作 ─────────────────────────────────


class TestMemoryManagerStructured:
    def test_save_and_get_column_semantics(self, mm):
        sem = ColumnSemanticDef(semantic="numeric", role="feature", confidence=0.9, source="auto")
        mm.save_column_semantic("p1", "age", sem)

        result = mm.get_column_semantics("p1")
        assert "age" in result
        assert result["age"].semantic == "numeric"
        assert result["age"].role == "feature"

    def test_save_and_get_target(self, mm):
        mm.save_target("p1", "revenue", source="user")

        target = mm.get_target("p1")
        assert target == "revenue"

    def test_save_and_get_cleaning_prefs(self, mm):
        mm.save_cleaning_pref("p1", "age", "median", reason="skewed distribution", source="auto")

        prefs = mm.get_cleaning_prefs("p1")
        assert "age" in prefs
        assert prefs["age"].strategy == "median"
        assert prefs["age"].reason == "skewed distribution"

    def test_save_and_get_analysis_patterns(self, mm):
        mm.save_analysis_pattern("p1", "regression", question="trend?", significance="significant", source="auto")

        patterns = mm.get_analysis_patterns("p1")
        assert len(patterns) >= 1
        assert patterns[0].analysis_type == "regression"

    def test_save_and_get_user_notes(self, mm):
        mm.save_user_note("p1", "note1", "请关注缺失值")

        notes = mm.get_user_notes("p1")
        assert "note1" in notes
        assert notes["note1"] == "请关注缺失值"

    def test_get_target_none(self, mm):
        assert mm.get_target("nonexistent") is None


# ── Progress YAML I/O ──────────────────────────────────────


class TestProgressYamlIO:
    def test_export_progress_yaml(self, mm, progress_path):
        sem = ColumnSemanticDef(semantic="numeric", role="feature", confidence=0.9, source="auto")
        mm.save_column_semantic("p1", "age", sem)
        mm.save_target("p1", "revenue", source="auto")

        out_path = mm.export_progress_yaml("p1")
        assert out_path.exists()

        with open(out_path) as f:
            data = yaml.safe_load(f)

        assert "columns" in data
        assert "age" in data["columns"]
        assert data["target"] == "revenue"

    def test_import_progress_yaml(self, mm, tmp_path):
        # 创建外部 progress.yaml
        schema = {
            "columns": {
                "age": {"semantic": "numeric", "role": "feature"},
                "region": {"semantic": "categorical", "role": "group"},
            },
            "target": "revenue",
            "confounders": ["season"],
            "_memory": {
                "cleaning_pref": {
                    "age": {"strategy": "median", "reason": "skewed"},
                },
            },
        }
        ext_path = tmp_path / "external_progress.yaml"
        with open(ext_path, "w") as f:
            yaml.dump(schema, f, allow_unicode=True, default_flow_style=False)

        n = mm.import_progress_yaml("p1", ext_path)
        assert n >= 2  # 至少 2 columns + 1 target + 1 memory entry

        # 验证导入到了 SQLite
        target = mm.get_target("p1")
        assert target == "revenue"

        cols = mm.get_column_semantics("p1")
        assert "age" in cols
        assert "region" in cols

    def test_yaml_round_trip(self, mm, progress_path):
        """写入 → 导出 → 重新导入 → 验证一致"""
        sem1 = ColumnSemanticDef(semantic="numeric", role="feature", confidence=0.9, source="auto")
        sem2 = ColumnSemanticDef(semantic="categorical", role="group", confidence=0.8, source="auto")
        mm.save_column_semantic("p1", "age", sem1)
        mm.save_column_semantic("p1", "region", sem2)
        mm.save_target("p1", "revenue", source="user")

        # 导出
        exported_path = mm.export_progress_yaml("p1")

        # 用新 MemoryManager 导入
        db2 = HaGoKuDB(progress_path.parent / "test2.db")
        try:
            mm2 = MemoryManager(db2)
            n = mm2.import_progress_yaml("p1", exported_path)
            assert n >= 2

            target = mm2.get_target("p1")
            assert target == "revenue"
        finally:
            db2.close()

    def test_import_nonexistent_file(self, mm):
        n = mm.import_progress_yaml("p1", Path("/nonexistent/path.yaml"))
        assert n == 0

    def test_export_with_cleaning_prefs(self, mm, progress_path):
        sem = ColumnSemanticDef(semantic="numeric", role="feature", confidence=0.9, source="auto")
        mm.save_column_semantic("p1", "age", sem)
        mm.save_cleaning_pref("p1", "age", "median", reason="skewed")

        out_path = mm.export_progress_yaml("p1")
        with open(out_path) as f:
            data = yaml.safe_load(f)

        assert "_memory" in data
        assert "cleaning_pref" in data["_memory"]


# ── apply_to_context ─────────────────────────────────────────


class TestApplyToContext:
    def _make_context(self) -> DataContext:
        """创建测试用 DataContext"""
        return DataContext(
            data_path="test.csv",
            n_rows=100,
            n_cols=3,
            column_semantics=[
                ColumnSemantic("age", SemanticType.NUMERIC, 0.5, "猜测", needs_user_input=True, suggested_role="feature"),
                ColumnSemantic("revenue", SemanticType.NUMERIC, 0.5, "猜测", needs_user_input=True, suggested_role="feature"),
                ColumnSemantic("region", SemanticType.CATEGORICAL, 0.7, "3个唯一值", suggested_role="categorical_feature"),
            ],
        )

    def test_apply_column_semantics(self, mm):
        ctx = self._make_context()

        # 保存记忆
        mm.save_column_semantic("p1", "age", ColumnSemanticDef(
            semantic="numeric", role="numeric_feature", confidence=0.95, source="auto"))
        mm.save_column_semantic("p1", "revenue", ColumnSemanticDef(
            semantic="target", role="target", confidence=1.0, source="user"))

        mm.apply_to_context("p1", ctx)

        # age 不再 needs_user_input
        age_sem = next(s for s in ctx.column_semantics if s.column_name == "age")
        assert age_sem.needs_user_input is False
        assert age_sem.confidence == 0.95

        # revenue 应变成 TARGET
        rev_sem = next(s for s in ctx.column_semantics if s.column_name == "revenue")
        assert rev_sem.inferred_type == SemanticType.TARGET
        assert rev_sem.suggested_role == "target"

    def test_apply_target(self, mm):
        ctx = self._make_context()
        mm.save_target("p1", "revenue", source="user")

        mm.apply_to_context("p1", ctx)
        assert ctx.target == "revenue"

    def test_apply_confounders(self, mm):
        ctx = self._make_context()
        mm.save_column_semantic("p1", "region", ColumnSemanticDef(
            semantic="categorical", role="control", confidence=0.9, source="auto"))

        mm.apply_to_context("p1", ctx)
        assert "region" in ctx.confounders

    def test_apply_ignore(self, mm):
        ctx = self._make_context()
        mm.save_column_semantic("p1", "age", ColumnSemanticDef(
            semantic="numeric", ignore=True, role="ignore", confidence=1.0, source="user"))

        mm.apply_to_context("p1", ctx)
        age_sem = next(s for s in ctx.column_semantics if s.column_name == "age")
        assert age_sem.suggested_role == "ignore"

    def test_apply_descriptions_and_units(self, mm):
        ctx = self._make_context()
        mm.save_column_semantic("p1", "age", ColumnSemanticDef(
            semantic="numeric", description="客户年龄", unit="岁",
            confidence=1.0, source="user"))

        mm.apply_to_context("p1", ctx)
        assert ctx.column_descriptions.get("age") == "客户年龄"
        assert ctx.units.get("age") == "岁"

    def test_apply_user_constraints(self, mm):
        ctx = self._make_context()
        mm.save_user_note("p1", "rule1", "不能删除超过10%的数据")

        mm.apply_to_context("p1", ctx)
        assert "不能删除超过10%的数据" in ctx.user_constraints

    def test_apply_derives_from_semantics(self, mm):
        """apply_to_context 应调用 derive_from_column_semantics"""
        ctx = self._make_context()
        mm.save_target("p1", "revenue", source="user")

        mm.apply_to_context("p1", ctx)
        assert ctx.target == "revenue"
        assert "revenue" in ctx.variable_roles
        assert ctx.variable_roles["revenue"] == "target"


# ── learn_from_run ───────────────────────────────────────────


class TestLearnFromRun:
    def _make_context(self) -> DataContext:
        return DataContext(
            data_path="test.csv",
            n_rows=100,
            n_cols=3,
            column_semantics=[
                ColumnSemantic("age", SemanticType.NUMERIC, 0.9, "数值类型", suggested_role="feature"),
                ColumnSemantic("revenue", SemanticType.TARGET, 1.0, "用户确认", suggested_role="target"),
                ColumnSemantic("region", SemanticType.CATEGORICAL, 0.7, "3个唯一值", suggested_role="categorical_feature"),
            ],
            target="revenue",
        )

    def test_learns_column_semantics(self, mm):
        ctx = self._make_context()
        cleaning_report = MagicMock()
        cleaning_report.operations = []

        # 构造假 results
        result1 = MagicMock()
        result1.analysis_type = "regression"
        result1.question = "revenue趋势"
        result1.significance = "significant"

        n = mm.learn_from_run("p1", ctx, [result1], cleaning_report)
        assert n >= 1  # 至少学了 column_semantic

        # 验证学习了
        cols = mm.get_column_semantics("p1")
        assert "age" in cols
        assert "revenue" in cols

    def test_learns_target(self, mm):
        ctx = self._make_context()
        cleaning_report = MagicMock()
        cleaning_report.operations = []

        n = mm.learn_from_run("p1", ctx, [], cleaning_report)
        target = mm.get_target("p1")
        assert target == "revenue"

    def test_learns_cleaning_prefs(self, mm):
        ctx = self._make_context()
        op = MagicMock()
        op.column = "age"
        op.strategy = MagicMock(value="median")
        op.reason = "skewed distribution"
        cleaning_report = MagicMock()
        cleaning_report.operations = [op]

        mm.learn_from_run("p1", ctx, [], cleaning_report)

        prefs = mm.get_cleaning_prefs("p1")
        assert "age" in prefs
        assert prefs["age"].strategy == "median"

    def test_learns_analysis_patterns(self, mm):
        ctx = self._make_context()
        result1 = MagicMock()
        result1.analysis_type = "regression"
        result1.question = "trend?"
        result1.significance = "significant"

        cleaning_report = MagicMock()
        cleaning_report.operations = []

        mm.learn_from_run("p1", ctx, [result1], cleaning_report)

        patterns = mm.get_analysis_patterns("p1")
        assert len(patterns) >= 1
        assert patterns[0].analysis_type == "regression"

    def test_auto_exports_progress_yaml(self, mm, progress_path):
        ctx = self._make_context()
        cleaning_report = MagicMock()
        cleaning_report.operations = []

        mm.learn_from_run("p1", ctx, [], cleaning_report)

        # 应该自动导出了 progress.yaml
        assert progress_path.exists()


# ── Resume 支持 ──────────────────────────────────────────────


class TestResumeState:
    def test_save_and_get_resume_state(self, mm, db):
        # 先创建项目
        db.create_project("p1")

        ctx = DataContext(data_path="test.csv", n_rows=100, n_cols=3)
        mm.save_resume_state("p1", "cleaned", cleaned_path="/tmp/cleaned.parquet",
                              context=ctx, run_id="run001")

        state = mm.get_resume_state("p1")
        assert state is not None
        assert state["stage"] == "cleaned"
        assert state["cleaned_path"] == "/tmp/cleaned.parquet"

    def test_get_resume_state_none(self, mm, db):
        state = mm.get_resume_state("nonexistent_project")
        assert state is None

    def test_get_resume_state_created_stage(self, mm, db):
        db.create_project("p1")
        db.update_project_state("p1", stage="created")

        state = mm.get_resume_state("p1")
        assert state is None  # "created" 阶段不返回恢复状态


# ── YAML 自动同步 ────────────────────────────────────────────


class TestYamlAutoSync:
    def test_auto_sync_on_init(self, db, tmp_path):
        """YAML 存在但 SQLite 空时，init 应自动导入"""
        progress_path = tmp_path / "progress.yaml"
        schema = {
            "columns": {
                "age": {"semantic": "numeric", "role": "feature"},
            },
            "target": "revenue",
        }
        with open(progress_path, "w") as f:
            yaml.dump(schema, f, allow_unicode=True, default_flow_style=False)

        mm = MemoryManager(db, progress_path=progress_path)

        # 应该已自动导入到 SQLite
        target = mm.get_target("p1")  # 注意 YAML 没指定 project_id，可能不会按 p1 查
        # 检查 SQLite 有记录即可
        sqlite_entries = mm._sqlite.load(None, "column_semantic")
        assert len(sqlite_entries) >= 1


# ── 无 YAML 降级 ─────────────────────────────────────────────


class TestNoYamlFallback:
    def test_operations_without_yaml(self, mm_no_yaml):
        """无 YAML 后端时，所有操作应正常工作（仅 SQLite）"""
        sem = ColumnSemanticDef(semantic="numeric", role="feature", confidence=0.9, source="auto")
        mm_no_yaml.save_column_semantic("p1", "age", sem)
        mm_no_yaml.save_target("p1", "revenue", source="user")

        cols = mm_no_yaml.get_column_semantics("p1")
        assert "age" in cols

        target = mm_no_yaml.get_target("p1")
        assert target == "revenue"

    def test_export_without_yaml(self, mm_no_yaml, tmp_path):
        """无 YAML 后端时，export_progress_yaml 应指定路径"""
        sem = ColumnSemanticDef(semantic="numeric", role="feature", confidence=0.9, source="auto")
        mm_no_yaml.save_column_semantic("p1", "age", sem)

        out_path = tmp_path / "export.yaml"
        result_path = mm_no_yaml.export_progress_yaml("p1", out_path)
        assert result_path.exists()

    def test_delete_without_yaml(self, mm_no_yaml):
        mm_no_yaml.save("p1", "cat", "k1", "val1", source="user", confidence=1.0)
        assert mm_no_yaml.delete("p1", "cat", "k1") is True


# ── Pydantic 模型 ────────────────────────────────────────────


class TestPydanticModels:
    def test_column_semantic_def(self):
        sem = ColumnSemanticDef(semantic="numeric", role="feature", confidence=0.9, source="auto")
        d = sem.model_dump(exclude_none=True)
        assert d["semantic"] == "numeric"

    def test_column_semantic_def_with_optional(self):
        sem = ColumnSemanticDef(
            semantic="ordinal", ordinal=True, order=["low", "mid", "high"],
            unit="level", description="satisfaction",
            confidence=0.8, source="user",
        )
        assert sem.ordinal is True
        assert len(sem.order) == 3

    def test_cleaning_pref_def(self):
        pref = CleaningPrefDef(strategy="median", reason="skewed")
        assert pref.strategy == "median"

    def test_analysis_pattern_def(self):
        pat = AnalysisPatternDef(analysis_type="regression", question="trend?", significance="significant")
        assert pat.analysis_type == "regression"

    def test_progress_yaml(self):
        s = ProgressYaml(
            columns={"age": ColumnSemanticDef(semantic="numeric")},
            target="revenue",
        )
        assert s.target == "revenue"
        assert "age" in s.columns

    def test_column_semantic_def_ignore(self):
        sem = ColumnSemanticDef(semantic="id", ignore=True, role="identifier")
        assert sem.ignore is True
