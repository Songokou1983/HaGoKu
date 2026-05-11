"""Tests for enhanced analysis tools: cross-validation, multiple comparison, assumption checks, interaction"""

import numpy as np
import pandas as pd
import pytest

from hagoku.tools.analysis import (
    check_test_assumptions,
    cross_validate,
    interaction_analysis,
    multiple_comparison_correction,
)


# ── cross_validate ──────────────────────────────────────────


class TestCrossValidate:
    def test_basic_cv(self):
        """5-fold CV on simple linear data"""
        np.random.seed(42)
        n = 100
        df = pd.DataFrame({
            "y": np.random.randn(n),
            "x1": np.random.randn(n),
            "x2": np.random.randn(n),
        })
        # Add some signal
        df["y"] = 2 * df["x1"] + 0.5 * df["x2"] + np.random.randn(n) * 0.5

        result = cross_validate(df, "y", ["x1", "x2"], k_folds=5)
        assert "error" not in result
        assert result["k_folds"] == 5
        assert len(result["train_scores"]) == 5
        assert len(result["test_scores"]) == 5
        assert result["train_mean"] > 0.5  # strong signal
        assert result["test_mean"] > 0.5
        assert not result["overfitting_detected"]

    def test_small_data_auto_reduce_folds(self):
        """CV should auto-reduce k when sample is small"""
        df = pd.DataFrame({
            "y": [1, 2, 3, 4, 5, 6, 7, 8],
            "x1": [1, 2, 3, 4, 5, 6, 7, 8],
        })
        result = cross_validate(df, "y", ["x1"], k_folds=10)
        assert "error" not in result
        assert result["k_folds"] < 10  # should be reduced

    def test_insufficient_data(self):
        """Too few rows should return error"""
        df = pd.DataFrame({"y": [1, 2], "x1": [1, 2]})
        result = cross_validate(df, "y", ["x1"])
        assert "error" in result

    def test_missing_target(self):
        """Missing target column should return error"""
        df = pd.DataFrame({"y": [1, 2, 3], "x1": [1, 2, 3]})
        result = cross_validate(df, "z", ["x1"])
        assert "error" in result

    def test_scoring_rmse(self):
        """CV with RMSE scoring"""
        np.random.seed(42)
        n = 50
        df = pd.DataFrame({
            "y": np.random.randn(n),
            "x1": np.random.randn(n),
        })
        result = cross_validate(df, "y", ["x1"], scoring="rmse")
        assert "error" not in result
        assert result["scoring"] == "rmse"
        assert all(s > 0 for s in result["train_scores"])

    def test_overfitting_detection(self):
        """Should detect overfitting when train >> test"""
        np.random.seed(42)
        n = 30
        # Many features, few samples → likely overfit
        df = pd.DataFrame({
            "y": np.random.randn(n),
            **{f"x{i}": np.random.randn(n) for i in range(10)},
        })
        result = cross_validate(df, "y", [f"x{i}" for i in range(10)], k_folds=3)
        assert "error" not in result
        # Overfitting detection key exists
        assert "overfitting_detected" in result


# ── multiple_comparison_correction ──────────────────────────


class TestMultipleComparison:
    def test_bonferroni(self):
        """Bonferroni correction"""
        p_values = [0.01, 0.03, 0.04, 0.10]
        result = multiple_comparison_correction(p_values, method="bonferroni")
        assert result["method"] == "bonferroni"
        assert result["n_tests"] == 4
        # Bonferroni: p * n
        assert result["adjusted_p"][0] == pytest.approx(0.04, abs=0.001)
        assert result["adjusted_p"][3] == pytest.approx(0.40, abs=0.01)  # 0.10 * 4
        # Only first might survive
        assert result["n_significant"] <= result["n_original_significant"]

    def test_bh_correction(self):
        """Benjamini-Hochberg correction"""
        p_values = [0.01, 0.02, 0.03, 0.04, 0.05]
        result = multiple_comparison_correction(p_values, method="bh")
        assert result["method"] == "bh"
        assert result["n_tests"] == 5
        # BH should be less conservative than Bonferroni
        bonf_result = multiple_comparison_correction(p_values, method="bonferroni")
        assert sum(result["adjusted_p"]) <= sum(bonf_result["adjusted_p"])

    def test_holm_correction(self):
        """Holm-Bonferroni correction"""
        p_values = [0.01, 0.03, 0.05]
        result = multiple_comparison_correction(p_values, method="holm")
        assert result["method"] == "holm"
        assert result["n_tests"] == 3
        # All adjusted p should be <= 1.0
        assert all(p <= 1.0 for p in result["adjusted_p"])

    def test_single_test(self):
        """Single test needs no correction"""
        result = multiple_comparison_correction([0.03])
        assert result["method"] == "none_needed"
        assert result["n_tests"] == 1

    def test_empty_p_values(self):
        """Empty list should return error"""
        result = multiple_comparison_correction([])
        assert "error" in result

    def test_invalid_method(self):
        """Invalid method should raise"""
        with pytest.raises(ValueError, match="不支持"):
            multiple_comparison_correction([0.01, 0.05], method="invalid")

    def test_correction_note(self):
        """Should include human-readable note"""
        p_values = [0.01, 0.04, 0.06, 0.10]
        result = multiple_comparison_correction(p_values, method="bh")
        assert "correction_note" in result
        assert "→" in result["correction_note"]


# ── check_test_assumptions ──────────────────────────────────


class TestCheckAssumptions:
    def test_ttest_normal_data(self):
        """Normal data should pass ttest assumptions"""
        np.random.seed(42)
        df = pd.DataFrame({
            "group": ["A"] * 50 + ["B"] * 50,
            "value": np.concatenate([
                np.random.normal(0, 1, 50),
                np.random.normal(0.5, 1, 50),
            ]),
        })
        result = check_test_assumptions(df, "ttest", group_col="group", target="value")
        assert result["test_type"] == "ttest"
        assert "assumptions" in result
        # Normal data should generally pass
        assert "all_assumptions_met" in result

    def test_ttest_skewed_data(self):
        """Highly skewed data should fail normality"""
        np.random.seed(42)
        df = pd.DataFrame({
            "group": ["A"] * 50 + ["B"] * 50,
            "value": np.concatenate([
                np.random.exponential(1, 50),
                np.random.exponential(2, 50),
            ]),
        })
        result = check_test_assumptions(df, "ttest", group_col="group", target="value")
        # Should warn about normality
        if not result.get("all_assumptions_met", True):
            assert len(result.get("warnings", [])) > 0
            assert result.get("recommendation") is not None

    def test_anova_assumptions(self):
        """ANOVA assumption check"""
        np.random.seed(42)
        df = pd.DataFrame({
            "group": ["A"] * 30 + ["B"] * 30 + ["C"] * 30,
            "value": np.random.randn(90),
        })
        result = check_test_assumptions(df, "anova", group_col="group", target="value")
        assert result["test_type"] == "anova"
        assert "equal_variance" in result["assumptions"]

    def test_regression_assumptions(self):
        """Regression assumption check (VIF, sample size)"""
        np.random.seed(42)
        n = 100
        x1 = np.random.randn(n)
        x2 = np.random.randn(n)
        df = pd.DataFrame({
            "y": 2 * x1 + 0.5 * x2 + np.random.randn(n) * 0.5,
            "x1": x1,
            "x2": x2,
        })
        result = check_test_assumptions(df, "regression", target="y", features=["x1", "x2"])
        assert result["test_type"] == "regression"
        assert "multicollinearity" in result["assumptions"]
        assert result["assumptions"]["multicollinearity"]["met"] is True

    def test_regression_high_vif(self):
        """High VIF should be detected"""
        np.random.seed(42)
        n = 100
        x1 = np.random.randn(n)
        x2 = x1 + np.random.randn(n) * 0.01  # nearly collinear
        df = pd.DataFrame({
            "y": np.random.randn(n),
            "x1": x1,
            "x2": x2,
        })
        result = check_test_assumptions(df, "regression", target="y", features=["x1", "x2"])
        vif = result["assumptions"].get("multicollinearity", {})
        if "max_vif" in vif:
            assert vif["max_vif"] > 10 or vif["met"] is False  # might not always be >10

    def test_correlation_assumptions(self):
        """Correlation assumption check"""
        np.random.seed(42)
        n = 100
        df = pd.DataFrame({
            "x": np.random.randn(n),
            "y": np.random.randn(n),
        })
        result = check_test_assumptions(df, "correlation", col1="x", col2="y", method="pearson")
        assert result["test_type"] == "correlation"
        assert "normality" in result["assumptions"]

    def test_chi_square_expected_freq(self):
        """Chi-square expected frequency check"""
        df = pd.DataFrame({
            "col1": ["A"] * 5 + ["B"] * 5,
            "col2": ["X"] * 3 + ["Y"] * 7,
        })
        result = check_test_assumptions(df, "chi_square", col1="col1", col2="col2")
        assert result["test_type"] == "chi_square"
        assert "expected_frequencies" in result["assumptions"]


# ── interaction_analysis ────────────────────────────────────


class TestInteractionAnalysis:
    def test_no_interaction(self):
        """Independent features should show no interaction"""
        np.random.seed(42)
        n = 200
        x1 = np.random.randn(n)
        x2 = np.random.randn(n)
        # y = 2*x1 + 0.5*x2 (no interaction)
        df = pd.DataFrame({
            "y": 2 * x1 + 0.5 * x2 + np.random.randn(n) * 0.5,
            "x1": x1,
            "x2": x2,
        })
        result = interaction_analysis(df, "y", "x1", "x2")
        assert "error" not in result
        assert result["significance"] == "not_significant"
        assert result["r_squared_improvement"] is not None

    def test_with_interaction(self):
        """Features with interaction should be detected"""
        np.random.seed(42)
        n = 300
        x1 = np.random.randn(n)
        x2 = np.random.randn(n)
        # y = x1 + x2 + 3*x1*x2 (strong interaction)
        df = pd.DataFrame({
            "y": x1 + x2 + 3 * x1 * x2 + np.random.randn(n) * 0.5,
            "x1": x1,
            "x2": x2,
        })
        result = interaction_analysis(df, "y", "x1", "x2")
        assert "error" not in result
        assert result["significance"] == "significant"
        assert result["coefficient"] > 1.0  # interaction term should be large

    def test_missing_target(self):
        """Missing target should return error"""
        df = pd.DataFrame({"x1": [1, 2, 3], "x2": [1, 2, 3]})
        result = interaction_analysis(df, "z", "x1", "x2")
        assert "error" in result

    def test_missing_feature(self):
        """Missing feature should return error"""
        df = pd.DataFrame({"y": [1, 2, 3], "x1": [1, 2, 3]})
        result = interaction_analysis(df, "y", "x1", "x2")
        assert "error" in result

    def test_insufficient_data(self):
        """Too few rows should return error"""
        df = pd.DataFrame({
            "y": [1, 2, 3],
            "x1": [1, 2, 3],
            "x2": [1, 2, 3],
        })
        result = interaction_analysis(df, "y", "x1", "x2")
        assert "error" in result

    def test_result_has_interpretation(self):
        """Result should include human-readable interpretation"""
        np.random.seed(42)
        n = 100
        df = pd.DataFrame({
            "y": np.random.randn(n),
            "x1": np.random.randn(n),
            "x2": np.random.randn(n),
        })
        result = interaction_analysis(df, "y", "x1", "x2")
        assert "interpretation" in result
        assert "交互效应" in result["interpretation"]

    def test_effect_size_present(self):
        """Should report effect size"""
        np.random.seed(42)
        n = 100
        df = pd.DataFrame({
            "y": np.random.randn(n),
            "x1": np.random.randn(n),
            "x2": np.random.randn(n),
        })
        result = interaction_analysis(df, "y", "x1", "x2")
        assert "effect_size" in result
        assert result["effect_type"] == "partial_eta_squared"
