"""测试工具层"""

import json
import tempfile
from pathlib import Path

import pytest
import pandas as pd
import numpy as np

from hagokyu.tools.data_io import load_data, save_data, get_data_info, compute_data_hash
from hagokyu.tools.profiling import generate_profile, suggest_column_roles
from hagokyu.tools.cleaning import (
    clean_data,
    detect_missing_mechanism,
    detect_outliers_iqr,
    detect_outliers_zscore,
    suggest_cleaning_strategy,
    CleaningStrategy,
)
from hagokyu.tools.analysis import ttest, correlation, chi_square, regression, anova
from hagokyu.tools.diagnostics import diagnose_regression
from hagokyu.tools.reporting import ReportData, ReportSection, ReportGenerator


class TestDataIO:
    def test_load_csv(self, tmp_path):
        df = pd.DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]})
        path = tmp_path / "test.csv"
        df.to_csv(path, index=False)
        loaded = load_data(path)
        assert len(loaded) == 3

    def test_load_parquet(self, tmp_path):
        df = pd.DataFrame({"x": [1, 2, 3]})
        path = tmp_path / "test.parquet"
        df.to_parquet(path, index=False)
        loaded = load_data(path)
        assert len(loaded) == 3

    def test_load_nonexistent(self):
        with pytest.raises(FileNotFoundError):
            load_data("/nonexistent/file.csv")

    def test_load_unsupported_format(self, tmp_path):
        path = tmp_path / "test.xyz"
        path.write_text("data")
        with pytest.raises(ValueError, match="不支持"):
            load_data(path)

    def test_save_and_reload_csv(self, tmp_path):
        df = pd.DataFrame({"x": [1, 2, 3]})
        path = tmp_path / "output.csv"
        save_data(df, path)
        reloaded = load_data(path)
        assert len(reloaded) == 3

    def test_save_parquet(self, tmp_path):
        df = pd.DataFrame({"x": [1, 2, 3]})
        path = tmp_path / "output.parquet"
        save_data(df, path)
        assert path.exists()

    def test_get_data_info(self, tmp_path):
        df = pd.DataFrame({"x": [1, 2, 3], "y": [4, 5, None]})
        path = tmp_path / "test.csv"
        df.to_csv(path, index=False)
        info = get_data_info(df, path)
        assert info["n_rows"] == 3
        assert info["n_columns"] == 2
        assert info["null_count"] == 1
        assert "source_hash" in info

    def test_compute_data_hash(self, tmp_path):
        path = tmp_path / "test.csv"
        pd.DataFrame({"x": [1, 2, 3]}).to_csv(path, index=False)
        h1 = compute_data_hash(path)
        h2 = compute_data_hash(path)
        assert h1 == h2
        assert len(h1) == 32  # MD5 hex


class TestProfiling:
    def test_generate_profile(self):
        df = pd.DataFrame({
            "id": range(100),
            "value": [1.0, 2.0, 3.0, 1.0, 2.0] * 20,  # non-unique numeric
            "category": np.random.choice(["A", "B", "C"], 100),
            "flag": np.random.choice([0, 1], 100),
        })
        p = generate_profile(df)
        assert p["n_rows"] == 100
        assert p["n_cols"] == 4
        assert "quality_score" in p
        assert "columns" in p
        assert p["columns"]["id"]["inferred_type"] == "id"
        assert p["columns"]["value"]["inferred_type"] == "numeric"
        assert p["columns"]["category"]["inferred_type"] in ("categorical", "id")

    def test_profile_with_missing(self):
        df = pd.DataFrame({
            "x": [1, 2, None, 4, 5],
            "y": [1, None, None, 4, 5],
        })
        p = generate_profile(df)
        assert p["missing_summary"]["total_nulls"] == 3
        assert p["missing_summary"]["columns_with_nulls"] == 2

    def test_suggest_column_roles(self):
        df = pd.DataFrame({
            "user_id": range(50),
            "revenue": [100.0, 200.0, 150.0, 300.0, 250.0] * 10,  # non-unique
            "region": np.random.choice(["East", "West"], 50),
        })
        roles = suggest_column_roles(df)
        assert roles["user_id"]["role"] == "identifier"
        assert roles["region"]["type"] == "categorical"


class TestCleaning:
    def test_clean_drop_rows(self):
        df = pd.DataFrame({"x": [1, 2, None, 4, 5]})
        df_clean, report = clean_data(df, operations=[
            {"column": "x", "strategy": "drop_rows", "reason": "test"},
        ])
        assert len(df_clean) == 4
        assert report.total_rows_after == 4

    def test_clean_fill_median(self):
        df = pd.DataFrame({"x": [1.0, 2.0, None, 4.0, 5.0]})
        df_clean, report = clean_data(df, operations=[
            {"column": "x", "strategy": "fill_median", "reason": "test"},
        ])
        assert df_clean["x"].isnull().sum() == 0

    def test_auto_clean(self):
        df = pd.DataFrame({
            "x": [1, 2, None, 4, 5, 6, 7, 8, 9, 10],
            "y": [10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
        })
        df_clean, report = clean_data(df, auto_strategy=True)
        # 应该自动检测并处理 x 的缺失
        assert report.total_rows_after > 0

    def test_detect_outliers_iqr(self):
        df = pd.DataFrame({
            "x": [1, 2, 3, 4, 5, 100],  # 100 is outlier
        })
        outliers = detect_outliers_iqr(df)
        assert outliers["x"]["count"] >= 1

    def test_suggest_cleaning_strategy_low_null(self):
        df = pd.DataFrame({"x": [1, 2, 3, 4, None]})
        strategy, reason = suggest_cleaning_strategy(df, "x", null_rate=0.01)
        assert strategy == CleaningStrategy.DROP_ROWS


class TestAnalysis:
    def test_ttest(self):
        g1 = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        g2 = pd.Series([11, 12, 13, 14, 15, 16, 17, 18, 19, 20])
        result = ttest(g1, g2)
        assert result["test"] == "ttest"
        assert result["p_value"] < 0.05
        assert result["effect_size"] is not None
        assert result["effect_type"] == "cohen_d"

    def test_ttest_no_difference(self):
        np.random.seed(42)
        g1 = pd.Series(np.random.randn(100))
        g2 = pd.Series(np.random.randn(100) + 0.01)
        result = ttest(g1, g2)
        assert result["p_value"] > 0.01  # 大概率不显著

    def test_correlation(self):
        df = pd.DataFrame({
            "x": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            "y": [2, 4, 6, 8, 10, 12, 14, 16, 18, 20],
        })
        result = correlation(df, "x", "y")
        assert result["statistic"] > 0.99  # 完美线性
        assert result["p_value"] < 0.001

    def test_chi_square(self):
        df = pd.DataFrame({
            "group": ["A"] * 50 + ["B"] * 50,
            "result": ["yes"] * 30 + ["no"] * 20 + ["yes"] * 20 + ["no"] * 30,
        })
        result = chi_square(df, "group", "result")
        assert result["test"] == "chi_square"
        assert result["effect_type"] == "cramers_v"
        assert result["p_value"] is not None

    def test_regression(self):
        np.random.seed(42)
        n = 100
        x1 = np.random.randn(n)
        x2 = np.random.randn(n)
        y = 2 * x1 + 3 * x2 + np.random.randn(n) * 0.5 + 5
        df = pd.DataFrame({"y": y, "x1": x1, "x2": x2})

        result = regression(df, "y", ["x1", "x2"])
        assert result["test"] == "regression"
        assert result["r_squared"] > 0.9
        assert result["diagnostics"] is not None
        assert abs(result["coefficients"]["x1"] - 2) < 0.3
        assert abs(result["coefficients"]["x2"] - 3) < 0.3


class TestDiagnostics:
    def test_diagnose_regression(self):
        np.random.seed(42)
        n = 100
        x = np.random.randn(n)
        y = 2 * x + np.random.randn(n) * 0.5 + 5
        df = pd.DataFrame({"y": y, "x": x})

        import statsmodels.api as sm
        model = sm.OLS(df["y"], sm.add_constant(df[["x"]])).fit()

        diag = diagnose_regression(model, df, "y", ["x"])
        assert "residual_normality" in diag
        assert "heteroscedasticity" in diag
        assert "autocorrelation" in diag
        assert "overall" in diag


class TestReporting:
    def test_generate_html_report(self):
        report = ReportData(
            project_name="test_project",
            query="测试问题",
            sections=[
                ReportSection(
                    title="测试章节",
                    content="测试内容",
                    findings=[{
                        "question": "测试发现",
                        "conclusion_plain": "显著",
                        "p_value": 0.01,
                        "effect_size": 0.5,
                        "significance": "significant",
                    }],
                ),
            ],
            data_summary={"n_rows": 100, "n_cols": 5, "quality_score": 0.95, "null_rate": 0.02},
        )

        gen = ReportGenerator()
        html = gen.generate_html(report)
        assert "test_project" in html
        assert "测试问题" in html
        assert "测试章节" in html

    def test_generate_markdown_report(self):
        report = ReportData(
            project_name="test_project",
            query="测试问题",
            sections=[],
        )

        gen = ReportGenerator()
        md = gen.generate_markdown(report)
        assert "test_project" in md
        assert "测试问题" in md

    def test_generate_json_report(self):
        report = ReportData(
            project_name="test_project",
            query="测试问题",
            sections=[],
        )

        gen = ReportGenerator()
        json_str = gen.generate_json(report)
        data = json.loads(json_str)
        assert data["project_name"] == "test_project"

    def test_academic_template(self):
        report = ReportData(
            project_name="学术测试",
            query="研究假设",
            sections=[
                ReportSection(
                    title="回归分析",
                    content="模型显著",
                    findings=[{
                        "question": "X是否影响Y？",
                        "conclusion_plain": "显著",
                        "p_value": 0.001,
                        "effect_size": 0.6,
                        "effect_type": "cohen_d",
                        "significance": "significant",
                    }],
                ),
            ],
            data_summary={"n_rows": 200, "n_cols": 8, "quality_score": 0.92, "null_rate": 0.01},
        )
        gen = ReportGenerator()
        html = gen.generate_html(report, template_name="academic")
        assert "学术测试" in html
        assert "Research Question" in html
        assert "200" in html  # sample size

    def test_brief_template(self):
        report = ReportData(
            project_name="简要测试",
            query="快速看结论",
            sections=[
                ReportSection(
                    title="核心发现",
                    content="",
                    findings=[{
                        "question": "A和B有差异吗？",
                        "conclusion_plain": "有显著差异",
                        "p_value": 0.03,
                        "effect_size": 0.4,
                        "effect_type": "cohen_d",
                        "significance": "significant",
                    }],
                ),
            ],
        )
        gen = ReportGenerator()
        html = gen.generate_html(report, template_name="brief")
        assert "简要测试" in html
        assert "A和B有差异吗？" in html


# ── 边界情况测试 ──────────────────────────────────────────────


class TestEdgeCases:
    """边界情况：空数据、小样本、常数列、全 NaN 列"""

    # -- Profiling 边界 --

    def test_profile_empty_dataframe(self):
        df = pd.DataFrame()
        p = generate_profile(df)
        assert p["n_rows"] == 0
        assert p["quality_score"] == 0

    def test_profile_all_nan_column(self):
        df = pd.DataFrame({"x": [np.nan] * 10, "y": range(10)})
        p = generate_profile(df)
        assert p["columns"]["x"]["inferred_type"] == "unknown"

    def test_profile_single_row(self):
        df = pd.DataFrame({"x": [1], "y": ["a"]})
        p = generate_profile(df)
        assert p["n_rows"] == 1
        assert "columns" in p

    def test_profile_constant_column(self):
        df = pd.DataFrame({"x": [5.0] * 20, "y": range(20)})
        p = generate_profile(df)
        # 常数列 std=0 但仍是 numeric 类型
        assert p["columns"]["x"]["inferred_type"] in ("numeric", "categorical")

    # -- Analysis 边界 --

    def test_ttest_insufficient_data(self):
        g1 = pd.Series([1])
        g2 = pd.Series([2])
        result = ttest(g1, g2)
        assert "error" in result
        assert result["error"] == "insufficient_data"

    def test_ttest_constant_group(self):
        g1 = pd.Series([5.0, 5.0, 5.0, 5.0])
        g2 = pd.Series([1.0, 2.0, 3.0, 4.0])
        result = ttest(g1, g2)
        assert "error" in result

    def test_correlation_insufficient_data(self):
        df = pd.DataFrame({"x": [1], "y": [2]})
        result = correlation(df, "x", "y")
        assert "error" in result

    def test_correlation_constant_column(self):
        df = pd.DataFrame({"x": [5.0] * 10, "y": range(10)})
        result = correlation(df, "x", "y")
        assert "error" in result

    def test_regression_insufficient_data(self):
        df = pd.DataFrame({"y": [1, 2], "x": [3, 4]})
        result = regression(df, "y", ["x"])
        assert "error" in result

    def test_regression_constant_target(self):
        df = pd.DataFrame({"y": [5.0] * 10, "x": range(10)})
        result = regression(df, "y", ["x"])
        assert "error" in result

    def test_regression_constant_feature(self):
        df = pd.DataFrame({"y": range(10, 20), "x": [3.0] * 10})
        result = regression(df, "y", ["x"])
        assert "error" in result

    def test_anova_insufficient_data(self):
        df = pd.DataFrame({"y": [1], "g": ["A"]})
        result = anova(df, "y", "g")
        assert "error" in result

    def test_chi_square_insufficient_data(self):
        df = pd.DataFrame({"g": ["A"], "r": ["yes"]})
        result = chi_square(df, "g", "r")
        assert "error" in result

    # -- Cleaning 边界 --

    def test_clean_empty_dataframe(self):
        df = pd.DataFrame()
        df_clean, report = clean_data(df, auto_strategy=True)
        assert len(df_clean) == 0
        assert report.total_rows_original == 0

    def test_outliers_iqr_constant_column(self):
        df = pd.DataFrame({"x": [5.0] * 20})
        outliers = detect_outliers_iqr(df)
        assert outliers["x"]["count"] == 0
        assert "零方差" in outliers["x"].get("note", "")

    def test_outliers_zscore_constant_column(self):
        df = pd.DataFrame({"x": [5.0] * 20})
        outliers = detect_outliers_zscore(df)
        assert outliers["x"]["count"] == 0
        assert "零方差" in outliers["x"].get("note", "")

    def test_suggest_strategy_no_missing(self):
        df = pd.DataFrame({"x": [1, 2, 3]})
        strategy, reason = suggest_cleaning_strategy(df, "x", null_rate=0)
        # 无缺失 → 返回某种策略（不应崩溃）
        assert isinstance(strategy, CleaningStrategy)
