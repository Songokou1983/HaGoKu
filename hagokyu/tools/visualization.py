"""HaGoKu 可视化 — 吸引力层的实现 + 洞察图/趋势图/对比图"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..log import get_logger

logger = get_logger("visualization")


def create_plot(
    plot_type: str,
    data: pd.DataFrame | dict[str, Any],
    *,
    x: str | None = None,
    y: str | None = None,
    color: str | None = None,
    title: str = "",
    xlabel: str = "",
    ylabel: str = "",
    output_path: str | Path | None = None,
    interactive: bool = True,
    **kwargs: Any,
) -> Any:
    """
    统一绘图入口

    Args:
        plot_type: 图表类型 (scatter / line / bar / histogram / box / heatmap / qq / residual)
        data: 数据（DataFrame 或图表数据字典）
        x: X 轴列名
        y: Y 轴列名
        color: 分组/颜色列名
        title: 图表标题
        xlabel: X 轴标签
        ylabel: Y 轴标签
        output_path: 输出文件路径
        interactive: 是否生成交互式图表 (Plotly)
        **kwargs: 额外参数

    Returns:
        图表对象
    """
    if interactive:
        return _plotly_plot(plot_type, data, x=x, y=y, color=color,
                           title=title, xlabel=xlabel, ylabel=ylabel,
                           output_path=output_path, **kwargs)
    else:
        return _matplotlib_plot(plot_type, data, x=x, y=y, color=color,
                               title=title, xlabel=xlabel, ylabel=ylabel,
                               output_path=output_path, **kwargs)


def _plotly_plot(
    plot_type: str,
    data: pd.DataFrame | dict[str, Any],
    *,
    x: str | None = None,
    y: str | None = None,
    color: str | None = None,
    title: str = "",
    xlabel: str = "",
    ylabel: str = "",
    output_path: str | Path | None = None,
    **kwargs: Any,
) -> Any:
    """Plotly 交互式图表"""
    import plotly.express as px
    import plotly.graph_objects as go

    # 图表数据字典 → plotly traces
    if isinstance(data, dict):
        return _plotly_from_data_dict(data, title=title, output_path=output_path)

    # DataFrame 绘图
    plot_funcs = {
        "scatter": px.scatter,
        "line": px.line,
        "bar": px.bar,
        "histogram": px.histogram,
        "box": px.box,
        "violin": px.violin,
        "scatter_matrix": px.scatter_matrix,
    }

    if plot_type == "heatmap":
        # 相关性热力图
        numeric_df = data.select_dtypes(include=[np.number])
        corr = numeric_df.corr()
        fig = px.imshow(
            corr.round(3),
            title=title or "相关性热力图",
            color_continuous_scale="RdBu_r",
            zmin=-1, zmax=1,
            text_auto=True,
        )
    elif plot_type in plot_funcs:
        fig = plot_funcs[plot_type](
            data, x=x, y=y, color=color,
            title=title,
            labels={x: xlabel, y: ylabel} if x and y else None,
            **kwargs,
        )
    elif plot_type == "qq":
        # Q-Q 图
        from scipy import stats

        if y and isinstance(data, pd.DataFrame):
            sample = data[y].dropna()
        else:
            sample = data

        (osm, osr), (slope, intercept, _) = stats.probplot(sample, dist="norm")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=osm, y=osr, mode="markers", name="样本"))
        fig.add_trace(go.Scatter(x=osm, y=slope * osm + intercept, mode="lines", name="参考线"))
        fig.update_layout(title=title or "Q-Q Plot", xaxis_title="理论分位数", yaxis_title="样本分位数")
    elif plot_type == "residual":
        # 残差图
        fig = go.Figure()
        if isinstance(data, dict):
            fitted = data.get("fitted", data.get("x", []))
            residuals = data.get("residuals", data.get("y", []))
        else:
            return None

        fig.add_trace(go.Scatter(x=fitted, y=residuals, mode="markers", name="残差"))
        fig.add_hline(y=0, line_dash="dash", line_color="red")
        fig.update_layout(
            title=title or "残差 vs 拟合值",
            xaxis_title=xlabel or "拟合值",
            yaxis_title=ylabel or "残差",
        )
    else:
        raise ValueError(f"不支持的图表类型: {plot_type}")

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.write_html(str(output_path))

    return fig


def _plotly_from_data_dict(
    data: dict[str, Any],
    *,
    title: str = "",
    output_path: str | Path | None = None,
) -> Any:
    """从 diagnostics.py 返回的数据字典创建 Plotly 图表"""
    import plotly.graph_objects as go

    chart_type = data.get("type", "scatter")
    fig = go.Figure()

    if chart_type == "scatter":
        x_data = data.get("x", {}).get("data", [])
        y_data = data.get("y", {}).get("data", [])
        fig.add_trace(go.Scatter(x=x_data, y=y_data, mode="markers"))
        if "hline" in data:
            fig.add_hline(y=data["hline"], line_dash="dash", line_color="red")
        fig.update_layout(
            title=data.get("title", title),
            xaxis_title=data.get("x", {}).get("label", ""),
            yaxis_title=data.get("y", {}).get("label", ""),
        )

    elif chart_type == "qq":
        theoretical = data.get("theoretical", [])
        sample = data.get("sample", [])
        fit = data.get("fit_line", {})
        fig.add_trace(go.Scatter(x=theoretical, y=sample, mode="markers", name="样本"))
        if fit:
            slope, intercept = fit.get("slope", 1), fit.get("intercept", 0)
            fig.add_trace(go.Scatter(
                x=theoretical,
                y=[slope * t + intercept for t in theoretical],
                mode="lines", name="参考线",
            ))
        fig.update_layout(title=data.get("title", "Q-Q Plot"))

    elif chart_type == "bar":
        x_data = data.get("x", {}).get("data", [])
        y_data = data.get("y", {}).get("data", [])
        fig.add_trace(go.Bar(x=x_data, y=y_data))
        if "hline" in data:
            fig.add_hline(y=data["hline"], line_dash="dash", line_color="red")
        fig.update_layout(
            title=data.get("title", title),
            xaxis_title=data.get("x", {}).get("label", ""),
            yaxis_title=data.get("y", {}).get("label", ""),
        )

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.write_html(str(output_path))

    return fig


def _matplotlib_plot(
    plot_type: str,
    data: pd.DataFrame | dict[str, Any],
    *,
    x: str | None = None,
    y: str | None = None,
    color: str | None = None,
    title: str = "",
    xlabel: str = "",
    ylabel: str = "",
    output_path: str | Path | None = None,
    **kwargs: Any,
) -> Any:
    """Matplotlib 静态图表"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=kwargs.get("figsize", (10, 6)))

    if isinstance(data, pd.DataFrame):
        if plot_type == "scatter":
            ax.scatter(data[x], data[y], alpha=0.6)
        elif plot_type == "line":
            ax.plot(data[x], data[y])
        elif plot_type == "bar":
            ax.bar(data[x], data[y])
        elif plot_type == "histogram":
            ax.hist(data[y] if y else data[x], bins=kwargs.get("bins", 30))
        elif plot_type == "box":
            if color:
                groups = data.groupby(color)[y]
                ax.boxplot([g.values for _, g in groups], label=[g for g, _ in groups])
            else:
                ax.boxplot(data[y])
        elif plot_type == "heatmap":
            numeric_df = data.select_dtypes(include=[np.number])
            im = ax.imshow(numeric_df.corr(), cmap="RdBu_r", vmin=-1, vmax=1)
            ax.set_xticks(range(len(numeric_df.columns)))
            ax.set_yticks(range(len(numeric_df.columns)))
            ax.set_xticklabels(numeric_df.columns, rotation=45)
            ax.set_yticklabels(numeric_df.columns)
            fig.colorbar(im)
    elif isinstance(data, dict):
        chart_type = data.get("type", "scatter")
        if chart_type == "scatter":
            x_data = data.get("x", {}).get("data", [])
            y_data = data.get("y", {}).get("data", [])
            ax.scatter(x_data, y_data, alpha=0.6)
            if "hline" in data:
                ax.axhline(y=data["hline"], linestyle="--", color="red")
        elif chart_type == "qq":
            theoretical = data.get("theoretical", [])
            sample = data.get("sample", [])
            ax.scatter(theoretical, sample, alpha=0.6)
            fit = data.get("fit_line", {})
            if fit:
                slope, intercept = fit.get("slope", 1), fit.get("intercept", 0)
                ax.plot(theoretical, [slope * t + intercept for t in theoretical], "r--")

    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    plt.tight_layout()

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(output_path), dpi=150, bbox_inches="tight")
        plt.close(fig)

    return fig


# ── 洞察图/趋势图/对比图 — 分析驱动的图表生成 ───────────────


def generate_insight_charts(
    df: pd.DataFrame,
    results: list[dict[str, Any]],
    context: dict[str, Any] | None = None,
    output_dir: str | Path | None = None,
    *,
    interactive: bool = True,
) -> list[dict[str, Any]]:
    """
    从分析结果自动生成洞察图

    根据分析类型选择最合适的可视化：
    - regression: 回归拟合图 + 残差诊断图
    - hypothesis_test: 分组对比图 (box/violin)
    - correlation: 相关散点图
    - trend_analysis: 时间趋势图
    - interaction: 交互效应图

    Args:
        df: 清洗后数据
        results: 分析结果列表（dict 格式，来自 AnalysisResult.raw_result）
        context: 数据上下文（可选，含 column_semantics 等）
        output_dir: 图表输出目录
        interactive: 是否交互式图表

    Returns:
        图表元数据列表，可附加到 ReportSection.charts
    """
    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

    charts: list[dict[str, Any]] = []

    for i, result in enumerate(results):
        analysis_type = result.get("analysis_type", "")
        raw = result.get("raw_result", result)

        try:
            if analysis_type == "regression":
                chart = _chart_regression(df, raw, i, output_dir, interactive)
                if chart:
                    charts.extend(chart)

            elif analysis_type in ("hypothesis_test", "hypothesis_test_mann_whitney", "hypothesis_test_kruskal_wallis"):
                chart = _chart_hypothesis_test(df, raw, i, output_dir, interactive)
                if chart:
                    charts.extend(chart)

            elif analysis_type == "correlation":
                chart = _chart_correlation(df, raw, i, output_dir, interactive)
                if chart:
                    charts.extend(chart)

            elif analysis_type == "trend_analysis":
                chart = _chart_trend(df, raw, i, output_dir, interactive)
                if chart:
                    charts.extend(chart)

            elif analysis_type == "interaction_analysis":
                chart = _chart_interaction(df, raw, i, output_dir, interactive)
                if chart:
                    charts.extend(chart)

        except Exception as e:
            # 图表生成失败不应阻止报告生成
            logger.warning("Chart generation failed for result %d (%s): %s", i, analysis_type, e)
            continue

    return charts


def _chart_regression(
    df: pd.DataFrame,
    raw: dict[str, Any],
    idx: int,
    output_dir: Path | None,
    interactive: bool,
) -> list[dict[str, Any]]:
    """回归分析图表：拟合图 + 残差图"""
    charts = []
    coeffs = raw.get("coefficients", {})
    # 找最显著的预测变量
    p_values = raw.get("p_values", {})
    features = [k for k in coeffs.keys() if k != "const" and k in df.columns]

    if not features:
        return charts

    # 选最显著的特征做图
    best_feature = min(features, key=lambda f: p_values.get(f, 1.0)) if features else None
    if best_feature is None:
        return charts

    # 1. 拟合散点图
    target = raw.get("target", "")
    if not target:
        # 从 question 推断
        return charts

    fname = f"regression_scatter_{idx}.html" if interactive else f"regression_scatter_{idx}.png"
    fpath = str(output_dir / fname) if output_dir else None

    fig = create_plot(
        "scatter",
        df,
        x=best_feature,
        y=target,
        title=f"回归拟合: {target} vs {best_feature}",
        xlabel=best_feature,
        ylabel=target,
        output_path=fpath,
        interactive=interactive,
    )
    chart_entry = {
        "type": "image" if not interactive else "html",
        "path": fpath,
        "title": f"回归拟合: {target} vs {best_feature}",
    }
    # 内嵌 HTML（优先于 iframe）
    if interactive and fig is not None:
        try:
            chart_entry["type"] = "inline_html"
            chart_entry["html_snippet"] = fig.to_html(full_html=False, include_plotlyjs="cdn")
        except Exception as e:
            logger.warning("Failed to generate inline HTML for regression chart: %s", e)
    charts.append(chart_entry)

    # 2. 残差诊断图提示
    diagnostics = raw.get("diagnostics", {})
    if diagnostics and "residual_pattern" in diagnostics:
        charts.append({
            "type": "placeholder",
            "title": "残差诊断图",
            "note": "残差诊断详见诊断章节",
        })

    return charts


def _chart_hypothesis_test(
    df: pd.DataFrame,
    raw: dict[str, Any],
    idx: int,
    output_dir: Path | None,
    interactive: bool,
) -> list[dict[str, Any]]:
    """假设检验图表：分组对比 violin/box"""
    charts = []

    # 元数据优先（由 AnalystAgent 注入）
    target = raw.get("target")
    group_col = raw.get("group_col")

    # 降级：从 question 解析
    if not target or not group_col:
        test_type = raw.get("test", "")
        q = raw.get("question", "") or ""
        if "的" in q and "组" in q:
            parts = q.split("组")
            group_hint = parts[0].replace("不同", "").strip()
            target_hint = parts[1].replace("有差异吗？", "").replace("有差异吗", "").strip()
            for col in df.columns:
                if col in group_hint or group_hint in col:
                    group_col = col
                    break
            for col in df.select_dtypes(include=[np.number]).columns:
                if col in target_hint or target_hint in col:
                    target = col
                    break
            if target or group_col:
                logger.warning("Hypothesis test chart: using question-parsed columns (metadata missing)")

    if not target or not group_col:
        return charts

    if target not in df.columns or group_col not in df.columns:
        return charts

    fname = f"hypothesis_comparison_{idx}.html" if interactive else f"hypothesis_comparison_{idx}.png"
    fpath = str(output_dir / fname) if output_dir else None

    fig = create_plot(
        "violin" if interactive else "box",
        df,
        x=group_col,
        y=target,
        color=group_col,
        title=f"分组对比: {target} by {group_col}",
        xlabel=group_col,
        ylabel=target,
        output_path=fpath,
        interactive=interactive,
    )
    chart_entry = {
        "type": "image" if not interactive else "html",
        "path": fpath,
        "title": f"分组对比: {target} by {group_col}",
    }
    if interactive and fig is not None:
        try:
            chart_entry["type"] = "inline_html"
            chart_entry["html_snippet"] = fig.to_html(full_html=False, include_plotlyjs="cdn")
        except Exception as e:
            logger.warning("Failed to generate inline HTML for hypothesis chart: %s", e)
    charts.append(chart_entry)

    return charts


def _chart_correlation(
    df: pd.DataFrame,
    raw: dict[str, Any],
    idx: int,
    output_dir: Path | None,
    interactive: bool,
) -> list[dict[str, Any]]:
    """相关性图表：散点图"""
    charts = []

    # 元数据优先
    col1 = raw.get("col1")
    col2 = raw.get("col2")

    # 降级：从 question 解析
    if not col1 or not col2:
        q = raw.get("question", "") or ""
        if "与" in q and "之间" in q:
            parts = q.split("与")
            if len(parts) == 2:
                hint1 = parts[0].strip()
                hint2 = parts[1].split("之间")[0].strip()
                for col in df.columns:
                    if col == hint1 or hint1 in col:
                        col1 = col
                    if col == hint2 or hint2 in col:
                        col2 = col
                if col1 or col2:
                    logger.warning("Correlation chart: using question-parsed columns (metadata missing)")

    if not col1 or not col2:
        return charts

    fname = f"correlation_scatter_{idx}.html" if interactive else f"correlation_scatter_{idx}.png"
    fpath = str(output_dir / fname) if output_dir else None

    fig = create_plot(
        "scatter",
        df,
        x=col1,
        y=col2,
        title=f"相关分析: {col1} vs {col2} (r={raw.get('statistic', 0):.3f})",
        xlabel=col1,
        ylabel=col2,
        output_path=fpath,
        interactive=interactive,
    )
    chart_entry = {
        "type": "image" if not interactive else "html",
        "path": fpath,
        "title": f"相关分析: {col1} vs {col2}",
    }
    if interactive and fig is not None:
        try:
            chart_entry["type"] = "inline_html"
            chart_entry["html_snippet"] = fig.to_html(full_html=False, include_plotlyjs="cdn")
        except Exception as e:
            logger.warning("Failed to generate inline HTML for correlation chart: %s", e)
    charts.append(chart_entry)

    return charts


def _chart_trend(
    df: pd.DataFrame,
    raw: dict[str, Any],
    idx: int,
    output_dir: Path | None,
    interactive: bool,
) -> list[dict[str, Any]]:
    """趋势分析图表：时间线图"""
    charts = []

    # 元数据优先
    time_col = raw.get("time_col")
    target = raw.get("target")

    # 降级：推断
    if not time_col:
        for col in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                time_col = col
                break
    if not target:
        q = raw.get("question", "") or ""
        if "的" in q:
            hint = q.split("的")[0].strip()
            for col in df.select_dtypes(include=[np.number]).columns:
                if col == hint or hint in col:
                    target = col
                    break
        if target and not time_col:
            logger.warning("Trend chart: target from question parse, time_col from dataframe scan (metadata missing)")

    if not time_col or not target:
        return charts

    # 排序后绘图
    df_sorted = df.sort_values(time_col)

    fname = f"trend_line_{idx}.html" if interactive else f"trend_line_{idx}.png"
    fpath = str(output_dir / fname) if output_dir else None

    fig = create_plot(
        "line",
        df_sorted,
        x=time_col,
        y=target,
        title=f"趋势分析: {target} over {time_col}",
        xlabel=time_col,
        ylabel=target,
        output_path=fpath,
        interactive=interactive,
    )
    chart_entry = {
        "type": "image" if not interactive else "html",
        "path": fpath,
        "title": f"趋势分析: {target} over {time_col}",
    }
    if interactive and fig is not None:
        try:
            chart_entry["type"] = "inline_html"
            chart_entry["html_snippet"] = fig.to_html(full_html=False, include_plotlyjs="cdn")
        except Exception as e:
            logger.warning("Failed to generate inline HTML for trend chart: %s", e)
    charts.append(chart_entry)

    return charts


def _chart_interaction(
    df: pd.DataFrame,
    raw: dict[str, Any],
    idx: int,
    output_dir: Path | None,
    interactive: bool,
) -> list[dict[str, Any]]:
    """交互效应图表：双变量交互可视化"""
    charts = []
    feat1 = raw.get("feature1")
    feat2 = raw.get("feature2")

    if not feat1 or not feat2:
        return charts

    if feat1 not in df.columns or feat2 not in df.columns:
        return charts

    # 元数据优先
    target = raw.get("target")

    # 降级：从 question 推断
    if not target:
        q = raw.get("question", "") or ""
        if "对" in q:
            hint = q.split("对")[1].split("是否存在")[0].strip()
            for col in df.columns:
                if col == hint or hint in col:
                    target = col
                    break
            if target:
                logger.warning("Interaction chart: target from question parse (metadata missing)")

    if not target or target not in df.columns:
        return charts

    fname = f"interaction_{idx}.html" if interactive else f"interaction_{idx}.png"
    fpath = str(output_dir / fname) if output_dir else None

    if interactive:
        import plotly.express as px
        import plotly.graph_objects as go

        # 分组交互图：将 feat2 分成 high/low 两组
        median_val = df[feat2].median()
        df_copy = df.copy()
        df_copy[f"{feat2}_group"] = np.where(df_copy[feat2] >= median_val, "High", "Low")

        fig = px.scatter(
            df_copy, x=feat1, y=target, color=f"{feat2}_group",
            title=f"交互效应: {feat1}×{feat2} on {target}",
            trendline="ols",
            labels={feat1: feat1, target: target},
        )

        if fpath:
            fig.write_html(fpath)

        charts.append({
            "type": "html",
            "path": fpath,
            "title": f"交互效应: {feat1}×{feat2}",
        })
    else:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        median_val = df[feat2].median()
        df_high = df[df[feat2] >= median_val]
        df_low = df[df[feat2] < median_val]

        fig, ax = plt.subplots(figsize=(10, 6))
        ax.scatter(df_high[feat1], df_high[target], alpha=0.5, label=f"{feat2} ≥ median")
        ax.scatter(df_low[feat1], df_low[target], alpha=0.5, label=f"{feat2} < median")

        # 拟合线
        if len(df_high) > 1:
            z = np.polyfit(df_high[feat1].dropna(), df_high[target].dropna(), 1)
            p = np.poly1d(z)
            x_range = np.linspace(df_high[feat1].min(), df_high[feat1].max(), 100)
            ax.plot(x_range, p(x_range), "r--", alpha=0.8)
        if len(df_low) > 1:
            z = np.polyfit(df_low[feat1].dropna(), df_low[target].dropna(), 1)
            p = np.poly1d(z)
            x_range = np.linspace(df_low[feat1].min(), df_low[feat1].max(), 100)
            ax.plot(x_range, p(x_range), "b--", alpha=0.8)

        ax.set_xlabel(feat1)
        ax.set_ylabel(target)
        ax.set_title(f"交互效应: {feat1}×{feat2}")
        ax.legend()

        if fpath:
            fig.savefig(fpath, dpi=150, bbox_inches="tight")
            plt.close(fig)

        charts.append({
            "type": "image",
            "path": fpath,
            "title": f"交互效应: {feat1}×{feat2}",
        })

    return charts


def generate_data_overview_charts(
    df: pd.DataFrame,
    output_dir: str | Path | None = None,
    *,
    interactive: bool = True,
) -> list[dict[str, Any]]:
    """
    生成数据概览图表（独立于分析结果）

    包含：
    - 数值变量分布直方图矩阵
    - 相关性热力图
    - 缺失值模式图

    Args:
        df: 数据
        output_dir: 输出目录
        interactive: 是否交互式

    Returns:
        图表元数据列表
    """
    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

    charts: list[dict[str, Any]] = []

    # 1. 相关性热力图
    numeric_df = df.select_dtypes(include=[np.number])
    if len(numeric_df.columns) >= 2:
        fname = "correlation_heatmap.html" if interactive else "correlation_heatmap.png"
        fpath = str(output_dir / fname) if output_dir else None

        create_plot(
            "heatmap",
            numeric_df,
            title="变量相关性热力图",
            output_path=fpath,
            interactive=interactive,
        )
        charts.append({
            "type": "html" if interactive else "image",
            "path": fpath,
            "title": "变量相关性热力图",
        })

    # 2. 缺失值模式图
    null_counts = df.isnull().sum()
    null_cols = null_counts[null_counts > 0]
    if len(null_cols) > 0:
        if interactive:
            import plotly.graph_objects as go
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=null_cols.index.tolist(),
                y=null_cols.values.tolist(),
                marker_color="#ea4335",
            ))
            fig.update_layout(
                title="缺失值分布",
                xaxis_title="变量",
                yaxis_title="缺失数量",
            )
            fname = "missing_pattern.html"
            fpath = str(output_dir / fname) if output_dir else None
            if fpath:
                fig.write_html(fpath)
            charts.append({
                "type": "html",
                "path": fpath,
                "title": "缺失值分布",
            })

    return charts
