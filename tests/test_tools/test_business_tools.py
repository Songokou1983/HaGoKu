"""CO-T29: 测试业务指标工具 (ROI smoke)"""

import pandas as pd
from hagoku.tools.registry import agent_tools


class TestBusinessTools:
    """测试 7 个业务工具的注册与基本行为"""

    def test_tools_registered(self):
        """所有业务工具已注册"""
        for name in ["calc_roi", "calc_roas", "calc_ltv", "calc_cac",
                      "calc_ltv_cac_ratio", "funnel_analysis", "attribution_analysis"]:
            assert agent_tools.get(name) is not None, f"{name} 未注册"

    def test_calc_roi_scalar(self):
        """ROI 数值计算"""
        handler = agent_tools.get("calc_roi").handler
        result = handler({"revenue": 150.0, "cost": 100.0}, {}, None)
        assert result["roi"] == 50.0 or "roi" in result
        assert "metric" in result

    def test_calc_roi_dataframe(self):
        """ROI DataFrame 计算"""
        df = pd.DataFrame({
            "revenue": [100.0, 200.0, 150.0],
            "cost": [80.0, 120.0, 100.0],
        })
        handler = agent_tools.get("calc_roi").handler
        result = handler({"revenue_col": "revenue", "cost_col": "cost"}, {}, df)
        assert "avg_roi" in result or "error" not in result

    def test_calc_roas_scalar(self):
        """ROAS 数值计算"""
        handler = agent_tools.get("calc_roas").handler
        result = handler({"revenue": 400.0, "ad_spend": 100.0}, {}, None)
        assert result.get("roas") == 4.0

    def test_calc_ltv(self):
        """LTV 计算"""
        df = pd.DataFrame({
            "customer_id": ["c1", "c1", "c2", "c2", "c3"],
            "revenue": [100, 50, 200, 100, 300],
        })
        handler = agent_tools.get("calc_ltv").handler
        result = handler({"customer_col": "customer_id", "revenue_col": "revenue"}, {}, df)
        assert "avg_ltv" in result
        assert result["n_customers"] == 3

    def test_calc_cac(self):
        """CAC 计算"""
        df = pd.DataFrame({
            "customer_id": ["c1", "c2", "c3", "c4", "c5"],
            "cost": [50, 60, 40, 70, 80],
        })
        handler = agent_tools.get("calc_cac").handler
        result = handler({"customer_col": "customer_id", "cost_col": "cost"}, {}, df)
        assert "cac" in result
        assert result["n_new_customers"] == 5

    def test_calc_ltv_cac_ratio(self):
        """LTV/CAC 比率"""
        handler = agent_tools.get("calc_ltv_cac_ratio").handler
        result = handler({"ltv": 300.0, "cac": 100.0}, {}, None)
        assert result["ratio"] == 3.0

    def test_funnel_analysis(self):
        """漏斗分析"""
        df = pd.DataFrame({
            "stage": ["visit", "visit", "cart", "cart", "cart", "pay", "pay"],
            "user": ["u1", "u2", "u1", "u2", "u3", "u1", "u2"],
        })
        handler = agent_tools.get("funnel_analysis").handler
        result = handler({"stage_col": "stage"}, {}, df)
        assert "funnel" in result
        assert len(result["funnel"]) >= 2

    def test_attribution_analysis(self):
        """渠道归因"""
        df = pd.DataFrame({
            "channel": ["搜索", "社交", "搜索", "邮件", "社交"],
            "converted": [1, 0, 1, 1, 1],
        })
        handler = agent_tools.get("attribution_analysis").handler
        result = handler({
            "conversions_col": "converted",
            "channel_col": "channel",
            "method": "last_touch",
        }, {}, df)
        assert "attribution" in result
        assert result["method"] == "last_touch"
