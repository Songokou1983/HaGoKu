"""ToolCurator — 工具箱质量审计 Agent（CO-D05～D06）

用 Meta LLM + 确定性规则审 agent_tools：description 质量、schema 完整性、测试覆盖率。
只输出建议，不修改工具代码（brief §12.5）。
"""

from __future__ import annotations

import json as _json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hagoku.llm.client import create_raw_client
from hagoku.channel import build_messages

logger = logging.getLogger("hagoku.tool_curator")

AUDIT_DIR = Path.home() / ".hagoku" / "audits"

# 统计工具关键词（TC-03）
STAT_TOOL_KEYWORDS = {
    "stat", "test", "power", "effect", "anova", "ttest", "regression",
    "correlation", "distribution", "normality", "diagnose", "assess",
    "run_", "calc_", "required_", "interpret_", "check_", "compare_",
}


@dataclass
class ToolAuditReport:
    """工具箱审计报告"""
    report_type: str = "tool"
    timestamp: str = ""
    total_tools: int = 0
    tools_with_tests: int = 0
    tools_with_docs: int = 0
    prompt_fake_tools: list[str] = field(default_factory=list)
    missing_tests: list[str] = field(default_factory=list)
    missing_docs: list[str] = field(default_factory=list)
    stat_tools_without_metrics: list[str] = field(default_factory=list)
    llm_findings: str = ""


def _get_registered_tools() -> list[dict[str, Any]]:
    """从 agent_tools 注册表获取所有已注册工具的详细信息。"""
    try:
        from hagoku.tools.registry import agent_tools
    except Exception:
        return []
    tools = []
    for name, tool in sorted(agent_tools._tools.items()):
        tools.append({
            "name": name,
            "description": tool.description,
            "parameters": tool.parameters,
            "phase_tag": getattr(tool, "phase_tag", []),
        })
    return tools


def _find_tool_tests() -> set[str]:
    """扫描 tests/ 目录，找到有测试覆盖的工具名。"""
    tests_root = Path(__file__).resolve().parent.parent.parent / "tests"
    tested = set()
    if not tests_root.exists():
        return tested
    for py_file in tests_root.rglob("test_*.py"):
        try:
            content = py_file.read_text(encoding="utf-8")
        except Exception:
            continue
        # 查找函数名引用模式
        for match in re.finditer(r'"(test_\w+|\w+_test|\w+)"', content):
            tested.add(match.group(1))
        # 也检查 handler 函数名
        for match in re.finditer(r'"_handle_(\w+)"', content):
            tested.add(match.group(1))
        # 检查 tool name 字符串
        for match in re.finditer(r"name\s*=\s*[\"'](\w+)[\"']", content):
            tested.add(match.group(1))
    return tested


def _find_prompt_tools() -> set[str]:
    """扫描 prompt.md 中的反引号工具名（如 `run_statistical_test`）。"""
    prompt_path = Path(__file__).resolve().parent.parent / "prompt.md"
    tools = set()
    if not prompt_path.exists():
        return tools
    content = prompt_path.read_text(encoding="utf-8")
    # 匹配反引号中的工具名模式（小写+下划线，类似函数名）
    for match in re.finditer(r'`([a-z][a-z0-9_]*[a-z0-9])`', content):
        name = match.group(1)
        # 过滤掉明显不是工具名的（如 python、pandas、scipy 等库名）
        if name not in {"python", "pandas", "numpy", "scipy", "pingouin", "json", "csv",
                        "true", "false", "none", "type", "import", "from", "as", "if",
                        "elif", "else", "for", "while", "def", "class", "return", "yield",
                        "with", "try", "except", "raise", "finally", "and", "or", "not",
                        "in", "is", "lambda", "pass", "break", "continue", "self", "cls"}:
            tools.add(name)
    return tools


def _find_method_tools() -> set[str]:
    """从方法文档 frontmatter 中提取所有引用的工具名。"""
    # 用正则直接扫描，避免导入 method_curator（可能触发 pandas）
    methods_root = Path(__file__).resolve().parent.parent.parent / "memory" / "methods"
    all_tools: set[str] = set()
    if not methods_root.exists():
        return all_tools
    import re as _re
    for md_file in methods_root.rglob("*.md"):
        if md_file.name == "__init__.md":
            continue
        text = md_file.read_text(encoding="utf-8")
        # 提取 tools: 列表
        in_tools = False
        in_frontmatter = False
        for line in text.splitlines():
            stripped = line.strip()
            if stripped == "---":
                if not in_frontmatter:
                    in_frontmatter = True
                    continue
                else:
                    break  # 结束 frontmatter
            if not in_frontmatter:
                continue
            if stripped.startswith("tools:"):
                in_tools = True
                # 检查 inline list: tools: [a, b]
                rest = stripped.partition(":")[2].strip()
                if rest.startswith("[") and rest.endswith("]"):
                    for item in rest[1:-1].split(","):
                        item = item.strip().strip("'\"")
                        if item:
                            all_tools.add(item)
                    in_tools = False
                continue
            if in_tools and stripped.startswith("- "):
                tool = stripped[2:].strip().strip("'\"")
                if tool:
                    all_tools.add(tool)
            elif in_tools and not stripped.startswith("- "):
                in_tools = False
    return all_tools


def _is_stat_tool(name: str) -> bool:
    """判断是否为统计类工具。"""
    return any(kw in name.lower() for kw in STAT_TOOL_KEYWORDS)


def _has_stat_metrics(description: str) -> bool:
    """检查 description 是否承诺返回 p/效应量/CI。"""
    lower = description.lower()
    has_p = "p值" in description or "p-value" in lower or "p value" in lower or "p_val" in lower
    has_effect = "效应量" in description or "effect" in lower or "cohen" in lower
    has_ci = "置信区间" in description or "confidence interval" in lower or "ci" in lower
    return has_p or has_effect or has_ci


class ToolCurator:
    """工具箱审计 Agent。只读，不修改工具代码。"""

    def __init__(self) -> None:
        self._prompt_path = Path(__file__).parent / "prompt.md"

    @property
    def prompt(self) -> str:
        if self._prompt_path.exists():
            return self._prompt_path.read_text(encoding="utf-8")
        return ""

    def audit(self) -> ToolAuditReport:
        """执行完整工具箱审计。"""
        tools = _get_registered_tools()
        tool_names = {t["name"] for t in tools}
        tested = _find_tool_tests()
        prompt_tools = _find_prompt_tools()
        method_tools = _find_method_tools()

        report = ToolAuditReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
            total_tools=len(tools),
        )

        # ── 确定性检查 ──

        # TC-06: prompt.md 提到不存在的工具
        for pt in sorted(prompt_tools):
            if pt not in tool_names and pt not in {
                "query_method", "read_method", "save_lesson", "list_lessons",
                "query_lessons", "delete_lesson", "update_project_memory",
                "get_project_memory", "list_tools",
            }:
                # 排除已知的 memory 工具名变体
                if not pt.startswith(("query_", "read_", "save_", "list_",
                                       "update_", "delete_", "create_",
                                       "get_", "set_", "write_", "append_")):
                    report.prompt_fake_tools.append(pt)

        # TC-04: 无测试的工具
        for t_name in sorted(tool_names):
            # 简单启发式：工具名或 handler 名是否在测试文件中出现
            has_test = t_name in tested
            # 也检查常见变体
            if not has_test:
                for variant in [f"test_{t_name}", f"{t_name}_test", t_name]:
                    if variant in tested:
                        has_test = True
                        break
            if has_test:
                report.tools_with_tests += 1
            else:
                report.missing_tests.append(t_name)

        # TC-05: 无方法文档的工具
        for t_name in sorted(tool_names):
            if t_name in method_tools or t_name.startswith(("query_", "read_", "save_",
                                                              "list_", "update_", "delete_",
                                                              "create_", "get_", "set_",
                                                              "write_", "append_", "ask_")):
                report.tools_with_docs += 1
            else:
                report.missing_docs.append(t_name)

        # TC-03: 统计工具缺少 p/效应量/CI
        for t in tools:
            if _is_stat_tool(t["name"]) and not _has_stat_metrics(t["description"]):
                report.stat_tools_without_metrics.append(t["name"])

        # ── LLM 检查（TC-01, TC-02）──
        llm_result = self._llm_audit(tools, prompt_tools, method_tools)
        if llm_result:
            report.llm_findings = llm_result

        return report

    def _llm_audit(
        self,
        tools: list[dict],
        prompt_tools: set[str],
        method_tools: set[str],
    ) -> str | None:
        """调用 Meta LLM 做 description/schema 质量审计（TC-01, TC-02）。"""
        prompt_text = self.prompt
        if not prompt_text:
            return None
        from hagoku.config import HaGoKuConfig
        cfg = HaGoKuConfig.load()
        client = create_raw_client(cfg.llm)
        if client is None:
            raise RuntimeError("ToolCurator: LLM 不可达")

        payload = {
            "tools": [
                {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["parameters"],
                    "has_test": t["name"] not in set(),
                }
                for t in tools
            ],
            "prompt_tools": sorted(prompt_tools),
            "method_tools": sorted(method_tools),
        }
        # EXEMPT: Meta LLM — 工具箱审计，非主对话通道
        messages = build_messages(
            query="tool audit",
            user_input=_json.dumps(payload, ensure_ascii=False, default=str),
            system_extra=prompt_text,
        )
        model = cfg.meta_llm.model or cfg.llm.model
        resp = client.chat.completions.create(
            model=model, messages=messages, temperature=0.0, max_tokens=2048,
        )
        return (resp.choices[0].message.content or "").strip()

    def write_report(self, report: ToolAuditReport) -> Path:
        """将审计报告写入 ~/.hagoku/audits/。"""
        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        ts = report.timestamp[:19].replace(":", "").replace("-", "")
        filename = f"tool_audit_{ts}.md"
        path = AUDIT_DIR / filename

        lines = [
            "# Tool Audit",
            f"Time: {report.timestamp[:19]}",
            "",
            "## Deterministic Results (code-verified, authoritative)",
            f"- Total tools: {report.total_tools}",
            f"- With tests: {report.tools_with_tests}",
            f"- With method docs: {report.tools_with_docs}",
            f"- Prompt references unregistered tools: {len(report.prompt_fake_tools)}",
            f"- Stat tools missing metrics: {len(report.stat_tools_without_metrics)}",
            "",
        ]

        # Blocking
        if report.prompt_fake_tools:
            lines.append("## Blocking (TC-06: prompt references unregistered tools)")
            for t in report.prompt_fake_tools:
                lines.append(f"- `{t}`: mentioned in prompt.md but not registered in agent_tools")
            lines.append("")

        # Warnings
        if report.stat_tools_without_metrics:
            lines.append("## Warnings (TC-03: stat tools missing p/effect/CI in description)")
            for t in report.stat_tools_without_metrics:
                lines.append(f"- `{t}`: stat tool without p-value/effect size/CI in description")
            lines.append("")

        if report.missing_tests:
            lines.append("## Missing Tests (TC-04)")
            for t in report.missing_tests[:20]:
                lines.append(f"- `{t}`")
            if len(report.missing_tests) > 20:
                lines.append(f"- ... and {len(report.missing_tests) - 20} more")
            lines.append("")

        if report.missing_docs:
            lines.append("## Missing Method Docs (TC-05)")
            for t in report.missing_docs[:20]:
                lines.append(f"- `{t}`")
            if len(report.missing_docs) > 20:
                lines.append(f"- ... and {len(report.missing_docs) - 20} more")
            lines.append("")

        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path


# ── 便利函数 ──

def run_tool_audit() -> Path:
    """执行一次工具箱审计，返回报告路径。"""
    curator = ToolCurator()
    report = curator.audit()
    return curator.write_report(report)
