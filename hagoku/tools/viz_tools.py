"""可视化工具 — CO-T22

注册：
  CO-T22 create_plot → visualization.create_plot
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from hagoku.tools.registry import Tool, agent_tools


# ═══════════════════════════════════════════════════════════════════
# CO-T22: create_plot
# ═══════════════════════════════════════════════════════════════════

def _handle_create_plot(args: dict, ctx: dict, df: pd.DataFrame | None) -> dict:
    chart_type = str(args.get("chart_type", "")).strip()
    columns = list(args.get("columns", []) or [])
    title = str(args.get("title", ""))
    x = args.get("x") or (columns[0] if len(columns) >= 1 else None)
    y = args.get("y") or (columns[1] if len(columns) >= 2 else None)

    if not chart_type:
        return {"error": "chart_type 必填"}
    if df is None:
        return {"error": "需要 DataFrame"}

    # 验证列存在
    if x and isinstance(x, str) and x not in df.columns:
        return {"error": f"列 {x} 不存在"}
    if y and isinstance(y, str) and y not in df.columns:
        return {"error": f"列 {y} 不存在"}

    from hagoku.tools.visualization import create_plot

    try:
        color = args.get("color")
        xlabel = str(args.get("xlabel", ""))
        ylabel = str(args.get("ylabel", ""))

        fig = create_plot(
            chart_type, df,
            x=str(x) if x else None,
            y=str(y) if y else None,
            color=str(color) if color else None,
            title=title,
            xlabel=xlabel,
            ylabel=ylabel,
            interactive=True,
        )

        # 大图不进 LLM context，只返 artifact 路径/摘要
        result: dict[str, Any] = {
            "chart_type": chart_type,
            "title": title or f"{chart_type} 图",
            "x": x,
            "y": y,
        }

        if fig is not None:
            try:
                html_snippet = fig.to_html(full_html=False, include_plotlyjs="cdn")
                result["html_snippet"] = html_snippet
                result["type"] = "inline_html"
                # ── 自动存入 context，供 generate_report 读取 ──
                charts = ctx.setdefault("_generated_charts", [])
                charts.append({
                    "type": "inline_html",
                    "html_snippet": html_snippet,
                    "title": title or f"{chart_type} 图",
                })
            except Exception:
                result["type"] = "plotly_figure"
                result["note"] = "图表已生成 (Plotly Figure)，大图不进入 LLM context"

        # 如果指定了 output_path，写入文件
        output_path = args.get("output_path")
        if output_path and fig is not None:
            try:
                from pathlib import Path
                p = Path(output_path)
                p.parent.mkdir(parents=True, exist_ok=True)
                fig.write_html(str(p))
                result["artifact_path"] = str(p)
            except Exception as e:
                result["write_error"] = str(e)

        return result
    except Exception as e:
        return {"error": str(e)}


agent_tools.register(Tool(
    name="create_plot",
    description=(
        "生成交互式图表（Plotly）。chart_type 可选: scatter / line / bar / histogram / box / violin / heatmap。"
        "需传 chart_type + columns（列名列表，第1个=x轴，第2个=y轴）。"
        "也可显式传 x / y / title / xlabel / ylabel / color（分组列）。"
        "图表不进 LLM context，只返回 artifact_path 和摘要信息。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "chart_type": {
                "type": "string",
                "enum": ["scatter", "line", "bar", "histogram", "box", "violin", "heatmap"],
                "description": "图表类型",
            },
            "columns": {"type": "array", "items": {"type": "string"}, "description": "使用的列名 [x轴, y轴]"},
            "x": {"type": "string", "description": "X 轴列名（覆盖 columns[0]）"},
            "y": {"type": "string", "description": "Y 轴列名（覆盖 columns[1]）"},
            "color": {"type": "string", "description": "分组/颜色列名"},
            "title": {"type": "string", "description": "图表标题"},
            "xlabel": {"type": "string", "description": "X 轴标签"},
            "ylabel": {"type": "string", "description": "Y 轴标签"},
            "output_path": {"type": "string", "description": "输出文件路径（.html），不传则不写文件"},
        },
        "required": ["chart_type"],
    },
    handler=_handle_create_plot,
    phase_tag=["写报告"],
))
