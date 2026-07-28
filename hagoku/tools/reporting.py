"""HaGoKu Studio 报告生成 — 模板驱动，AI 填充内容"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

# ── 报告数据结构 ─────────────────────────────────────────────

class ReportSection:
    """报告章节 — 双轨产出：吸引力层 + 核心价值层"""

    def __init__(
        self,
        title: str,
        content: str = "",
        findings: list[dict[str, Any]] | None = None,
        charts: list[dict[str, Any]] | None = None,
        subsections: list["ReportSection"] | None = None,
        level: int = 2,
        # 吸引力层
        headline: str | None = None,
        metric_cards: list[dict[str, Any]] | None = None,
        # 核心价值层
        plain_explanation: str | None = None,
        statistical_detail: str | None = None,
        limitations: list[str] | None = None,
        evidence_trace: str | None = None,
    ) -> None:
        self.title = title
        self.content = content
        self.findings = findings or []
        self.charts = charts or []
        self.subsections = subsections or []
        self.level = level
        # 吸引力层
        self.headline = headline
        self.metric_cards = metric_cards or []
        # 核心价值层
        self.plain_explanation = plain_explanation
        self.statistical_detail = statistical_detail
        self.limitations = limitations or []
        self.evidence_trace = evidence_trace

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "content": self.content,
            "findings": self.findings,
            "charts": self.charts,
            "subsections": [s.to_dict() for s in self.subsections],
            "level": self.level,
            # 吸引力层
            "headline": self.headline,
            "metric_cards": self.metric_cards,
            # 核心价值层
            "plain_explanation": self.plain_explanation,
            "statistical_detail": self.statistical_detail,
            "limitations": self.limitations,
            "evidence_trace": self.evidence_trace,
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
        # 双轨新增
        headline: str | None = None,
        metric_cards: list[dict[str, Any]] | None = None,
        executive_summary: str | None = None,
    ) -> None:
        self.project_name = project_name
        self.query = query
        self.sections = sections or []
        self.metadata = metadata or {}
        self.findings_summary = findings_summary or []
        self.data_summary = data_summary or {}
        self.cleaning_summary = cleaning_summary or {}
        # 双轨新增
        self.headline = headline
        self.metric_cards = metric_cards or []
        self.executive_summary = (executive_summary or "").strip() or None
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
            "headline": self.headline,
            "metric_cards": self.metric_cards,
            "executive_summary": self.executive_summary,
            "generated_at": self.generated_at.isoformat(),
        }


# ── 共享基础 CSS（所有模板通用） ───────────────────────────────

_BASE_REPORT_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: var(--text); background: var(--bg); line-height: 1.6; max-width: 960px; margin: 0 auto; padding: 2rem; }
header { border-bottom: 2px solid var(--primary); padding-bottom: 1rem; margin-bottom: 2rem; }
h1 { font-size: 1.8rem; color: var(--primary); }
h2 { font-size: 1.4rem; }
h3 { font-size: 1.15rem; margin: 1rem 0 0.5rem; }
.meta { color: var(--text-secondary); font-size: 0.9rem; margin-top: 0.5rem; }
.query { font-size: 1.1rem; margin: 1rem 0; padding: 0.75rem 1rem; background: var(--surface); border-left: 4px solid var(--primary); border-radius: 4px; }
.section { margin: 2rem 0; }
.section h2 { font-size: 1.4rem; color: var(--primary); border-bottom: 1px solid var(--border); padding-bottom: 0.5rem; margin-bottom: 1rem; }
.metric-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem; margin: 1.5rem 0; }
.metric-card { background: var(--surface); border-radius: 10px; padding: 1.25rem; text-align: center; border: 1px solid var(--border); transition: transform 0.2s, box-shadow 0.2s; }
.metric-card:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
.metric-card .value { font-size: 1.8rem; font-weight: 700; color: var(--primary); }
.metric-card .label { font-size: 0.85rem; color: var(--text-secondary); margin-top: 0.25rem; }
.metric-card .trend-up { color: var(--success); }
.metric-card .trend-down { color: var(--error); }
.finding { background: var(--surface); border-radius: 8px; padding: 1rem 1.25rem; margin: 0.75rem 0; border-left: 4px solid var(--success); }
.finding.warning { border-left-color: var(--warning); }
.finding.error { border-left-color: var(--error); }
.finding .headline { font-weight: 600; font-size: 1.05rem; margin-bottom: 0.35rem; color: var(--text); }
.finding .conclusion { font-weight: 500; margin-bottom: 0.25rem; }
.finding .detail { font-size: 0.9rem; color: var(--text-secondary); }
.finding .core-value { margin-top: 0.75rem; }
.finding .plain-explanation { font-size: 0.95rem; line-height: 1.7; margin-bottom: 0.5rem; }
.finding .stats { font-family: 'Courier New', monospace; font-size: 0.85rem; background: #fff; padding: 0.5rem; border-radius: 4px; margin-top: 0.5rem; }
.finding .limitations { font-size: 0.85rem; color: var(--text-secondary); margin-top: 0.5rem; padding-left: 1rem; border-left: 2px solid var(--border); }
.finding .limitations li { margin: 0.2rem 0; }
.finding .evidence-trace { font-size: 0.8rem; color: #80868b; margin-top: 0.5rem; font-family: 'Courier New', monospace; }
.chart { margin: 1rem 0; width: 100%; }
.chart img, .chart iframe { max-width: 100%; border-radius: 8px; border: 1px solid var(--border); }
/* markdown 渲染 */
.section-content table { width: 100%; border-collapse: collapse; margin: 0.75rem 0; font-size: 0.9rem; }
.section-content th, .section-content td { padding: 0.5rem 0.75rem; text-align: left; border-bottom: 1px solid var(--border); }
.section-content th { color: var(--text-secondary); font-weight: 600; font-size: 0.8rem; }
.section-content tr:nth-child(even) { background: rgba(0,0,0,0.02); }
.section-content pre { background: var(--surface); padding: 0.75rem; border-radius: 6px; overflow-x: auto; font-size: 0.85rem; margin: 0.75rem 0; }
.section-content code { background: var(--surface); padding: 0.1rem 0.3rem; border-radius: 3px; font-size: 0.85em; }
.section-content blockquote { border-left: 3px solid var(--primary); padding-left: 1rem; margin: 0.75rem 0; color: var(--text-secondary); }
.section-content ul, .section-content ol { padding-left: 1.5rem; margin: 0.5rem 0; }
.section-content li { margin: 0.25rem 0; }
.badge { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 12px; font-size: 0.75rem; font-weight: 600; }
.badge-pass { background: #e6f4ea; color: #137333; }
.badge-warn { background: #fef7e0; color: #b06000; }
.badge-fail { background: #fce8e6; color: #c5221f; }
.summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin: 1rem 0; }
.summary-card { background: var(--surface); border-radius: 8px; padding: 1rem; text-align: center; }
.summary-card .value { font-size: 1.5rem; font-weight: 700; color: var(--primary); }
.summary-card .label { font-size: 0.85rem; color: var(--text-secondary); }
.guardrail { margin: 0.5rem 0; padding: 0.5rem 0.75rem; border-radius: 4px; font-size: 0.9rem; }
.guardrail-pass { background: #e6f4ea; }
.guardrail-warn { background: #fef7e0; }
.guardrail-fail { background: #fce8e6; }
footer { margin-top: 3rem; padding-top: 1rem; border-top: 1px solid var(--border); color: var(--text-secondary); font-size: 0.8rem; text-align: center; }
.headline-box { font-size: 1.15rem; font-weight: 600; color: var(--primary); margin: 1rem 0; padding: 1rem 1.25rem; background: var(--surface); border-radius: 8px; border-left: 4px solid var(--primary); line-height: 1.5; }
.report-toc { display: flex; gap: 1rem; flex-wrap: wrap; align-items: center; margin: 1.25rem 0; padding: 0.65rem 1rem; background: var(--surface); border-radius: 8px; border: 1px solid var(--border); position: sticky; top: 0; z-index: 20; box-shadow: 0 1px 0 rgba(0,0,0,0.04); }
.report-toc .toc-label { font-size: 0.8rem; color: var(--text-secondary); margin-right: 0.25rem; }
.report-toc a { color: var(--primary); font-weight: 600; text-decoration: none; font-size: 0.95rem; }
.report-toc a:hover { text-decoration: underline; }
.track { margin: 2rem 0; padding: 1.25rem 0 0; }
.track-summary { border-top: 2px solid var(--primary); padding-top: 1.25rem; }
.track-evidence { border-top: 2px solid var(--border); padding-top: 1.25rem; margin-top: 2rem; }
.track-hint { font-size: 0.85rem; color: var(--text-secondary); margin: 0 0 1.25rem; line-height: 1.5; }
.exec-summary { white-space: pre-wrap; font-size: 0.98rem; line-height: 1.75; margin: 1rem 0; padding: 1rem 1.25rem; background: var(--surface); border-radius: 8px; border: 1px solid var(--border); }
.finding-compact { background: var(--surface); border-radius: 8px; padding: 1rem 1.25rem; margin: 0.75rem 0; border-left: 4px solid var(--success); }
.finding-compact.warning { border-left-color: var(--warning); }
.finding-compact.error { border-left-color: var(--error); }
.finding-compact .fc-headline { font-weight: 600; margin-bottom: 0.35rem; color: var(--text); }
.finding-compact .fc-plain { font-size: 0.95rem; color: var(--text-secondary); line-height: 1.6; }
.finding-compact .fc-meta { font-size: 0.8rem; color: var(--text-secondary); margin-top: 0.5rem; }
"""

_PRINT_CSS = """
@media print {
  body { -webkit-print-color-adjust: exact; print-color-adjust: exact; max-width: none; padding: 1cm; }
  h2, h3, h4 { break-after: avoid; page-break-after: avoid; }
  thead { display: table-header-group; }
  tr { break-inside: avoid; page-break-inside: avoid; }
  .chart, canvas, img, svg { break-inside: avoid; page-break-inside: avoid; }
  .finding-compact { break-inside: avoid; page-break-inside: avoid; }
  table { width: 100%; }
}
"""


# ── 默认模板 ──────────────────────────────────────────────────

DEFAULT_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ report.project_name }} — HaGoKu Studio 分析报告</title>
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
        </style>
        <style>""" + _BASE_REPORT_CSS + """
    </style>
</head>
<body>
    <header>
        <h1>{{ report.project_name }}</h1>
        <div class="meta">
            生成时间: {{ report.generated_at[:19] }} | HaGoKu Studio v2.3.1

        </div>
        <div class="query">
            <strong>研究问题：</strong>{{ report.query }}
        </div>
    </header>

    <nav class="report-toc" aria-label="报告导航">
        <span class="toc-label">跳转：</span>
        <a href="#track-summary">要点速览</a>
        <a href="#track-evidence">数据与完整证据</a>
    </nav>

    <section id="track-summary" class="track track-summary" aria-labelledby="h-summary">
        <h2 id="h-summary">要点速览</h2>
        <p class="track-hint">快速阅读：结论摘要与关键数字。统计细节见下方「数据与完整证据」。</p>

        {% if report.headline %}
        <div class="headline-box">{{ report.headline }}</div>
        {% endif %}

        {% if report.metric_cards %}
        <div class="metric-cards">
        {% for card in report.metric_cards %}
            <div class="metric-card">
                <div class="value">{{ card.value }}{% if card.trend %} <span class="trend-{{ card.trend }}">{{ '↑' if card.trend == 'up' else '↓' }}</span>{% endif %}</div>
                <div class="label">{{ card.label }}</div>
            </div>
        {% endfor %}
        </div>
        {% endif %}

        {% if report.executive_summary %}
        <div class="exec-summary">{{ report.executive_summary }}</div>
        {% endif %}

        {% if report.findings_summary %}
        {% for finding in report.findings_summary %}
        <div class="finding-compact {% if finding.get('significance') == 'not_significant' %}warning{% elif finding.get('significance') == 'marginal' %}warning{% endif %}">
            {% if finding.get('headline') %}
            <div class="fc-headline">{{ finding.headline }}</div>
            {% endif %}
            {% if finding.get('conclusion_plain') %}
            <div class="fc-plain">{{ finding.conclusion_plain }}</div>
            {% elif finding.get('question') %}
            <div class="fc-plain">{{ finding.question }}</div>
            {% endif %}
            <div class="fc-meta">{% if finding.get('significance') == 'significant' %}判定：达到预设显著性水平{% elif finding.get('significance') == 'marginal' %}判定：边际显著{% elif finding.get('significance') == 'not_significant' %}判定：未达常规显著水平{% else %}判定：详见下方完整证据{% endif %}</div>
        </div>
        {% endfor %}
        {% endif %}
    </section>

    <section id="track-evidence" class="track track-evidence" aria-labelledby="h-evidence">
        <h2 id="h-evidence">数据、过程与完整证据</h2>
        <p class="track-hint">可追溯：样本与清洗、图表及逐项统计结果。</p>

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

        {% if section.headline %}
        <div class="headline" style="font-size:1.1rem; font-weight:600; margin-bottom:0.5rem;">{{ section.headline }}</div>
        {% endif %}

        {% if section.metric_cards %}
        <div class="metric-cards">
        {% for card in section.metric_cards %}
            <div class="metric-card">
                <div class="value">{{ card.value }}{% if card.trend %} <span class="trend-{{ card.trend }}">{{ '↑' if card.trend == 'up' else '↓' }}</span>{% endif %}</div>
                <div class="label">{{ card.label }}</div>
            </div>
        {% endfor %}
        </div>
        {% endif %}

        {% if section.content %}
        <div class="section-content">{{ section.content | safe }}</div>
        {% endif %}

        {% if section.plain_explanation %}
        <div class="plain-explanation" style="margin:0.75rem 0; font-size:0.95rem; line-height:1.7;">{{ section.plain_explanation }}</div>
        {% endif %}

        {% for finding in section.findings %}
        <div class="finding {% if finding.get('significance') == 'not_significant' %}warning{% elif finding.get('significance') == 'marginal' %}warning{% endif %}">
            {% if finding.get('headline') %}
            <div class="headline">{{ finding.headline }}</div>
            {% endif %}
            <div class="conclusion">{{ finding.get('question', finding.get('conclusion_plain', '')) }}</div>
            {% if finding.get('conclusion_plain') %}
            <div class="detail">{{ finding.conclusion_plain }}</div>
            {% endif %}
            <div class="core-value">
            {% if finding.get('plain_explanation') %}
            <div class="plain-explanation">{{ finding.plain_explanation }}</div>
            {% endif %}
            {% if finding.get('p_value') is not none %}
            <div class="stats">
                p = {{ '%.4f' | format(finding.p_value) }}
                {% if finding.get('effect_size') is not none %}| {{ finding.get('effect_type', '效应量') }} = {{ '%.3f' | format(finding.effect_size) }}{% endif %}
                {% if finding.get('confidence_interval') %}| 95% CI: {{ finding.confidence_interval }}{% endif %}
            </div>
            {% endif %}
            {% if finding.get('limitations') %}
            <ul class="limitations">
            {% for lim in finding.limitations %}
                <li>{{ lim }}</li>
            {% endfor %}
            </ul>
            {% endif %}
            {% if finding.get('evidence_trace') %}
            <div class="evidence-trace">→ {{ finding.evidence_trace }}</div>
            {% endif %}
            </div>
        </div>
        {% endfor %}

        {% if section.statistical_detail %}
        <div class="stats" style="background:var(--surface); padding:0.75rem; border-radius:6px; margin-top:0.75rem;">{{ section.statistical_detail }}</div>
        {% endif %}

        {% if section.limitations %}
        <ul class="limitations" style="margin-top:0.5rem; padding-left:1rem; border-left:2px solid var(--border); font-size:0.9rem; color:var(--text-secondary);">
        {% for lim in section.limitations %}
            <li>{{ lim }}</li>
        {% endfor %}
        </ul>
        {% endif %}

        {% if section.evidence_trace %}
        <div class="evidence-trace" style="margin-top:0.5rem;">→ {{ section.evidence_trace }}</div>
        {% endif %}

        {% for chart in section.charts %}
        <div class="chart">
            {% if chart.get('type') == 'inline_html' and chart.get('html_snippet') %}
            {{ chart.html_snippet | safe }}
            {% elif chart.get('type') == 'html' and chart.get('path') %}
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

    </section>

    <footer>
        HaGoKu Studio — 用数学的力量，挖出数据背后真正的信息
    </footer>
</body>
</html>
"""


# ── 学术报告模板 ──────────────────────────────────────────────

ACADEMIC_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ report.project_name }} — Statistical Analysis Report</title>
    <style>
        :root {
            --primary: #2c3e50;
            --bg: #ffffff;
            --surface: #f5f5f5;
            --text: #333333;
            --text-secondary: #666666;
            --border: #cccccc;
        }
        </style>
        <style>""" + _BASE_REPORT_CSS + """
    </style>
</head>
<body>
    <header>
        <h1>{{ report.project_name }}</h1>
        <div class="meta">
            Generated: {{ report.generated_at[:19] }} | HaGoKu Studio v2.3.1
        </div>
        <div class="query">Research Question: {{ report.query }}</div>
    </header>

    {% if report.data_summary %}
    <div class="section">
        <h2>1. Data Summary</h2>
        <table>
            <tr><th>Metric</th><th>Value</th></tr>
            <tr><td>Sample Size (N)</td><td>{{ report.data_summary.get('n_rows', 'N/A') }}</td></tr>
            <tr><td>Variables</td><td>{{ report.data_summary.get('n_cols', 'N/A') }}</td></tr>
            <tr><td>Data Quality Score</td><td>{{ report.data_summary.get('quality_score', 'N/A') }}</td></tr>
            <tr><td>Missing Rate</td><td>{{ report.data_summary.get('null_rate', 'N/A') }}</td></tr>
        </table>
    </div>
    {% endif %}

    {% if report.cleaning_summary %}
    <div class="section">
        <h2>2. Data Cleaning</h2>
        <p>
            Original N = {{ report.cleaning_summary.get('total_rows_original', 'N/A') }},
            After cleaning N = {{ report.cleaning_summary.get('total_rows_after', 'N/A') }},
            Impact rate = {{ report.cleaning_summary.get('impact_rate', 'N/A') }}.
        </p>
    </div>
    {% endif %}

    {% for section in report.sections %}
    <div class="section">
        <h2>{{ loop.index + 2 }}. {{ section.title | replace('🎯 ', '') | replace('📈 ', '') | replace('🔬 ', '') | replace('🔗 ', '') | replace('📊 ', '') | replace('🛡️ ', '') }}</h2>
        {% if section.content %}<div class="section-content">{{ section.content | safe }}</div>{% endif %}

        {% for finding in section.findings %}
        <div class="finding">
            <p><strong>{{ finding.get('question', finding.get('conclusion_plain', '')) }}</strong></p>
            {% if finding.get('p_value') is not none %}
            <table class="stats-table">
                <tr><th>Statistic</th><th>Value</th></tr>
                <tr><td>p-value</td><td>{{ '%.4f' | format(finding.p_value) }}</td></tr>
                {% if finding.get('effect_size') is not none %}
                <tr><td>{{ finding.get('effect_type', 'Effect Size') }}</td><td>{{ '%.3f' | format(finding.effect_size) }}</td></tr>
                {% endif %}
                {% if finding.get('confidence_interval') %}
                <tr><td>95% CI</td><td>{{ finding.confidence_interval }}</td></tr>
                {% endif %}
                <tr><td>Significance</td><td>{{ finding.get('significance', 'N/A') }}</td></tr>
            </table>
            {% endif %}
        </div>
        {% endfor %}
    </div>
    {% endfor %}

    <footer>
        HaGoKu Studio Statistical Analysis Report
    </footer>
</body>
</html>
"""


# ── 简要摘要模板 ──────────────────────────────────────────────

BRIEF_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ report.project_name }} — Summary</title>
    <style>
        :root { --primary: #1a73e8; --bg: #fff; --surface: #f8f9fa; --text: #202124; --border: #dadce0; }
        </style>
        <style>""" + _BASE_REPORT_CSS + """
    </style>
</head>
<body>
    <header>
        <h1>{{ report.project_name }}</h1>
        <div class="meta">{{ report.generated_at[:10] }}</div>
        {% if report.query %}<div class="query">{{ report.query }}</div>{% endif %}
    </header>

    {% if report.data_summary %}
    <div class="key-number">
        <div class="item">
            <div class="value">{{ report.data_summary.get('n_rows', 'N/A') }}</div>
            <div class="label">Samples</div>
        </div>
        <div class="item">
            <div class="value">{{ report.data_summary.get('n_cols', 'N/A') }}</div>
            <div class="label">Variables</div>
        </div>
        <div class="item">
            <div class="value">{{ report.data_summary.get('quality_score', 'N/A') }}</div>
            <div class="label">Quality</div>
        </div>
    </div>
    {% endif %}

    <div class="findings">
    {% for section in report.sections %}
        {% if section.content %}<div class="section-content">{{ section.content | safe }}</div>{% endif %}
        {% for chart in section.charts %}
        <div class="chart">{% if chart.get('html_snippet') %}{{ chart.html_snippet | safe }}{% endif %}</div>
        {% endfor %}
        {% if section.content %}<div class="section-content">{{ section.content | safe }}</div>{% endif %}
        {% for chart in section.charts %}
        <div class="chart">{% if chart.get('html_snippet') %}{{ chart.html_snippet | safe }}{% elif chart.get('path') %}<img src="{{ chart.path }}">{% endif %}</div>
        {% endfor %}
        {% for finding in section.findings %}
        <div class="finding-item {% if finding.get('significance') == 'not_significant' %}warning{% endif %}">
            <div class="question">{{ finding.get('question', '') }}</div>
            {% if finding.get('conclusion_plain') %}
            <div class="conclusion">{{ finding.conclusion_plain }}</div>
            {% endif %}
            {% if finding.get('p_value') is not none %}
            <div class="stats">
                p = {{ '%.4f' | format(finding.p_value) }}
                {% if finding.get('effect_size') is not none %}| d = {{ '%.3f' | format(finding.effect_size) }}{% endif %}
            </div>
            {% endif %}
        </div>
        {% endfor %}
    {% endfor %}
    </div>

    <footer>HaGoKu Studio Summary</footer>
</body>
</html>
"""


# ── 内置模板注册 ──────────────────────────────────────────────
# 注意：新模板在下方定义，BUILTIN_TEMPLATES 字典移到文件末尾


# ── 商业分析模板 ──────────────────────────────────────────────

BUSINESS_ANALYSIS_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ report.project_name }} — 商业分析报告</title>
    <style>
        :root {
            --bg: #ffffff;
            --surface: #f8f9fa;
            --card: #ffffff;
            --border: #dee2e6;
            --text: #212529;
            --text-secondary: #6c757d;
            --accent: #0d6efd;
            --accent-dim: #0b5ed7;
            --success: #198754;
            --warning: #fd7e14;
            --error: #dc3545;
            --tier-1: rgba(63,185,80,0.15);
            --tier-2: rgba(88,166,255,0.15);
            --tier-3: rgba(210,153,34,0.15);
            --tier-4: rgba(248,81,73,0.12);
            --font: -apple-system, 'Microsoft YaHei', 'PingFang SC', sans-serif;
        }
        * { margin:0; padding:0; box-sizing:border-box; }
        body {
            background: var(--bg);
            color: var(--text);
            font-family: var(--font);
            line-height: 1.7;
            max-width: 960px;
            margin: 0 auto;
            padding: 2rem 1.5rem 4rem;
            -webkit-font-smoothing: antialiased;
        }
        header {
            text-align: center;
            padding: 3rem 0 2rem;
            border-bottom: 1px solid var(--border);
            margin-bottom: 2rem;
        }
        header h1 { font-size: 2rem; font-weight: 700; margin-bottom: 0.5rem; }
        header .meta { color: var(--text-secondary); font-size: 0.85rem; margin-bottom: 0.5rem; }
        header .query { color: var(--accent); font-size: 0.95rem; margin-top: 0.5rem; }

        .headline-box {
            background: linear-gradient(135deg, #e7f1ff, #f0f7ff);
            color: var(--text);
            padding: 1.25rem 1.5rem;
            border-radius: 12px;
            font-size: 1.15rem;
            font-weight: 600;
            margin-bottom: 2rem;
            border-left: 4px solid var(--accent);
        }

        .metric-cards {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }
        .metric-card {
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 1.25rem;
            text-align: center;
        }
        .metric-card .value {
            font-size: 1.8rem;
            font-weight: 700;
            color: var(--accent);
            line-height: 1.2;
        }
        .metric-card .label { color: var(--text-secondary); font-size: 0.8rem; margin-top: 0.3rem; }

        .section {
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
        }
        .section h2 {
            font-size: 1.2rem;
            color: var(--accent);
            margin-bottom: 1rem;
            padding-bottom: 0.5rem;
            border-bottom: 1px solid var(--border);
        }
        .section p, .section .content { color: var(--text); font-size: 0.95rem; margin-bottom: 1rem; }

        .finding {
            background: var(--bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 1rem 1.25rem;
            margin-bottom: 0.75rem;
        }
        .finding .headline { font-weight: 600; font-size: 1rem; margin-bottom: 0.3rem; color: var(--text); }
        .finding .conclusion { font-size: 0.9rem; color: var(--text-secondary); margin-bottom: 0.3rem; }
        .finding .stats {
            font-family: 'SF Mono', 'Consolas', monospace;
            font-size: 0.8rem;
            color: var(--accent);
            background: rgba(13,110,253,0.06);
            display: inline-block;
            padding: 0.15rem 0.5rem;
            border-radius: 4px;
            margin-top: 0.3rem;
        }
        .finding.warning .headline { color: var(--warning); }

        table {
            width: 100%;
            border-collapse: collapse;
            margin: 1rem 0;
            font-size: 0.9rem;
        }
        th, td {
            padding: 0.6rem 0.75rem;
            text-align: left;
            border-bottom: 1px solid var(--border);
        }
        th { color: var(--text-secondary); font-weight: 600; font-size: 0.8rem; text-transform: uppercase; }
        tr:hover td { background: rgba(13,110,253,0.03); }

        .chart {
            margin: 1rem 0; width: 100%;
            border-radius: 8px;
            overflow: hidden;
            background: var(--bg);
        }

        .action-box {
            background: linear-gradient(135deg, #f8f9fa, #e7f1ff);
            border: 1px solid var(--accent-dim);
            border-radius: 12px;
            padding: 1.5rem;
            margin-top: 2rem;
        }
        .action-box h3 { color: var(--accent); font-size: 1.05rem; margin-bottom: 0.75rem; }
        .action-box ul { padding-left: 1.25rem; }
        .action-box li { color: var(--text); font-size: 0.9rem; margin-bottom: 0.4rem; }

        footer {
            text-align: center;
            color: var(--text-secondary);
            font-size: 0.75rem;
            margin-top: 3rem;
            padding-top: 1.5rem;
            border-top: 1px solid var(--border);
        }
    </style>
</head>
<body>
    <header>
        <h1>📊 {{ report.project_name }}</h1>
        <div class="meta">商业分析报告 | {{ report.generated_at[:10] }} | HaGoKu Studio</div>
        {% if report.query %}<div class="query"><strong>核心问题：</strong>{{ report.query }}</div>{% endif %}
    </header>

    {% if report.headline %}
    <div class="headline-box">💡 {{ report.headline }}</div>
    {% endif %}

    {% if report.metric_cards %}
    <div class="metric-cards">
    {% for card in report.metric_cards %}
        <div class="metric-card">
            <div class="value">{{ card.value }}</div>
            <div class="label">{{ card.label }}</div>
        </div>
    {% endfor %}
    </div>
    {% endif %}

    {% for section in report.sections %}
    <div class="section">
        <h2>{{ section.title }}</h2>
        {% if section.content %}<div class="content">{{ section.content | safe }}</div>{% endif %}

        {% for finding in section.findings %}
        <div class="finding {% if finding.get('significance') == 'not_significant' %}warning{% endif %}">
            {% if finding.get('headline') %}<div class="headline">{{ finding.headline }}</div>{% endif %}
            <div class="conclusion">{{ finding.get('conclusion_plain', finding.get('question', '')) }}</div>
            {% if finding.get('plain_explanation') %}
            <div class="detail">{{ finding.plain_explanation }}</div>
            {% endif %}
            {% if finding.get('p_value') is not none %}
            <div class="stats">p = {{ '%.4f' | format(finding.p_value) }}{% if finding.get('effect_size') is not none %} | 效应量 = {{ '%.3f' | format(finding.effect_size) }}{% endif %}</div>
            {% endif %}
        </div>
        {% endfor %}

        {% for chart in section.charts %}
        <div class="chart">
            {% if chart.get('type') == 'inline_html' and chart.get('html_snippet') %}
            {{ chart.html_snippet | safe }}
            {% elif chart.get('type') == 'html' and chart.get('path') %}
            <iframe src="{{ chart.path }}" width="100%" height="400" frameborder="0"></iframe>
            {% elif chart.get('type') == 'image' and chart.get('path') %}
            <img src="{{ chart.path }}" alt="{{ chart.get('title', '') }}">
            {% endif %}
        </div>
        {% endfor %}
    </div>
    {% endfor %}

    <footer>HaGoKu Studio 商业分析报告 · 用数据驱动决策</footer>
</body>
</html>
"""


# ── A/B 测试报告模板 ─────────────────────────────────────────

AB_TEST_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ report.project_name }} — A/B 测试报告</title>
    <style>
        :root { --primary: #1b5e20; --bg: #fff; --surface: #f1f8e9; --text: #212121; --border: #c8e6c9; --success: #2e7d32; --warning: #f57f17; --error: #c62828; }
        </style>
        <style>""" + _BASE_REPORT_CSS + """
    </style>
</head>
<body>
    <header>
        <h1>🧪 {{ report.project_name }}</h1>
        <div class="meta">A/B 测试分析 | {{ report.generated_at[:10] }}</div>
        {% if report.query %}<div style="margin-top:0.5rem;">{{ report.query }}</div>{% endif %}
    </header>

    {% if report.headline %}
    <div class="verdict-box {% if '显著' in report.headline or 'significant' in report.headline.lower() %}verdict-significant{% else %}verdict-not-significant{% endif %}">
        {{ report.headline }}
    </div>
    {% endif %}

    {% if report.metric_cards %}
    <div class="metric-cards">
    {% for card in report.metric_cards %}
        <div class="metric-card">
            <div class="value">{{ card.value }}</div>
            <div class="label">{{ card.label }}</div>
        </div>
    {% endfor %}
    </div>
    {% endif %}

    {% for section in report.sections %}
    <div class="section">
        <h2>{{ section.title }}</h2>
        {% if section.content %}<div class="section-content">{{ section.content | safe }}</div>{% endif %}
        {% for finding in section.findings %}
        <div class="finding">
            {% if finding.get('headline') %}<strong>{{ finding.headline }}</strong><br>{% endif %}
            {{ finding.get('conclusion_plain', finding.get('question', '')) }}
            {% if finding.get('p_value') is not none %}
            <div class="stats">
                p = {{ '%.4f' | format(finding.p_value) }}
                {% if finding.get('effect_size') is not none %}| 效应量 = {{ '%.3f' | format(finding.effect_size) }}{% endif %}
                {% if finding.get('confidence_interval') %}| 95% CI: {{ finding.confidence_interval }}{% endif %}
            </div>
            {% endif %}
        </div>
        {% endfor %}
        {% for chart in section.charts %}
        <div class="chart">
            {% if chart.get('type') == 'inline_html' and chart.get('html_snippet') %}
            {{ chart.html_snippet | safe }}
            {% elif chart.get('type') == 'html' and chart.get('path') %}
            <iframe src="{{ chart.path }}" width="100%" height="400" frameborder="0"></iframe>
            {% elif chart.get('type') == 'image' and chart.get('path') %}
            <img src="{{ chart.path }}" alt="{{ chart.get('title', '') }}">
            {% endif %}
        </div>
        {% endfor %}
    </div>
    {% endfor %}

    <footer>HaGoKu Studio A/B 测试报告</footer>
</body>
</html>
"""


# ── 高管简报模板 ──────────────────────────────────────────────

EXECUTIVE_BRIEF_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ report.project_name }} — 高管简报</title>
    <style>
        :root { --primary: #1565c0; --bg: #fff; --surface: #f5f5f5; --text: #212121; --border: #e0e0e0; }
        </style>
        <style>""" + _BASE_REPORT_CSS + """
    </style>
</head>
<body>
    <header>
        <h1>{{ report.project_name }}</h1>
        <div class="meta">高管简报 | {{ report.generated_at[:10] }}</div>
    </header>

    {% if report.headline %}
    <div class="key-message">{{ report.headline }}</div>
    {% endif %}

    {% if report.metric_cards %}
    <div class="numbers">
    {% for card in report.metric_cards %}
        <div class="item">
            <div class="value">{{ card.value }}</div>
            <div class="label">{{ card.label }}</div>
        </div>
    {% endfor %}
    </div>
    {% endif %}

    {% for section in report.sections %}
        {% if section.content %}<div class="section-content">{{ section.content | safe }}</div>{% endif %}
        {% for chart in section.charts %}
        <div class="chart">{% if chart.get('html_snippet') %}{{ chart.html_snippet | safe }}{% endif %}</div>
        {% endfor %}
        {% for finding in section.findings %}
        <div class="insight">
            <div class="q">{{ finding.get('question', '') }}</div>
            <div class="a">{{ finding.get('conclusion_plain', finding.get('plain_explanation', '')) }}</div>
        </div>
        {% endfor %}
    {% endfor %}

    <div class="recommendation">
        <h3>📋 建议行动</h3>
        <ol>
        {% for section in report.sections %}
            {% for finding in section.findings %}
                {% if finding.get('significance') == 'significant' %}
            <li>{{ finding.get('question', '') }}</li>
                {% endif %}
            {% endfor %}
        {% endfor %}
        </ol>
    </div>

    <div class="caveat">
        ⚠️ 以上结论基于统计检验（p < 0.05），但统计显著不代表商业显著。
        决策前请考虑效应量大小、业务成本和实施可行性。
    </div>

    <footer>HaGoKu Studio 高管简报</footer>
</body>
</html>
"""


# ── 数据审计模板 ──────────────────────────────────────────────

DATA_AUDIT_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ report.project_name }} — 数据审计报告</title>
    <style>
        :root { --primary: #37474f; --bg: #fff; --surface: #eceff1; --text: #212121; --text-secondary: #607d8b; --border: #cfd8dc; --success: #2e7d32; --warning: #f57f17; --error: #c62828; }
        </style>
        <style>""" + _BASE_REPORT_CSS + """
    </style>
</head>
<body>
    <header>
        <h1>🔍 {{ report.project_name }} — 数据审计</h1>
        <div class="meta">审计时间: {{ report.generated_at[:19] }} | HaGoKu Studio v2.3.1</div>
    </header>

    <div class="audit-summary">
        {% if report.data_summary %}
        <div class="audit-card">
            <div class="label">样本量</div>
            <div class="value">{{ report.data_summary.get('n_rows', 'N/A') }}</div>
        </div>
        <div class="audit-card">
            <div class="label">变量数</div>
            <div class="value">{{ report.data_summary.get('n_cols', 'N/A') }}</div>
        </div>
        <div class="audit-card {% if report.data_summary.get('null_rate') and report.data_summary.get('null_rate') != 'N/A' and report.data_summary.get('null_rate')|float > 0.1 %}warn{% endif %}">
            <div class="label">缺失率</div>
            <div class="value">{{ report.data_summary.get('null_rate', 'N/A') }}</div>
        </div>
        <div class="audit-card">
            <div class="label">质量评分</div>
            <div class="value">{{ report.data_summary.get('quality_score', 'N/A') }}</div>
        </div>
        {% endif %}
    </div>

    {% if report.cleaning_summary %}
    <div class="section">
        <h2>🧹 清洗审计</h2>
        <table class="audit-table">
            <tr><th>操作</th><th>列</th><th>策略</th><th>原因</th></tr>
            {% for op in report.cleaning_summary.get('operations', []) %}
            <tr>
                <td>{{ loop.index }}</td>
                <td>{{ op.column }}</td>
                <td>{{ op.strategy }}</td>
                <td>{{ op.reason }}</td>
            </tr>
            {% endfor %}
        </table>
        <div class="finding">
            原始 {{ report.cleaning_summary.get('total_rows_original', 'N/A') }} 行
            → 清洗后 {{ report.cleaning_summary.get('total_rows_after', 'N/A') }} 行
            (影响率: {{ report.cleaning_summary.get('impact_rate', 'N/A') }})
        </div>
    </div>
    {% endif %}

    {% for section in report.sections %}
    <div class="section">
        <h2>{{ section.title }}</h2>
        {% if section.content %}<div class="section-content">{{ section.content | safe }}</div>{% endif %}
        {% for finding in section.findings %}
        <div class="finding">
            {% if finding.get('headline') %}<strong>{{ finding.headline }}</strong><br>{% endif %}
            {{ finding.get('conclusion_plain', finding.get('question', '')) }}
            {% if finding.get('p_value') is not none %}
            <br><span class="badge {% if finding.p_value < 0.05 %}badge-pass{% else %}badge-warn{% endif %}">
                p = {{ '%.4f' | format(finding.p_value) }}
            </span>
            {% endif %}
            {% if finding.get('limitations') %}
            <ul style="font-size:0.85rem; color:#607d8b; margin-top:0.5rem; padding-left:1.5rem;">
            {% for lim in finding.limitations %}<li>{{ lim }}</li>{% endfor %}
            </ul>
            {% endif %}
        </div>
        {% endfor %}
        {% for chart in section.charts %}
        <div class="chart">
            {% if chart.get('type') == 'inline_html' and chart.get('html_snippet') %}
            {{ chart.html_snippet | safe }}
            {% elif chart.get('type') == 'html' and chart.get('path') %}
            <iframe src="{{ chart.path }}" width="100%" height="400" frameborder="0"></iframe>
            {% elif chart.get('type') == 'image' and chart.get('path') %}
            <img src="{{ chart.path }}" alt="{{ chart.get('title', '') }}">
            {% endif %}
        </div>
        {% endfor %}
    </div>
    {% endfor %}

    <footer>HaGoKu Studio 数据审计报告</footer>
</body>
</html>
"""


# ── 打印模板（白纸黑字，A4 排版）─────────────────────────────

_PRINT_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>{{ report.title or '分析报告' }}</title>
    <style>
        @page { size: A4; margin: 1cm; }
        body { font-family: 'Noto Sans SC', 'Microsoft YaHei', sans-serif; color: #1a1a1a; background: #fff; line-height: 1.8; font-size: 11pt; }
        h1 { font-size: 18pt; border-bottom: 2px solid #333; padding-bottom: 0.5rem; margin-bottom: 1.5rem; }
        h2 { font-size: 14pt; border-bottom: 1px solid #ccc; padding-bottom: 0.25rem; margin-top: 2rem; }
        h3 { font-size: 12pt; margin-top: 1.5rem; }
        table { width: 100%; border-collapse: collapse; margin: 0.75rem 0; font-size: 10pt; }
        th, td { padding: 0.4rem 0.6rem; text-align: left; border: 1px solid #ccc; }
        th { background: #f5f5f5; font-weight: 600; }
        tr { break-inside: avoid; }
        thead { display: table-header-group; }
        .chart { width: 100%; margin: 1rem 0; }
        .chart img, .chart svg { max-width: 100%; height: auto; }
        .headline { font-weight: 700; font-size: 12pt; margin: 1rem 0 0.5rem; }
        .meta { color: #666; font-size: 9pt; margin-bottom: 2rem; }
        code { font-family: 'Courier New', monospace; font-size: 9pt; background: #f5f5f5; padding: 0.1rem 0.3rem; }
        pre { background: #f5f5f5; padding: 0.5rem; font-size: 9pt; overflow-x: auto; }
        blockquote { border-left: 3px solid #ccc; padding-left: 1rem; margin: 0.5rem 0; color: #555; }
        ul, ol { padding-left: 1.5rem; }
    </style>
</head>
<body>
    <h1>{{ report.query or '数据分析报告' }}</h1>
    <div class="meta">HaGoKu Studio · {{ report.generated_at[:19] or '' }}</div>

    {% if report.headline %}
    <p class="headline">{{ report.headline }}</p>
    {% endif %}

    {% for section in report.sections %}
    <h2>{{ section.title }}</h2>
    {% if section.content %}
    <div>{{ section.content | safe }}</div>
    {% endif %}
    {% for chart in section.charts %}
    <div class="chart">
        {% if chart.get('html_snippet') %}
        {{ chart.html_snippet | safe }}
        {% elif chart.get('path') %}
        <img src="{{ chart.path }}" alt="{{ chart.get('title', '') }}">
        {% endif %}
    </div>
    {% endfor %}
    {% endfor %}
</body>
</html>
"""


# ── 内置模板注册 ──────────────────────────────────────────────

BUILTIN_TEMPLATES: dict[str, str] = {
    "default": DEFAULT_HTML_TEMPLATE,
    "academic": ACADEMIC_HTML_TEMPLATE,
    "brief": BRIEF_HTML_TEMPLATE,
    "business_analysis": BUSINESS_ANALYSIS_HTML_TEMPLATE,
    "ab_test": AB_TEST_HTML_TEMPLATE,
    "executive_brief": EXECUTIVE_BRIEF_HTML_TEMPLATE,
    "data_audit": DATA_AUDIT_HTML_TEMPLATE,
    "print": _PRINT_HTML_TEMPLATE,
}


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
            template_name: 模板名 — "default"/"academic"/"brief" 或 template_dir 中的文件名

        Returns:
            HTML 字符串
        """
        env = self._get_env()

        # 选择模板
        if template_name and template_name in BUILTIN_TEMPLATES:
            template = env.from_string(BUILTIN_TEMPLATES[template_name])
        elif template_name:
            template = env.get_template(template_name)
        elif self.custom_template:
            template = env.get_template(self.custom_template)
        else:
            template = env.from_string(DEFAULT_HTML_TEMPLATE)

        # 渲染
        html: str = template.render(report=report.to_dict())

        # 注入打印 CSS，避免换页截断
        html = html.replace("</head>", f"<style>{_PRINT_CSS}</style>\n</head>")

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

        lines.append("## 要点速览")
        lines.append("")
        if report.headline:
            lines.append(f"**结论摘要：** {report.headline}")
            lines.append("")
        if report.executive_summary:
            lines.append(report.executive_summary)
            lines.append("")
        if report.metric_cards:
            for card in report.metric_cards:
                lines.append(f"- **{card.get('label', '')}**：{card.get('value', '')}")
            lines.append("")
        if report.findings_summary:
            for finding in report.findings_summary:
                q = finding.get("question") or finding.get("headline") or ""
                plain = finding.get("conclusion_plain") or ""
                sig = finding.get("significance") or ""
                lines.append(f"- ({sig}) {q} {plain}".strip())
            lines.append("")

        lines.append("## 数据、过程与完整证据")
        lines.append("")
        if report.data_summary:
            lines.append("### 📊 数据概况")
            lines.append("")
            lines.append(f"- 样本量: {report.data_summary.get('n_rows', 'N/A')}")
            lines.append(f"- 变量数: {report.data_summary.get('n_cols', 'N/A')}")
            lines.append(f"- 数据质量: {report.data_summary.get('quality_score', 'N/A')}")
            lines.append("")

        # 清洗摘要
        if report.cleaning_summary:
            lines.append("### 🧹 数据清洗")
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
        lines.append("*HaGoKu Studio — 用数学的力量，挖出数据背后真正的信息*")

        md = "\n".join(lines)

        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(md)

        return md
