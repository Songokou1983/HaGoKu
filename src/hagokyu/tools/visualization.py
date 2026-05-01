"""HaGoKu 可视化 — 吸引力层的实现"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


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
                ax.boxplot([g.values for _, g in groups], labels=[g for g, _ in groups])
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
