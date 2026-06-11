"""CO-T27: 测试 check_test_assumptions 工具注册与行为"""

import pandas as pd
import numpy as np
from hagoku.tools.registry import agent_tools


class TestCheckTestAssumptions:
    """测试 check_test_assumptions 工具"""

    def test_tool_registered(self):
        """工具已在注册表"""
        tool = agent_tools.get("check_test_assumptions")
        assert tool is not None
        assert tool.name == "check_test_assumptions"

    def test_ttest_assumptions(self):
        """t 检验假设检查"""
        np.random.seed(42)
        df = pd.DataFrame({
            "value": np.concatenate([
                np.random.normal(10, 2, 30),
                np.random.normal(13, 2, 30),
            ]),
            "group": ["A"] * 30 + ["B"] * 30,
        })
        handler = agent_tools.get("check_test_assumptions").handler
        result = handler(
            {"test_type": "ttest", "group_col": "group", "target": "value"},
            {}, df,
        )
        assert "assumptions" in result
        assert result["test_type"] == "ttest"
        assert "normality_group1" in result["assumptions"] or "normality_group2" in result["assumptions"]

    def test_correlation_assumptions(self):
        """相关分析假设检查"""
        np.random.seed(42)
        df = pd.DataFrame({
            "x": np.random.normal(0, 1, 30),
            "y": np.random.normal(0, 1, 30),
        })
        handler = agent_tools.get("check_test_assumptions").handler
        result = handler(
            {"test_type": "correlation", "col1": "x", "col2": "y", "method": "pearson"},
            {}, df,
        )
        assert "assumptions" in result
        assert result["test_type"] == "correlation"

    def test_regression_assumptions(self):
        """回归假设检查"""
        np.random.seed(42)
        n = 50
        x1 = np.random.randn(n)
        x2 = np.random.randn(n)
        y = 2 * x1 + 3 * x2 + np.random.randn(n) * 0.5
        df = pd.DataFrame({"y": y, "x1": x1, "x2": x2})
        handler = agent_tools.get("check_test_assumptions").handler
        result = handler(
            {"test_type": "regression", "target": "y", "features": ["x1", "x2"]},
            {}, df,
        )
        assert "assumptions" in result
        assert result["test_type"] == "regression"

    def test_missing_test_type_returns_error(self):
        """缺少 test_type 返回错误"""
        tool = agent_tools.get("check_test_assumptions")
        result = tool.handler({"test_type": ""}, {}, None)
        assert "error" in result

    def test_chi_square_assumptions(self):
        """卡方检验假设检查"""
        df = pd.DataFrame({
            "g1": ["A"] * 20 + ["B"] * 20 + ["C"] * 20,
            "g2": ["yes"] * 15 + ["no"] * 15 + ["yes"] * 15 + ["no"] * 15,
        })
        handler = agent_tools.get("check_test_assumptions").handler
        result = handler(
            {"test_type": "chi_square", "col1": "g1", "col2": "g2"},
            {}, df,
        )
        assert "assumptions" in result
        assert result["test_type"] == "chi_square"
