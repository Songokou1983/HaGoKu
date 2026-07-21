"""可视化工具 — CO-T22

注册：
  CO-T22 create_plot → visualization.create_plot
"""

from __future__ import annotations

from typing import Any

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

    # ── 数据过滤 ──
    filter_col = args.get("filter")
    if filter_col and isinstance(filter_col, dict):
        try:
            for col, vals in filter_col.items():
                if col in df.columns and isinstance(vals, list):
                    df = df[df[col].isin(vals)]
        except Exception:
            pass

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
        width = int(args["width"]) if args.get("width") else None
        height = int(args["height"]) if args.get("height") else None

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
        if fig and (width or height):
            layout: dict[str, Any] = {}
            if width:
                layout["width"] = width
            if height:
                layout["height"] = height
            fig.update_layout(**layout)

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
                # ── 非 ephemeral 才存入 context ──
                if not args.get("ephemeral"):
                    chart_id = args.get("chart_id") or f"chart_{len(charts) + 1}"
                    charts = ctx.setdefault("_generated_charts", [])
                    charts.append({
                        "chart_id": chart_id,
                        "type": "inline_html",
                        "html_snippet": html_snippet,
                        "title": title or f"{chart_type} 图",
                    })
                    result["chart_id"] = chart_id
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
        "filter 按列值过滤数据（如 filter: {Code: [\"A0001\",\"A0002\"]} 只画指定店铺）。"
        "ephemeral: true 时不存入上下文（预览用，不会被 generate_report 自动注入）。"
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
            "chart_id": {"type": "string", "description": "图表标识，供 generate_report 的 section.charts 按 ID 引用"},
            "width": {"type": "integer", "description": "图表宽度（px）"},
            "height": {"type": "integer", "description": "图表高度（px）"},
            "filter": {"type": "object", "description": "按列值过滤，如 {\"Code\": [\"A0001\", \"A0002\"]}"},
            "ephemeral": {"type": "boolean", "description": "true 时不存入上下文，仅预览"},
        },
        "required": ["chart_type"],
    },
    handler=_handle_create_plot,
    phase_tag=["写报告"],
))
