"""MethodCurator — 学术方法库质量审计 Agent（CO-D01～D04）

用 Meta LLM + 确定性规则审 memory/methods/：frontmatter 完整性、工具引用、正文质量。
只输出建议，不修改方法文档（brief §12.4）。
"""

from __future__ import annotations

import json as _json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hagoku.llm.client import create_raw_client
from hagoku.channel import build_messages

logger = logging.getLogger("hagoku.method_curator")

AUDIT_DIR = Path.home() / ".hagoku" / "audits"
DRAFT_DIR = AUDIT_DIR / "drafts" / "methods"
_METHODS_ROOT = Path(__file__).resolve().parent.parent.parent / "memory" / "methods"

# frontmatter 必含字段（MC-01）
REQUIRED_FRONTMATTER = {"title", "category", "summary", "tags", "tools"}


@dataclass
class MethodAuditReport:
    """方法库审计报告"""
    report_type: str = "method"
    timestamp: str = ""
    total_methods: int = 0
    tools_referenced: set[str] = field(default_factory=set)
    missing_frontmatter: list[dict[str, Any]] = field(default_factory=list)
    missing_tools: list[dict[str, Any]] = field(default_factory=list)
    orphan_tools: list[str] = field(default_factory=list)
    llm_findings: str = ""
    draft_suggestions: list[str] = field(default_factory=list)


def _parse_frontmatter(text: str) -> dict[str, Any]:
    """解析 YAML frontmatter（`---` 包裹的头部）。返回 dict。"""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    end = -1
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            end = i
            break
    if end == -1:
        return {}
    raw = "\n".join(lines[1:end])
    try:
        import yaml
        data = yaml.safe_load(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        # 尝试手动解析简单 YAML
        result: dict[str, Any] = {}
        for line in raw.splitlines():
            line = line.strip()
            if ":" in line and not line.startswith("#"):
                key, _, val = line.partition(":")
                key = key.strip()
                val = val.strip().strip("'\"")
                if key == "tools":
                    # tools 可能是 list
                    continue
                result[key] = val
        # 单独解析 tools 列表
        tools = _parse_tools_list(raw)
        if tools:
            result["tools"] = tools
        return result


def _parse_tools_list(yaml_str: str) -> list[str]:
    """从 YAML 字符串中解析 tools 列表。"""
    tools = []
    in_tools = False
    for line in yaml_str.splitlines():
        stripped = line.strip()
        if stripped.startswith("tools:"):
            in_tools = True
            val = stripped.partition(":")[2].strip()
            if val and val.startswith("[") and val.endswith("]"):
                import yaml
                try:
                    parsed = yaml.safe_load(stripped)
                    if isinstance(parsed, dict) and "tools" in parsed:
                        return parsed["tools"] or []
                except Exception:
                    pass
            if val and val != "[]":
                tools.append(val.strip(" -[]\"'"))
            continue
        if in_tools and stripped.startswith("- "):
            tools.append(stripped[2:].strip(" '\""))
        elif in_tools and not stripped.startswith("-"):
            in_tools = False
    return tools


def _strip_frontmatter(text: str) -> str:
    """移除 frontmatter，返回正文。"""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return text
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            return "\n".join(lines[i + 1:])
    return text


def _discover_methods() -> list[dict[str, Any]]:
    """扫描 memory/methods/ 目录，返回方法文档列表。"""
    methods = []
    if not _METHODS_ROOT.exists():
        return methods
    for md_file in sorted(_METHODS_ROOT.rglob("*.md")):
        if md_file.name == "__init__.md":
            continue
        text = md_file.read_text(encoding="utf-8")
        fm = _parse_frontmatter(text)
        body = _strip_frontmatter(text)
        rel_path = str(md_file.relative_to(_METHODS_ROOT.parent))
        methods.append({
            "path": rel_path,
            "frontmatter": fm,
            "body_preview": body[:500],
            "body_length": len(body),
        })
    return methods


def _get_registered_tool_names() -> set[str]:
    """从 agent_tools 注册表获取所有已注册工具名称。"""
    try:
        from hagoku.tools.registry import agent_tools
        return set(agent_tools._tools.keys())
    except Exception:
        return set()


class MethodCurator:
    """学术方法库审计 Agent。只读，不修改方法文档。"""

    def __init__(self) -> None:
        self._prompt_path = Path(__file__).parent / "prompt.md"

    @property
    def prompt(self) -> str:
        if self._prompt_path.exists():
            return self._prompt_path.read_text(encoding="utf-8")
        return ""

    def audit(self) -> MethodAuditReport:
        """执行完整方法库审计。"""
        methods = _discover_methods()
        registered = _get_registered_tool_names()
        report = MethodAuditReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
            total_methods=len(methods),
        )

        # ── 确定性检查 ──

        # MC-01: frontmatter 必含字段
        for m in methods:
            fm = m["frontmatter"]
            missing_fields = [f for f in REQUIRED_FRONTMATTER if f not in fm or not fm[f]]
            if missing_fields:
                report.missing_frontmatter.append({
                    "path": m["path"],
                    "missing": missing_fields,
                })

        # MC-02: tools 引用的工具必须已注册
        all_refd: set[str] = set()
        for m in methods:
            tools = m["frontmatter"].get("tools", [])
            if isinstance(tools, list):
                for t in tools:
                    t_str = str(t).strip()
                    if t_str:
                        all_refd.add(t_str)
                        if t_str not in registered:
                            report.missing_tools.append({
                                "path": m["path"],
                                "tool": t_str,
                            })
        report.tools_referenced = all_refd

        # MC-03: 统计类工具是否有文档引用
        stat_keywords = {
            "stat", "test", "power", "effect", "anova", "ttest", "regression",
            "correlation", "distribution", "normality", "diagnose", "assess",
            "run_", "calc_", "required_", "interpret_", "check_", "compare_",
        }
        for t_name in sorted(registered):
            is_stat = any(kw in t_name.lower() for kw in stat_keywords)
            if is_stat and t_name not in all_refd:
                # 排除 memory 工具、项目管理工具等
                if not t_name.startswith(("query_", "read_", "save_", "list_",
                                           "update_", "delete_", "create_",
                                           "get_", "set_", "write_")):
                    report.orphan_tools.append(t_name)

        # ── LLM 检查（MC-04, MC-05）──
        llm_result = self._llm_audit(methods, registered)
        if llm_result:
            report.llm_findings = llm_result

        return report

    def _llm_audit(self, methods: list[dict], registered: set[str]) -> str | None:
        """调用 Meta LLM 做正文质量审计（MC-04, MC-05）。"""
        prompt_text = self.prompt
        if not prompt_text:
            return None
        from hagoku.config import HaGoKuConfig
        cfg = HaGoKuConfig.load()
        client = create_raw_client(cfg.llm)
        if client is None:
            raise RuntimeError("MethodCurator: LLM 不可达")

        payload = {
            "methods": [
                {
                    "path": m["path"],
                    "frontmatter": m["frontmatter"],
                    "body_preview": m["body_preview"],
                }
                for m in methods
            ],
            "registered_tools": sorted(registered),
        }
        # EXEMPT: Meta LLM — 方法库审计，非主对话通道
        messages = build_messages(
            query="method audit",
            user_input=_json.dumps(payload, ensure_ascii=False, default=str),
            system_extra=prompt_text,
        )
        model = cfg.meta_llm.model or cfg.llm.model
        resp = client.chat.completions.create(
            model=model, messages=messages, temperature=0.0, max_tokens=2048,
        )
        return (resp.choices[0].message.content or "").strip()

    def write_report(self, report: MethodAuditReport) -> Path:
        """将审计报告写入 ~/.hagoku/audits/。"""
        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        ts = report.timestamp[:19].replace(":", "").replace("-", "")
        filename = f"method_audit_{ts}.md"
        path = AUDIT_DIR / filename

        lines = [
            "# Method Audit",
            f"Time: {report.timestamp[:19]}",
            f"Total methods: {report.total_methods}",
            f"Tools referenced: {len(report.tools_referenced)}",
            "",
            "## Summary",
            f"- methods: {report.total_methods}",
            f"- tools referenced: {len(report.tools_referenced)}",
            f"- missing frontmatter: {len(report.missing_frontmatter)}",
            f"- missing tool docs: {len(report.missing_tools)}",
            f"- orphan tools (no doc): {len(report.orphan_tools)}",
            "",
        ]

        # Blocking
        blocking = []
        for item in report.missing_frontmatter:
            blocking.append(f"- `{item['path']}`: missing {item['missing']}")
        for item in report.missing_tools:
            blocking.append(f"- `{item['path']}` references `{item['tool']}`, but tool is not registered")
        if blocking:
            lines.append("## Blocking")
            lines.extend(blocking)
            lines.append("")

        # Orphan tools
        if report.orphan_tools:
            lines.append("## Orphan Tools (no method doc)")
            for t in report.orphan_tools:
                lines.append(f"- `{t}`")
            lines.append("")

        # LLM findings
        if report.llm_findings:
            lines.append("## LLM Findings")
            lines.append(report.llm_findings)
            lines.append("")

        # Draft suggestions
        if report.draft_suggestions:
            lines.append("## Draft Suggestions")
            for s in report.draft_suggestions:
                lines.append(f"- {s}")
            lines.append("")

        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def write_draft(self, domain: str, slug: str, content: str) -> Path:
        """将草稿方法文档写入 drafts 目录。"""
        DRAFT_DIR.mkdir(parents=True, exist_ok=True)
        domain_dir = DRAFT_DIR / domain
        domain_dir.mkdir(parents=True, exist_ok=True)
        draft_path = domain_dir / f"{slug}.md"
        draft_path.write_text(content, encoding="utf-8")
        logger.info("Draft written: %s", draft_path)
        return draft_path


# ── 便利函数 ──

def run_method_audit() -> Path:
    """执行一次方法库审计，返回报告路径。"""
    curator = MethodCurator()
    report = curator.audit()
    return curator.write_report(report)
