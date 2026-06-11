"""CO-T28: 测试功效分析工具"""

from hagoku.tools.registry import agent_tools


class TestPowerTools:
    """测试 assess_statistical_power / required_sample_size / interpret_nonsignificant"""

    def test_assess_power_registered(self):
        assert agent_tools.get("assess_statistical_power") is not None
        assert agent_tools.get("required_sample_size") is not None
        assert agent_tools.get("interpret_nonsignificant") is not None

    def test_assess_power_ttest(self):
        """t 检验功效评估"""
        handler = agent_tools.get("assess_statistical_power").handler
        result = handler({"mode": "ttest", "n1": 30, "n2": 30, "effect_size": 0.5}, {}, None)
        assert "power" in result
        assert "test" in result
        assert result["test"] == "ttest"
        assert 0 < result["power"] < 1

    def test_assess_power_anova(self):
        """ANOVA 功效评估"""
        handler = agent_tools.get("assess_statistical_power").handler
        result = handler({"mode": "anova", "n_per_group": 20, "n_groups": 3, "effect_size": 0.25}, {}, None)
        assert "power" in result
        assert result["test"] == "anova"

    def test_assess_power_correlation(self):
        """相关分析功效"""
        handler = agent_tools.get("assess_statistical_power").handler
        result = handler({"mode": "correlation", "n": 50, "effect_size": 0.3}, {}, None)
        assert "power" in result
        assert 0 < result["power"] < 1

    def test_assess_power_regression(self):
        """回归功效"""
        handler = agent_tools.get("assess_statistical_power").handler
        result = handler({"mode": "regression", "n": 80, "n_predictors": 3, "effect_size": 0.15}, {}, None)
        assert "power" in result
        assert result["test"] == "regression"

    def test_required_sample_size_ttest(self):
        """所需样本量计算"""
        handler = agent_tools.get("required_sample_size").handler
        result = handler({"mode": "ttest", "effect_size": 0.5}, {}, None)
        assert "required_n" in result or "required_n1" in result
        assert result["effect_size"] == 0.5

    def test_required_sample_size_correlation(self):
        """相关分析所需样本量"""
        handler = agent_tools.get("required_sample_size").handler
        result = handler({"mode": "correlation", "effect_size": 0.3}, {}, None)
        assert "required_n" in result

    def test_interpret_nonsignificant_significant(self):
        """显著结果解读"""
        handler = agent_tools.get("interpret_nonsignificant").handler
        result = handler({
            "p_value": 0.01, "effect_size": 0.6, "effect_type": "cohen_d", "n": 100,
        }, {}, None)
        assert result["verdict"] == "significant"

    def test_interpret_nonsignificant_not_significant(self):
        """不显著结果解读"""
        handler = agent_tools.get("interpret_nonsignificant").handler
        result = handler({
            "p_value": 0.15, "effect_size": 0.1, "effect_type": "cohen_d", "n": 20,
        }, {}, None)
        assert result["verdict"] != "significant"

    def test_assess_power_invalid_mode(self):
        """无效 mode 返回 error"""
        handler = agent_tools.get("assess_statistical_power").handler
        result = handler({"mode": "invalid"}, {}, None)
        assert "error" in result

    def test_correct_multiple_comparisons_registered(self):
        """多重比较校正已注册"""
        assert agent_tools.get("correct_multiple_comparisons") is not None

    def test_correct_multiple_comparisons_bh(self):
        """BH 校正"""
        handler = agent_tools.get("correct_multiple_comparisons").handler
        result = handler({
            "p_values": [0.001, 0.01, 0.03, 0.08, 0.20],
            "method": "bh",
        }, {}, None)
        assert "adjusted_p" in result
        assert len(result["adjusted_p"]) == 5

    def test_correct_multiple_comparisons_bonferroni(self):
        """Bonferroni 校正"""
        handler = agent_tools.get("correct_multiple_comparisons").handler
        result = handler({
            "p_values": [0.001, 0.01, 0.05, 0.50],
            "method": "bonferroni",
        }, {}, None)
        assert result["method"] == "bonferroni"
        assert "n_significant" in result
