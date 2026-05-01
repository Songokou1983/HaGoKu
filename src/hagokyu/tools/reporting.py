"""HaGoKu 报告生成 — 模板驱动，AI 填充内容"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape


# ── 报告数据结构 ─────────────────────────────────────────────

class ReportSection:
    """报告章节"""

    def __init__(
        self,
        title: str,
        content: str = "",
        findings: list[dict[str, Any]] | None = None,
        charts: list[dict[str, Any]] | None = None,
        subsections: list["ReportSection"] | None = None,
        level: int = 2,
    ) -> None:
        self.title = title
        self.content = content
        self.findings = findings or []
        self.charts = charts or []
        self.subsections = subsections or []
        self.level = level

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "content": self.content,
            "findings": self.findings,
            "charts": self.charts,
            "subsections": [s.to_dict() for s in self.subsections],
            "level": self.level,
        }


class ReportData:
    """报告数据容器"""

    def __init__(
        self,
        project_name: str,
        query: str,
        sections: list[ReportSection] | None = None,
        metadata: dict[str, Any] | None = None,
        findings_summary: list[dict[str, Any]] | None = None,
        data_summary: dict[str, Any] | None = None,
        cleaning_summary: dict[str, Any] | None = None,
    ) -> None:
        self.project_name = project_name
        self.query = query
        self.sections = sections or []
        self.metadata = metadata or {}
        self.findings_summary = findings_summary or []
        self.data_summary = data_summary or {}
        self.cleaning_summary = cleaning_summary or {}
        self.generated_at = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_name": self.project_name,
            "query": self.query,
            "sections": [s.to_dict() for s in self.sections],
            "metadata": self.metadata,
            "findings_summary": self.findings_summary,
            "data_summary": self.data_summary,
            "cleaning_summary": self.cleaning_summary,
            "generated_at": self.generated_at.isoformat(),
        }


# ── 默认模板 ──────────────────────────────────────────────────

DEFAULT_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ report.project_name }} — HaGoKu 分析报告</title>
    <style>
        :root {
            --primary: #1a73e8;
            --bg: #ffffff;
            --surface: #f8f9fa;
            --text: #202124;
            --text-secondary: #5f6368;
            --border: #dadce0;
            --success: #34a853;
            --warning: #fbbc04;
            --error: #ea4335;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            color: var(--text); background: var(--bg); line-height: 1.6;
            max-width: 960px; margin: 0 auto; padding: 2rem;
        }
        header { border-bottom: 2px solid var(--primary); padding-bottom: 1rem; margin-bottom: 2rem; }
        h1 { font-size: 1.8rem; color: var(--primary); }
        .meta { color: var(--text-secondary); font-size: 0.9rem; margin-top: 0.5rem; }
        .query { font-size: 1.1rem; margin: 1rem 0; padding: 0.75rem 1rem;
                 background: var(--surface); border-left: 4px solid var(--primary); border-radius: 4px; }
        .section { margin: 2rem 0; }
        .section h2 { font-size: 1.4rem; color: var(--primary); border-bottom: 1px solid var(--border);
                      padding-bottom: 0.5rem; margin-bottom: 1rem; }
        .section h3 { font-size: 1.15rem; margin: 1rem 0 0.5rem; }
        .finding { background: var(--surface); border-radius: 8px; padding: 1rem 1.25rem;
                   margin: 0.75rem 0; border-left: 4px solid var(--success); }
        .finding.warning { border-left-color: var(--warning); }
        .finding.error { border-left-color: var(--error); }
        .finding .conclusion { font-weight: 600; margin-bottom: 0.25rem; }
        .finding .detail { font-size: 0.9rem; color: var(--text-secondary); }
        .finding .stats { font-family: 'Courier New', monospace; font-size: 0.85rem;
                         background: #fff; padding: 0.5rem; border-radius: 4px; margin-top: 0.5rem; }
        .chart { margin: 1rem 0; text-align: center; }
        .chart img, .chart iframe { max-width: 100%; border-radius: 8px; border: 1px solid var(--border); }
        .badge { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 12px;
                font-size: 0.75rem; font-weight: 600; }
        .badge-pass { background: #e6f4ea; color: #137333; }
        .badge-warn { background: #fef7e0; color: #b06000; }
        .badge-fail { background: #fce8e6; color: #c5221f; }
        .summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                        gap: 1rem; margin: 1rem 0; }
        .summary-card { background: var(--surface); border-radius: 8px; padding: 1rem; text-align: center; }
        .summary-card .value { font-size: 1.5rem; font-weight: 700; color: var(--primary); }
        .summary-card .label { font-size: 0.85rem; color: var(--text-secondary); }
        .guardrail { margin: 0.5rem 0; padding: 0.5rem 0.75rem; border-radius: 4px; font-size: 0.9rem; }
        .guardrail-pass { background: #e6f4ea; }
        .guardrail-warn { background: #fef7e0; }
        .guardrail-fail { background: #fce8e6; }
        footer { margin-top: 3rem; padding-top: 1rem; border-top: 1px solid var(--border);
                color: var(--text-secondary); font-size: 0.8rem; text-align: center; }
    </style>
</head>
<body>
    <header>
        <h1>{{ report.project_name }}</h1>
        <div class="meta">
            生成时间: {{ report.generated_at[:19] }} | HaGoKu v0.1.0
        </div>
        <div class="query">
            <strong>研究问题：</strong>{{ report.query }}
        </div>
    </header>

    {% if report.data_summary %}
    <div class="section">
        <h2>📊 数据概况</h2>
        <div class="summary-grid">
            <div class="summary-card">
                <div class="value">{{ report.data_summary.get('n_rows', 'N/A') }}</div>
                <div class="label">样本量</div>
            </div>
            <div class="summary-card">
                <div class="value">{{ report.data_summary.get('n_cols', 'N/A') }}</div>
                <div class="label">变量数</div>
            </div>
            <div class="summary-card">
                <div class="value">{{ report.data_summary.get('quality_score', 'N/A') }}</div>
                <div class="label">数据质量</div>
            </div>
            <div class="summary-card">
                <div class="value">{{ report.data_summary.get('null_rate', 'N/A') }}</div>
                <div class="label">缺失率</div>
            </div>
        </div>
    </div>
    {% endif %}

    {% if report.cleaning_summary %}
    <div class="section">
        <h2>🧹 数据清洗</h2>
        <p>原始: {{ report.cleaning_summary.get('total_rows_original', 'N/A') }} 行
           → 清洗后: {{ report.cleaning_summary.get('total_rows_after', 'N/A') }} 行
           (影响率: {{ report.cleaning_summary.get('impact_rate', 'N/A') }})</p>
        {% for op in report.cleaning_summary.get('operations', []) %}
        <div class="finding">
            <div class="conclusion">{{ op.column }}: {{ op.strategy }}</div>
            <div class="detail">{{ op.reason }}</div>
        </div>
        {% endfor %}
    </div>
    {% endif %}

    {% for section in report.sections %}
    <div class="section">
        <h2>{{ section.title }}</h2>
        {% if section.content %}
        <p>{{ section.content }}</p>
        {% endif %}
        {% for finding in section.findings %}
        <div class="finding {% if finding.get('significance') == 'not_significant' %}warning{% elif finding.get('significance') == 'marginal' %}warning{% endif %}">
            <div class="conclusion">{{ finding.get('question', finding.get('conclusion_plain', '')) }}</div>
            {% if finding.get('conclusion_plain') %}
            <div class="detail">{{ finding.conclusion_plain }}</div>
            {% endif %}
            {% if finding.get('p_value') is not none %}
            <div class="stats">
                p = {{ '%.4f' | format(finding.p_value) }}
                {% if finding.get('effect_size') is not none %}| {{ finding.get('effect_type', '效应量') }} = {{ '%.3f' | format(finding.effect_size) }}{% endif %}
                {% if finding.get('confidence_interval') %}| 95% CI: {{ finding.confidence_interval }}{% endif %}
            </div>
            {% endif %}
        </div>
        {% endfor %}
        {% for chart in section.charts %}
        <div class="chart">
            {% if chart.get('type') == 'html' and chart.get('path') %}
            <iframe src="{{ chart.path }}" width="100%" height="400" frameborder="0"></iframe>
            {% elif chart.get('type') == 'image' and chart.get('path') %}
            <img src="{{ chart.path }}" alt="{{ chart.get('title', '') }}">
            {% endif %}
        </div>
        {% endfor %}
        {% for sub in section.subsections %}
        <h3>{{ sub.title }}</h3>
        {% if sub.content %}<p>{{ sub.content }}</p>{% endif %}
        {% endfor %}
    </div>
    {% endfor %}

    <footer>
        HaGoKu — 用数学的力量，挖出数据背后真正的信息
    </footer>
</body>
</html>
"""


# ── 报告生成器 ────────────────────────────────────────────────


class ReportGenerator:
    """报告生成器：模板驱动，AI 填充内容"""

    def __init__(
        self,
        template_dir: Path | None = None,
        custom_template: str | None = None,
    ) -> None:
        """
        Args:
            template_dir: 自定义模板目录
            custom_template: 自定义模板文件名
        """
        self.template_dir = template_dir
        self.custom_template = custom_template
        self._env: Environment | None = None

    def _get_env(self) -> Environment:
        """获取 Jinja2 环境"""
        if self._env is None:
            if self.template_dir and self.template_dir.exists():
                self._env = Environment(
                    loader=FileSystemLoader(str(self.template_dir)),
                    autoescape=select_autoescape(["html"]),
                )
            else:
                self._env = Environment(autoescape=select_autoescape(["html"]))
        return self._env

    def generate_html(
        self,
        report: ReportData,
        output_path: str | Path | None = None,
        *,
        template_name: str | None = None,
    ) -> str:
        """
        生成 HTML 报告

        Args:
            report: 报告数据
            output_path: 输出路径
            template_name: 模板名（在 template_dir 中查找）

        Returns:
            HTML 字符串
        """
        env = self._get_env()

        # 选择模板
        if template_name:
            template = env.get_template(template_name)
        elif self.custom_template:
            template = env.get_template(self.custom_template)
        else:
            template = env.from_string(DEFAULT_HTML_TEMPLATE)

        # 渲染
        html = template.render(report=report.to_dict())

        # 保存
        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(html)

        return html

    def generate_json(
        self,
        report: ReportData,
        output_path: str | Path | None = None,
    ) -> str:
        """
        生成 JSON 报告（供程序化消费）

        Args:
            report: 报告数据
            output_path: 输出路径

        Returns:
            JSON 字符串
        """
        json_str = json.dumps(report.to_dict(), ensure_ascii=False, indent=2)

        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(json_str)

        return json_str

    def generate_markdown(
        self,
        report: ReportData,
        output_path: str | Path | None = None,
    ) -> str:
        """
        生成 Markdown 报告

        Args:
            report: 报告数据
            output_path: 输出路径

        Returns:
            Markdown 字符串
        """
        lines = [
            f"# {report.project_name}",
            "",
            f"> 研究问题：{report.query}",
            f"> 生成时间：{report.generated_at.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
        ]

        # 数据概况
        if report.data_summary:
            lines.append("## 📊 数据概况")
            lines.append("")
            lines.append(f"- 样本量: {report.data_summary.get('n_rows', 'N/A')}")
            lines.append(f"- 变量数: {report.data_summary.get('n_cols', 'N/A')}")
            lines.append(f"- 数据质量: {report.data_summary.get('quality_score', 'N/A')}")
            lines.append("")

        # 清洗摘要
        if report.cleaning_summary:
            lines.append("## 🧹 数据清洗")
            lines.append("")
            lines.append(
                f"原始 {report.cleaning_summary.get('total_rows_original', 'N/A')} 行"
                f" → 清洗后 {report.cleaning_summary.get('total_rows_after', 'N/A')} 行"
                f" (影响率: {report.cleaning_summary.get('impact_rate', 'N/A')})"
            )
            lines.append("")

        # 章节
        for section in report.sections:
            prefix = "#" * section.level
            lines.append(f"{prefix} {section.title}")
            lines.append("")
            if section.content:
                lines.append(section.content)
                lines.append("")

            for finding in section.findings:
                significance = finding.get("significance", "")
                if significance == "significant":
                    icon = "✅"
                elif significance == "marginal":
                    icon = "⚠️"
                else:
                    icon = "📌"

                lines.append(f"{icon} **{finding.get('question', '')}**")
                if finding.get("conclusion_plain"):
                    lines.append(f"   {finding['conclusion_plain']}")
                if finding.get("p_value") is not None:
                    stats_line = f"   p = {finding['p_value']:.4f}"
                    if finding.get("effect_size") is not None:
                        stats_line += f" | {finding.get('effect_type', '效应量')} = {finding['effect_size']:.3f}"
                    if finding.get("confidence_interval"):
                        stats_line += f" | 95% CI: {finding['confidence_interval']}"
                    lines.append(f"   `{stats_line}`")
                lines.append("")

            if section.charts:
                for chart in section.charts:
                    if chart.get("path"):
                        lines.append(f"![{chart.get('title', '')}]({chart['path']})")
                lines.append("")

        lines.append("---")
        lines.append("*HaGoKu — 用数学的力量，挖出数据背后真正的信息*")

        md = "\n".join(lines)

        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(md)

        return md
