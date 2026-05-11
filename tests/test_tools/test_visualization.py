"""Tests for visualization module: insight charts and data overview charts"""

import numpy as np
import pandas as pd
import pytest

from hagoku.tools.visualization import (
    create_plot,
    generate_data_overview_charts,
    generate_insight_charts,
)


class TestCreatePlot:
    def test_scatter_plotly(self, tmp_path):
        """Scatter plot with Plotly"""
        np.random.seed(42)
        df = pd.DataFrame({"x": np.random.randn(50), "y": np.random.randn(50)})
        fpath = str(tmp_path / "scatter.html")
        fig = create_plot("scatter", df, x="x", y="y", output_path=fpath, interactive=True)
        assert fig is not None
        import os
        assert os.path.exists(fpath)

    def test_heatmap_plotly(self, tmp_path):
        """Heatmap with Plotly"""
        np.random.seed(42)
        df = pd.DataFrame({
            "a": np.random.randn(50),
            "b": np.random.randn(50),
            "c": np.random.randn(50),
        })
        fpath = str(tmp_path / "heatmap.html")
        fig = create_plot("heatmap", df, output_path=fpath, interactive=True)
        assert fig is not None

    def test_box_plotly(self, tmp_path):
        """Box plot with Plotly"""
        df = pd.DataFrame({
            "group": ["A"] * 30 + ["B"] * 30,
            "value": np.concatenate([np.random.randn(30), np.random.randn(30) + 1]),
        })
        fpath = str(tmp_path / "box.html")
        fig = create_plot("box", df, x="group", y="value", output_path=fpath, interactive=True)
        assert fig is not None


class TestGenerateInsightCharts:
    def test_hypothesis_test_chart(self, tmp_path):
        """Generate charts from hypothesis test results"""
        np.random.seed(42)
        df = pd.DataFrame({
            "group": ["A"] * 50 + ["B"] * 50,
            "value": np.concatenate([np.random.randn(50), np.random.randn(50) + 1]),
        })
        results = [{
            "analysis_type": "hypothesis_test",
            "raw_result": {
                "test": "ttest",
                "question": "不同 group 组的 value 有差异吗？",
                "target": "value",
                "group_col": "group",
                "p_value": 0.01,
                "effect_size": 0.8,
            },
        }]
        charts = generate_insight_charts(df, results, output_dir=str(tmp_path))
        assert len(charts) >= 1
        assert charts[0]["type"] == "inline_html"

    def test_correlation_chart(self, tmp_path):
        """Generate correlation scatter chart"""
        np.random.seed(42)
        df = pd.DataFrame({
            "x": np.random.randn(50),
            "y": np.random.randn(50),
        })
        results = [{
            "analysis_type": "correlation",
            "raw_result": {
                "test": "correlation",
                "question": "x 与 y 之间的关系？",
                "col1": "x",
                "col2": "y",
                "statistic": 0.5,
                "p_value": 0.01,
            },
        }]
        charts = generate_insight_charts(df, results, output_dir=str(tmp_path))
        assert len(charts) >= 1

    def test_empty_results(self, tmp_path):
        """Empty results should return empty charts"""
        df = pd.DataFrame({"x": [1, 2, 3]})
        charts = generate_insight_charts(df, [], output_dir=str(tmp_path))
        assert charts == []

    def test_unknown_analysis_type(self, tmp_path):
        """Unknown analysis type should not crash"""
        df = pd.DataFrame({"x": [1, 2, 3]})
        results = [{"analysis_type": "unknown_type", "raw_result": {}}]
        charts = generate_insight_charts(df, results, output_dir=str(tmp_path))
        assert charts == []


class TestGenerateDataOverviewCharts:
    def test_correlation_heatmap(self, tmp_path):
        """Generate correlation heatmap"""
        np.random.seed(42)
        df = pd.DataFrame({
            "a": np.random.randn(50),
            "b": np.random.randn(50),
            "c": np.random.randn(50),
        })
        charts = generate_data_overview_charts(df, output_dir=str(tmp_path))
        heatmap_charts = [c for c in charts if "热力图" in c.get("title", "")]
        assert len(heatmap_charts) >= 1

    def test_missing_pattern_chart(self, tmp_path):
        """Generate missing value pattern chart"""
        df = pd.DataFrame({
            "a": [1, 2, None, 4, 5],
            "b": [None, 2, 3, None, 5],
            "c": [1, 2, 3, 4, 5],
        })
        charts = generate_data_overview_charts(df, output_dir=str(tmp_path))
        missing_charts = [c for c in charts if "缺失" in c.get("title", "")]
        assert len(missing_charts) >= 1

    def test_no_missing_values(self, tmp_path):
        """No missing values → no missing chart"""
        df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        charts = generate_data_overview_charts(df, output_dir=str(tmp_path))
        missing_charts = [c for c in charts if "缺失" in c.get("title", "")]
        assert len(missing_charts) == 0
