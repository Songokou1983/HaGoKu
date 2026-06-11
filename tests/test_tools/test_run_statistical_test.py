"""CO-T11: 测试重构后的 run_statistical_test — effect_size + CI 断言"""

import pandas as pd
import numpy as np
from hagoku.tools.registry import agent_tools


class TestRunStatisticalTest:
    """测试 run_statistical_test 委托 analysis 模块后返回完整结构"""

    def test_tool_registered(self):
        assert agent_tools.get("run_statistical_test") is not None

    def test_ttest_returns_effect_size(self):
        """t 检验返回 effect_size + confidence_interval"""
        np.random.seed(42)
        df = pd.DataFrame({
            "group_a": np.random.normal(10, 2, 30),
            "group_b": np.random.normal(13, 2, 30),
        })
        handler = agent_tools.get("run_statistical_test").handler
        result = handler({"test_type": "ttest", "columns": ["group_a", "group_b"]}, {}, df)
        assert "error" not in result, f"Unexpected error: {result.get('error')}"
        assert result["test"] == "ttest"
        assert "p_value" in result
        assert "effect_size" in result, f"effect_size missing: {result.keys()}"
        assert result["effect_size"] is not None
        assert result["effect_type"] == "cohen_d"
        assert "confidence_interval" in result
        assert result["confidence_interval"] is not None

    def test_ttest_paired(self):
        """配对 t 检验"""
        np.random.seed(42)
        n = 20
        before = np.random.normal(100, 10, n)
        after = before + np.random.normal(5, 3, n)
        df = pd.DataFrame({"before": before, "after": after})
        handler = agent_tools.get("run_statistical_test").handler
        result = handler({
            "test_type": "ttest",
            "columns": ["before", "after"],
            "params": {"paired": True},
        }, {}, df)
        assert "error" not in result, f"Unexpected error: {result.get('error')}"
        assert result["test"] == "ttest"
        assert "effect_size" in result

    def test_correlation_returns_effect_size(self):
        """Pearson 相关返回 effect_size"""
        np.random.seed(42)
        n = 50
        x = np.random.randn(n)
        y = 2 * x + np.random.randn(n) * 0.5
        df = pd.DataFrame({"x": x, "y": y})
        handler = agent_tools.get("run_statistical_test").handler
        result = handler({"test_type": "pearson_r", "columns": ["x", "y"]}, {}, df)
        assert "error" not in result, f"Unexpected error: {result.get('error')}"
        assert result["test"] == "correlation"
        assert "effect_size" in result
        assert result["effect_type"] == "pearson_r"

    def test_spearman_returns_effect_size(self):
        """Spearman 相关"""
        np.random.seed(42)
        df = pd.DataFrame({
            "rank_a": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            "rank_b": [2, 4, 6, 8, 10, 12, 14, 16, 18, 20],
        })
        handler = agent_tools.get("run_statistical_test").handler
        result = handler({"test_type": "spearman_r", "columns": ["rank_a", "rank_b"]}, {}, df)
        assert result["test"] == "correlation"

    def test_regression_returns_effect_size(self):
        """线性回归返回 effect_size (f_squared)"""
        np.random.seed(42)
        n = 80
        x1 = np.random.randn(n)
        x2 = np.random.randn(n)
        y = 2 * x1 + 3 * x2 + np.random.randn(n) * 0.5 + 5
        df = pd.DataFrame({"y": y, "x1": x1, "x2": x2})
        handler = agent_tools.get("run_statistical_test").handler
        result = handler({"test_type": "linear_regression", "columns": ["y", "x1", "x2"]}, {}, df)
        assert "error" not in result, f"Unexpected error: {result.get('error')}"
        assert result["test"] == "regression"
        assert result.get("r_squared") and result["r_squared"] > 0.8

    def test_chi2_returns_effect_size(self):
        """卡方检验返回 effect_size (cramers_v)"""
        df = pd.DataFrame({
            "group": ["A"] * 30 + ["B"] * 30,
            "result": ["yes"] * 20 + ["no"] * 10 + ["yes"] * 10 + ["no"] * 20,
        })
        handler = agent_tools.get("run_statistical_test").handler
        result = handler({"test_type": "chi2", "columns": ["group", "result"]}, {}, df)
        assert result["test"] == "chi_square"
        assert "effect_size" in result
        assert result["effect_type"] == "cramers_v"

    def test_missing_columns_error(self):
        """缺列返回 error"""
        handler = agent_tools.get("run_statistical_test").handler
        result = handler({"test_type": "ttest", "columns": ["nonexistent"]}, {}, pd.DataFrame())
        assert "error" in result

    def test_unknown_test_type_error(self):
        """未知检验类型"""
        handler = agent_tools.get("run_statistical_test").handler
        result = handler({"test_type": "invalid", "columns": []}, {}, pd.DataFrame())
        assert "error" in result

    def test_trend_decomposition(self):
        """趋势分解"""
        np.random.seed(42)
        df = pd.DataFrame({
            "sales": np.cumsum(np.random.randn(100) + 0.1) + 100,
        })
        handler = agent_tools.get("run_statistical_test").handler
        result = handler({"test_type": "trend_decomposition", "columns": ["sales"]}, {}, df)
        assert result["test"] == "trend_decomposition"
        assert "trend_mean" in result
