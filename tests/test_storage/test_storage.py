"""测试数据持久化"""

import json
import tempfile
from pathlib import Path

import pytest
import pandas as pd

from hagokyu.storage.database import HaGoKuDB
from hagokyu.storage.artifact import ArtifactManager, DataArtifact
from hagokyu.storage.output import OutputManager
from hagokyu.config import OutputConfig


class TestHaGoKuDB:
    @pytest.fixture
    def db(self, tmp_path):
        db = HaGoKuDB(tmp_path / "test.db")
        yield db
        db.close()
        HaGoKuDB.reset_instance()

    def test_create_project(self, db):
        p = db.create_project("test_project", description="测试项目")
        assert p["id"] == "test_project"
        assert p["description"] == "测试项目"

    def test_get_project(self, db):
        db.create_project("test_project")
        p = db.get_project("test_project")
        assert p is not None
        assert p["id"] == "test_project"

    def test_list_projects(self, db):
        db.create_project("p1")
        db.create_project("p2")
        projs = db.list_projects()
        assert len(projs) == 2

    def test_create_run(self, db):
        db.create_project("test_project")
        run = db.create_run("20260501_120000", "test_project", query="分析趋势")
        assert run["id"] == "20260501_120000"
        assert run["status"] == "running"

    def test_complete_run(self, db):
        db.create_project("test_project")
        db.create_run("20260501_120000", "test_project")
        db.complete_run("20260501_120000", duration_ms=5000, output_path="/tmp/report.html")
        run = db.get_run("20260501_120000")
        assert run["status"] == "completed"
        assert run["duration_ms"] == 5000

    def test_save_and_get_findings(self, db):
        db.create_project("test_project")
        db.create_run("20260501_120000", "test_project")
        db.save_finding({
            "id": "f001",
            "run_id": "20260501_120000",
            "analysis_type": "regression",
            "question": "revenue 预测因素",
            "conclusion_plain": "R²=0.87",
            "p_value": 0.001,
            "effect_size": 0.45,
            "effect_type": "f_squared",
            "significance": "significant",
        })
        findings = db.get_findings("20260501_120000")
        assert len(findings) == 1
        assert findings[0]["analysis_type"] == "regression"

    def test_query_findings(self, db):
        db.create_project("test_project")
        db.create_run("20260501_120000", "test_project")
        db.save_finding({
            "id": "f001", "run_id": "20260501_120000",
            "analysis_type": "regression",
            "significance": "significant",
            "p_value": 0.001, "effect_size": 0.8,
        })
        db.save_finding({
            "id": "f002", "run_id": "20260501_120000",
            "analysis_type": "ttest",
            "significance": "not_significant",
            "p_value": 0.5, "effect_size": 0.1,
        })

        # 按显著性和效应量过滤
        results = db.query_findings(
            project_id="test_project",
            significance="significant",
            min_effect_size=0.5,
        )
        assert len(results) == 1

    def test_save_and_get_artifacts(self, db):
        db.create_project("test_project")
        db.create_run("20260501_120000", "test_project")
        db.save_artifact({
            "id": "a001",
            "run_id": "20260501_120000",
            "agent": "scout",
            "type": "parquet",
            "file_path": "/tmp/raw.parquet",
        })
        artifacts = db.get_artifacts("20260501_120000")
        assert len(artifacts) == 1
        assert artifacts[0]["agent"] == "scout"

    def test_diff_runs(self, db):
        db.create_project("test_project")
        db.create_run("r1", "test_project")
        db.create_run("r2", "test_project")

        db.save_finding({
            "id": "f1", "run_id": "r1",
            "analysis_type": "regression",
            "question": "revenue 趋势",
            "conclusion_statistical": "R²=0.87",
            "p_value": 0.001, "effect_size": 0.5,
        })
        db.save_finding({
            "id": "f2", "run_id": "r2",
            "analysis_type": "regression",
            "question": "revenue 趋势",
            "conclusion_statistical": "R²=0.91",
            "p_value": 0.001, "effect_size": 0.6,
        })

        diff = db.diff_runs("r1", "r2")
        assert len(diff["changed"]) == 1

    def test_add_data_source(self, db):
        db.create_project("test_project")
        ds = db.add_data_source(
            "ds001", "test_project", "sales_csv", "csv",
            connection="./data/sales.csv",
            schema_json={"revenue": "numeric", "region": "categorical"},
        )
        assert ds["name"] == "sales_csv"
        # schema_json 反序列化
        assert ds["schema_json"]["revenue"] == "numeric"


class TestArtifactManager:
    @pytest.fixture
    def mgr(self, tmp_path):
        return ArtifactManager(tmp_path / "data")

    def test_create_and_load_artifact(self, mgr, tmp_path):
        df = pd.DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]})
        artifact = mgr.create_artifact("scout", "raw", df)
        assert artifact.metadata["rows"] == 3
        assert artifact.artifact_id

        # 加载
        loaded_df, loaded_artifact = mgr.load_artifact(artifact.file_path)
        assert len(loaded_df) == 3

    def test_load_latest(self, mgr):
        df = pd.DataFrame({"x": [1, 2, 3]})
        mgr.create_artifact("scout", "raw", df)

        result = mgr.load_latest("raw")
        assert result is not None
        loaded_df, _ = result
        assert len(loaded_df) == 3

    def test_list_artifacts(self, mgr):
        df = pd.DataFrame({"x": [1, 2, 3]})
        mgr.create_artifact("scout", "raw", df)
        mgr.create_artifact("cleaner", "cleaned", df)

        all_artifacts = mgr.list_artifacts()
        assert len(all_artifacts) == 2

        raw_only = mgr.list_artifacts("raw")
        assert len(raw_only) == 1

    def test_extend_lineage(self, mgr):
        df = pd.DataFrame({"x": [1, 2, 3]})
        parent = mgr.create_artifact("scout", "raw", df, lineage=["raw"])
        lineage = mgr.extend_lineage(parent, "cleaned")
        assert lineage == ["raw", "cleaned"]


class TestOutputManager:
    @pytest.fixture
    def output_mgr(self, tmp_path):
        config = OutputConfig(base_dir=tmp_path / "projects")
        return OutputManager(config, "test_project")

    def test_create_run_dir(self, output_mgr):
        run_dir = output_mgr.create_run_dir("20260501_120000")
        assert run_dir.exists()
        assert (run_dir / "results").exists()
        assert (run_dir / "diagnostics").exists()
        assert (run_dir / "output").exists()

    def test_save_and_load_meta(self, output_mgr):
        run_dir = output_mgr.create_run_dir("20260501_120000")
        output_mgr.save_run_meta(run_dir, {"run_id": "20260501_120000", "status": "running"})
        meta = output_mgr.load_run_meta(run_dir)
        assert meta["status"] == "running"

    def test_get_output_path(self, output_mgr):
        run_dir = output_mgr.create_run_dir("20260501_120000")
        path = output_mgr.get_output_path(run_dir, name="report", fmt="html")
        assert str(path).endswith("report.html")
        assert "output" in str(path)

    def test_list_runs(self, output_mgr):
        output_mgr.create_run_dir("20260501_120000")
        output_mgr.create_run_dir("20260502_090000")
        runs = output_mgr.list_runs()
        assert len(runs) == 2
