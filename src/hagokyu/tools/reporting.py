"""HaGoKu 报告生成 — 模板驱动，AI 填充内容"""

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
        user_mode: str = "standard",
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
        self.user_mode = user_mode  # quick / standard / expert
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
            "user_mode": self.user_mode,
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

        /* 吸引力层 — 一眼抓住 */
        .headline-box {
            background: linear-gradient(135deg, #1a73e8 0%, #4285f4 100%);
            color: #fff; border-radius: 12px; padding: 1.5rem 2rem;
            margin: 1.5rem 0; font-size: 1.2rem; font-weight: 600;
        }
        .metric-cards {
            display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 1rem; margin: 1.5rem 0;
        }
        .metric-card {
            background: var(--surface); border-radius: 10px; padding: 1.25rem;
            text-align: center; border: 1px solid var(--border);
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .metric-card:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
        .metric-card .value { font-size: 1.8rem; font-weight: 700; color: var(--primary); }
        .metric-card .label { font-size: 0.85rem; color: var(--text-secondary); margin-top: 0.25rem; }
        .metric-card .trend-up { color: var(--success); }
        .metric-card .trend-down { color: var(--error); }

        .section { margin: 2rem 0; }
        .section h2 { font-size: 1.4rem; color: var(--primary); border-bottom: 1px solid var(--border);
                      padding-bottom: 0.5rem; margin-bottom: 1rem; }
        .section h3 { font-size: 1.15rem; margin: 1rem 0 0.5rem; }

        /* 双轨发现卡片 */
        .finding { background: var(--surface); border-radius: 8px; padding: 1rem 1.25rem;
                   margin: 0.75rem 0; border-left: 4px solid var(--success); }
        .finding.warning { border-left-color: var(--warning); }
        .finding.error { border-left-color: var(--error); }
        .finding .headline { font-weight: 600; font-size: 1.05rem; margin-bottom: 0.35rem; color: var(--text); }
        .finding .conclusion { font-weight: 500; margin-bottom: 0.25rem; }
        .finding .detail { font-size: 0.9rem; color: var(--text-secondary); }

        /* 核心价值层 — 展开查看 */
        .finding .core-value { margin-top: 0.75rem; }
        .finding .plain-explanation { font-size: 0.95rem; line-height: 1.7; margin-bottom: 0.5rem; }
        .finding .stats {
            font-family: 'Courier New', monospace; font-size: 0.85rem;
            background: #fff; padding: 0.5rem; border-radius: 4px; margin-top: 0.5rem;
        }
        .finding .limitations {
            font-size: 0.85rem; color: var(--text-secondary); margin-top: 0.5rem;
            padding-left: 1rem; border-left: 2px solid var(--border);
        }
        .finding .limitations li { margin: 0.2rem 0; }
        .finding .evidence-trace {
            font-size: 0.8rem; color: #80868b; margin-top: 0.5rem;
            font-family: 'Courier New', monospace;
        }

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
            {% if report.user_mode == 'quick' %}| ⚡ 快速模式{% elif report.user_mode == 'expert' %}| 🔬 资深模式{% endif %}
        </div>
        <div class="query">
            <strong>研究问题：</strong>{{ report.query }}
        </div>
    </header>

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
        <p>{{ section.content }}</p>
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
            {% if finding.get('p_value') is not none and report.user_mode != 'quick' %}
            <div class="stats">
                p = {{ '%.4f' | format(finding.p_value) }}
                {% if finding.get('effect_size') is not none %}| {{ finding.get('effect_type', '效应量') }} = {{ '%.3f' | format(finding.effect_size) }}{% endif %}
                {% if finding.get('confidence_interval') %}| 95% CI: {{ finding.confidence_interval }}{% endif %}
            </div>
            {% endif %}
            {% if finding.get('limitations') and report.user_mode != 'quick' %}
            <ul class="limitations">
            {% for lim in finding.limitations %}
                <li>{{ lim }}</li>
            {% endfor %}
            </ul>
            {% endif %}
            {% if finding.get('evidence_trace') and report.user_mode == 'expert' %}
            <div class="evidence-trace">→ {{ finding.evidence_trace }}</div>
            {% endif %}
            </div>
        </div>
        {% endfor %}

        {% if section.statistical_detail and report.user_mode != 'quick' %}
        <div class="stats" style="background:var(--surface); padding:0.75rem; border-radius:6px; margin-top:0.75rem;">{{ section.statistical_detail }}</div>
        {% endif %}

        {% if section.limitations and report.user_mode != 'quick' %}
        <ul class="limitations" style="margin-top:0.5rem; padding-left:1rem; border-left:2px solid var(--border); font-size:0.9rem; color:var(--text-secondary);">
        {% for lim in section.limitations %}
            <li>{{ lim }}</li>
        {% endfor %}
        </ul>
        {% endif %}

        {% if section.evidence_trace and report.user_mode == 'expert' %}
        <div class="evidence-trace" style="margin-top:0.5rem;">→ {{ section.evidence_trace }}</div>
        {% endif %}

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
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Times New Roman', 'Songti SC', 'SimSun', serif;
            color: var(--text); background: var(--bg); line-height: 1.8;
            max-width: 800px; margin: 0 auto; padding: 2.5rem;
            font-size: 12pt;
        }
        header { border-bottom: 1px solid var(--text); padding-bottom: 1rem; margin-bottom: 2rem; }
        h1 { font-size: 16pt; text-align: center; margin-bottom: 0.5rem; }
        .meta { font-size: 10pt; color: var(--text-secondary); text-align: center; }
        .query { font-style: italic; text-align: center; margin: 1rem 0; font-size: 11pt; }
        .section { margin: 2rem 0; }
        h2 { font-size: 13pt; border-bottom: 1px solid var(--border); padding-bottom: 0.3rem; margin-bottom: 0.8rem; }
        h3 { font-size: 12pt; margin: 1rem 0 0.5rem; }
        p { text-indent: 2em; margin: 0.5rem 0; }
        table { width: 100%; border-collapse: collapse; margin: 1rem 0; font-size: 10pt; }
        th, td { border: 1px solid var(--border); padding: 0.4rem 0.6rem; text-align: left; }
        th { background: var(--surface); font-weight: bold; }
        .finding { margin: 1rem 0; padding: 0.5rem 0; }
        .finding p { text-indent: 0; }
        .stats-table { margin: 0.5rem 0 0.5rem 2em; }
        .stats-table td { font-family: 'Courier New', monospace; font-size: 9pt; }
        .guardrail { font-size: 10pt; color: #c0392b; margin: 0.3rem 0; }
        footer { margin-top: 3rem; border-top: 1px solid var(--text); padding-top: 0.5rem;
                font-size: 9pt; color: var(--text-secondary); text-align: center; }
    </style>
</head>
<body>
    <header>
        <h1>{{ report.project_name }}</h1>
        <div class="meta">
            Generated: {{ report.generated_at[:19] }} | HaGoKu v0.1.0
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
        {% if section.content %}<p>{{ section.content }}</p>{% endif %}

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
        HaGoKu Statistical Analysis Report
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
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            color: var(--text); background: var(--bg); line-height: 1.5;
            max-width: 640px; margin: 0 auto; padding: 2rem;
        }
        header { border-left: 4px solid var(--primary); padding-left: 1rem; margin-bottom: 2rem; }
        h1 { font-size: 1.3rem; color: var(--primary); }
        .meta { font-size: 0.8rem; color: #80868b; margin-top: 0.3rem; }
        .query { font-size: 0.95rem; margin: 0.5rem 0; color: var(--text); }
        .key-number { display: flex; gap: 1.5rem; margin: 1.5rem 0; flex-wrap: wrap; }
        .key-number .item { text-align: center; }
        .key-number .value { font-size: 1.8rem; font-weight: 700; color: var(--primary); }
        .key-number .label { font-size: 0.75rem; color: #80868b; }
        .findings { margin: 1.5rem 0; }
        .finding-item {
            background: var(--surface); border-radius: 6px; padding: 0.75rem 1rem;
            margin: 0.5rem 0; border-left: 3px solid var(--primary);
        }
        .finding-item .question { font-weight: 600; font-size: 0.9rem; }
        .finding-item .conclusion { font-size: 0.85rem; margin-top: 0.25rem; }
        .finding-item .stats { font-size: 0.8rem; color: #5f6368; margin-top: 0.25rem;
                              font-family: 'Courier New', monospace; }
        .finding-item.warning { border-left-color: #fbbc04; }
        .finding-item.negative { border-left-color: #ea4335; }
        footer { margin-top: 2rem; font-size: 0.75rem; color: #80868b; text-align: center; }
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

    <footer>HaGoKu Summary</footer>
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
            --primary: #0d47a1;
            --accent: #ff6f00;
            --bg: #ffffff;
            --surface: #f5f7fa;
            --text: #212121;
            --text-secondary: #616161;
            --border: #e0e0e0;
            --success: #2e7d32;
            --warning: #f57f17;
            --error: #c62828;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            color: var(--text); background: var(--bg); line-height: 1.6;
            max-width: 960px; margin: 0 auto; padding: 2rem;
        }
        header {
            background: linear-gradient(135deg, #0d47a1 0%, #1565c0 100%);
            color: #fff; padding: 2rem; border-radius: 12px; margin-bottom: 2rem;
        }
        h1 { font-size: 1.8rem; margin-bottom: 0.5rem; }
        .meta { opacity: 0.85; font-size: 0.9rem; }
        .query { font-size: 1.1rem; margin-top: 1rem; padding-top: 1rem; border-top: 1px solid rgba(255,255,255,0.3); }

        .headline-box {
            background: var(--accent); color: #fff; border-radius: 8px;
            padding: 1.25rem 1.5rem; margin: 1.5rem 0;
            font-size: 1.15rem; font-weight: 600;
        }
        .metric-cards {
            display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 1rem; margin: 1.5rem 0;
        }
        .metric-card {
            background: var(--surface); border-radius: 8px; padding: 1.25rem;
            text-align: center; border-bottom: 3px solid var(--primary);
        }
        .metric-card .value { font-size: 2rem; font-weight: 700; color: var(--primary); }
        .metric-card .label { font-size: 0.85rem; color: var(--text-secondary); margin-top: 0.25rem; }

        .section { margin: 2rem 0; }
        .section h2 { font-size: 1.3rem; color: var(--primary); padding-bottom: 0.5rem;
                      border-bottom: 2px solid var(--primary); margin-bottom: 1rem; }

        .finding {
            background: var(--surface); border-radius: 8px; padding: 1rem 1.25rem;
            margin: 0.75rem 0; border-left: 4px solid var(--success);
        }
        .finding.warning { border-left-color: var(--warning); }
        .finding.error { border-left-color: var(--error); }
        .finding .headline { font-weight: 600; font-size: 1.05rem; margin-bottom: 0.35rem; }
        .finding .conclusion { font-weight: 500; }
        .finding .detail { font-size: 0.9rem; color: var(--text-secondary); margin-top: 0.25rem; }
        .finding .stats { font-family: monospace; font-size: 0.85rem; color: var(--text-secondary); margin-top: 0.5rem; }

        .action-box {
            background: #e3f2fd; border-radius: 8px; padding: 1rem 1.25rem;
            margin: 1rem 0; border-left: 4px solid var(--primary);
        }
        .action-box h3 { color: var(--primary); font-size: 1rem; margin-bottom: 0.5rem; }
        .action-box ul { padding-left: 1.5rem; }
        .action-box li { margin: 0.3rem 0; }

        .chart { margin: 1rem 0; text-align: center; }
        .chart img, .chart iframe { max-width: 100%; border-radius: 8px; border: 1px solid var(--border); }

        footer { margin-top: 3rem; padding-top: 1rem; border-top: 1px solid var(--border);
                color: var(--text-secondary); font-size: 0.8rem; text-align: center; }
    </style>
</head>
<body>
    <header>
        <h1>📊 {{ report.project_name }}</h1>
        <div class="meta">商业分析报告 | {{ report.generated_at[:10] }} | HaGoKu</div>
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
        {% if section.content %}<p>{{ section.content }}</p>{% endif %}

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
            {% if chart.get('type') == 'html' and chart.get('path') %}
            <iframe src="{{ chart.path }}" width="100%" height="400" frameborder="0"></iframe>
            {% elif chart.get('type') == 'image' and chart.get('path') %}
            <img src="{{ chart.path }}" alt="{{ chart.get('title', '') }}">
            {% endif %}
        </div>
        {% endfor %}
    </div>
    {% endfor %}

    <div class="action-box">
        <h3>📋 建议行动</h3>
        <ul>
        {% for section in report.sections %}
            {% for finding in section.findings %}
                {% if finding.get('significance') == 'significant' and finding.get('question') %}
            <li>{{ finding.question }} — 基于数据支持，建议优先关注</li>
                {% endif %}
            {% endfor %}
        {% endfor %}
        </ul>
    </div>

    <footer>HaGoKu 商业分析报告 — 用数学的力量，驱动商业决策</footer>
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
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color: var(--text); background: var(--bg); line-height: 1.6; max-width: 800px; margin: 0 auto; padding: 2rem; }
        header { background: var(--primary); color: #fff; padding: 1.5rem; border-radius: 8px; margin-bottom: 2rem; }
        h1 { font-size: 1.5rem; }
        .meta { opacity: 0.85; font-size: 0.85rem; margin-top: 0.5rem; }

        .verdict-box {
            border-radius: 12px; padding: 1.5rem; margin: 1.5rem 0;
            text-align: center; font-size: 1.2rem; font-weight: 600;
        }
        .verdict-significant { background: #e8f5e9; color: var(--success); border: 2px solid var(--success); }
        .verdict-not-significant { background: #fff3e0; color: var(--warning); border: 2px solid var(--warning); }

        .metric-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 1rem; margin: 1.5rem 0; }
        .metric-card { background: var(--surface); border-radius: 8px; padding: 1rem; text-align: center; }
        .metric-card .value { font-size: 1.6rem; font-weight: 700; color: var(--primary); }
        .metric-card .label { font-size: 0.8rem; color: #757575; }

        .section { margin: 2rem 0; }
        .section h2 { font-size: 1.2rem; color: var(--primary); border-bottom: 2px solid var(--border); padding-bottom: 0.5rem; margin-bottom: 1rem; }
        .result-table { width: 100%; border-collapse: collapse; margin: 1rem 0; }
        .result-table th, .result-table td { padding: 0.6rem 1rem; text-align: left; border-bottom: 1px solid var(--border); }
        .result-table th { background: var(--surface); font-weight: 600; }

        .finding { background: var(--surface); border-radius: 8px; padding: 1rem; margin: 0.5rem 0; }
        .finding .stats { font-family: monospace; font-size: 0.85rem; color: #616161; }

        .chart { margin: 1rem 0; text-align: center; }
        .chart img, .chart iframe { max-width: 100%; border-radius: 8px; }
        footer { margin-top: 3rem; font-size: 0.8rem; color: #9e9e9e; text-align: center; }
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
            {% if chart.get('type') == 'html' and chart.get('path') %}
            <iframe src="{{ chart.path }}" width="100%" height="400" frameborder="0"></iframe>
            {% elif chart.get('type') == 'image' and chart.get('path') %}
            <img src="{{ chart.path }}" alt="{{ chart.get('title', '') }}">
            {% endif %}
        </div>
        {% endfor %}
    </div>
    {% endfor %}

    <footer>HaGoKu A/B 测试报告</footer>
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
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color: var(--text); background: var(--bg); line-height: 1.5; max-width: 680px; margin: 0 auto; padding: 2rem; }

        header { margin-bottom: 1.5rem; padding-bottom: 1rem; border-bottom: 3px solid var(--primary); }
        h1 { font-size: 1.4rem; color: var(--primary); }
        .meta { font-size: 0.8rem; color: #9e9e9e; margin-top: 0.25rem; }

        .key-message {
            background: var(--primary); color: #fff; border-radius: 8px;
            padding: 1.25rem; margin: 1rem 0; font-size: 1.1rem; font-weight: 500;
        }

        .numbers { display: flex; gap: 2rem; margin: 1.5rem 0; flex-wrap: wrap; }
        .numbers .item { text-align: center; min-width: 100px; }
        .numbers .value { font-size: 2rem; font-weight: 700; color: var(--primary); }
        .numbers .label { font-size: 0.75rem; color: #757575; text-transform: uppercase; }

        .insight { margin: 1rem 0; padding: 0.75rem 1rem; border-left: 3px solid var(--primary); background: var(--surface); border-radius: 0 6px 6px 0; }
        .insight .q { font-weight: 600; font-size: 0.95rem; }
        .insight .a { font-size: 0.9rem; margin-top: 0.25rem; color: #424242; }

        .recommendation { background: #e3f2fd; border-radius: 6px; padding: 1rem; margin: 1rem 0; }
        .recommendation h3 { font-size: 0.95rem; color: var(--primary); margin-bottom: 0.5rem; }
        .recommendation ol { padding-left: 1.5rem; }
        .recommendation li { font-size: 0.9rem; margin: 0.3rem 0; }

        .caveat { font-size: 0.8rem; color: #9e9e9e; margin-top: 1.5rem; padding-top: 0.75rem; border-top: 1px solid var(--border); }

        footer { margin-top: 2rem; font-size: 0.7rem; color: #bdbdbd; text-align: center; }
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

    <footer>HaGoKu 高管简报</footer>
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
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color: var(--text); background: var(--bg); line-height: 1.6; max-width: 960px; margin: 0 auto; padding: 2rem; }
        header { border-bottom: 3px solid var(--primary); padding-bottom: 1rem; margin-bottom: 2rem; }
        h1 { font-size: 1.5rem; color: var(--primary); }
        .meta { color: var(--text-secondary); font-size: 0.85rem; margin-top: 0.5rem; }

        .audit-summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin: 1.5rem 0; }
        .audit-card { background: var(--surface); border-radius: 8px; padding: 1rem; border-left: 4px solid var(--primary); }
        .audit-card .label { font-size: 0.8rem; color: var(--text-secondary); text-transform: uppercase; }
        .audit-card .value { font-size: 1.4rem; font-weight: 700; color: var(--primary); margin-top: 0.25rem; }
        .audit-card.warn { border-left-color: var(--warning); }
        .audit-card.error { border-left-color: var(--error); }

        .section { margin: 2rem 0; }
        .section h2 { font-size: 1.2rem; color: var(--primary); margin-bottom: 1rem; }

        .audit-table { width: 100%; border-collapse: collapse; margin: 1rem 0; font-size: 0.9rem; }
        .audit-table th, .audit-table td { padding: 0.5rem 0.75rem; text-align: left; border-bottom: 1px solid var(--border); }
        .audit-table th { background: var(--surface); font-weight: 600; color: var(--primary); }
        .audit-table tr:hover { background: #fafafa; }

        .badge { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 12px; font-size: 0.75rem; font-weight: 600; }
        .badge-pass { background: #e8f5e9; color: var(--success); }
        .badge-warn { background: #fff3e0; color: var(--warning); }
        .badge-fail { background: #ffebee; color: var(--error); }

        .finding { background: var(--surface); border-radius: 6px; padding: 0.75rem 1rem; margin: 0.5rem 0; }
        .chart { margin: 1rem 0; text-align: center; }
        .chart img, .chart iframe { max-width: 100%; border-radius: 8px; }

        footer { margin-top: 3rem; padding-top: 1rem; border-top: 1px solid var(--border); color: var(--text-secondary); font-size: 0.8rem; text-align: center; }
    </style>
</head>
<body>
    <header>
        <h1>🔍 {{ report.project_name }} — 数据审计</h1>
        <div class="meta">审计时间: {{ report.generated_at[:19] }} | HaGoKu v0.1.0</div>
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
            {% if chart.get('type') == 'html' and chart.get('path') %}
            <iframe src="{{ chart.path }}" width="100%" height="400" frameborder="0"></iframe>
            {% elif chart.get('type') == 'image' and chart.get('path') %}
            <img src="{{ chart.path }}" alt="{{ chart.get('title', '') }}">
            {% endif %}
        </div>
        {% endfor %}
    </div>
    {% endfor %}

    <footer>HaGoKu 数据审计报告</footer>
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
