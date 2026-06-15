#!/usr/bin/env python3
"""tool_gate — 确定性工具注册表守门脚本。

检查 method 文档、prompt.md、工具注册表三者之间的一致性。
纯确定性规则，不调 LLM。失败 exit(1)，可用于 pre-commit hook 或 CI。

用法:
  python scripts/ci/tool_gate.py [--check-methods] [--check-prompt] [--check-tests] [--check-frontmatter]

规则:
  G1: method 文档 frontmatter 的 tools 列表中每个工具必须存在于 agent_tools
  G2: prompt.md 反引号中的工具名必须已注册
  G3: agent_tools 中每个工具必须有对应的测试文件
  G4: method 文档 frontmatter 必须含 title/category/summary/tags/tools
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# frontmatter 必含字段
REQUIRED_FRONTMATTER = {"title", "category", "summary", "tags", "tools"}

# prompt.md 反引号中排除的非工具名
_NON_TOOL_NAMES = {
    "python", "pandas", "numpy", "scipy", "pingouin", "json", "csv",
    "true", "false", "none", "type", "import", "from", "as", "if",
    "elif", "else", "for", "while", "def", "class", "return", "yield",
    "with", "try", "except", "raise", "finally", "and", "or", "not",
    "in", "is", "lambda", "pass", "break", "continue", "self", "cls",
    "str", "int", "float", "bool", "list", "dict", "set", "tuple",
    "object", "any", "all", "len", "range", "print", "open", "zip",
    "enumerate", "sorted", "reversed", "filter", "map", "max", "min",
    "sum", "abs", "round", "isinstance", "hasattr", "getattr", "setattr",
    "super", "__init__", "__name__", "__main__", "__file__",
    "data", "result", "value", "key", "item", "items", "row", "column",
    "model", "base_url", "api_key", "temperature", "max_tokens",
    "hagoku", "hagoku_web", "hagoku doctor", "agent_tools", "Tool",
    "HaGoKu", "HaGoKuConfig", "LLMConfig", "MetaLLMConfig",
    "DataAnalystAgent", "Orchestrator", "LessonAuditor",
    "MethodCurator", "ToolCurator", "Doctor",
    "ChatTurn", "BuildMessagesInput", "HealthCheckResult",
    "df", "config", "ctx", "args", "context", "client",
    "get_column_stats", "get_sample_rows", "list_columns",
    "group_stats", "check_test_assumptions", "run_statistical_test",
    "assess_statistical_power", "required_sample_size",
    "interpret_nonsignificant", "multiple_comparison_correction",
    "diagnose_regression", "create_plot",
    # Phase D collapsed agent names that may appear in historical docs
    "Scout", "Cleaner", "Analyst", "Reporter", "Manager",
}


def _parse_frontmatter(text: str) -> dict[str, Any]:
    """解析 YAML frontmatter。"""
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
        return {}


def _get_registered_tools() -> set[str]:
    """获取 agent_tools 中所有已注册工具名称。"""
    try:
        sys.path.insert(0, str(PROJECT_ROOT))
        from hagoku.tools.registry import agent_tools
        return set(agent_tools._tools.keys())
    except Exception as e:
        print(f"⚠️  无法加载 agent_tools: {e}", file=sys.stderr)
        return set()


def _discover_methods() -> list[dict[str, Any]]:
    """扫描 memory/methods/ 目录。"""
    methods_root = PROJECT_ROOT / "hagoku" / "memory" / "methods"
    methods = []
    if not methods_root.exists():
        return methods
    for md_file in sorted(methods_root.rglob("*.md")):
        if md_file.name == "__init__.md":
            continue
        text = md_file.read_text(encoding="utf-8")
        fm = _parse_frontmatter(text)
        rel_path = str(md_file.relative_to(methods_root.parent))
        methods.append({"path": rel_path, "frontmatter": fm})
    return methods


def _find_prompt_tools() -> set[str]:
    """扫描 prompt.md 反引号中的潜在工具名。"""
    prompt_path = PROJECT_ROOT / "hagoku" / "agents" / "prompt.md"
    if not prompt_path.exists():
        return set()
    content = prompt_path.read_text(encoding="utf-8")
    tools = set()
    for match in re.finditer(r'`([a-z][a-z0-9_]*[a-z0-9])`', content):
        name = match.group(1)
        if name not in _NON_TOOL_NAMES:
            tools.add(name)
    return tools


def _find_tool_tests() -> set[str]:
    """扫描 tests/ 目录找到已测试的工具名。"""
    tests_root = PROJECT_ROOT / "tests"
    if not tests_root.exists():
        return set()
    tested = set()
    for py_file in tests_root.rglob("test_*.py"):
        try:
            content = py_file.read_text(encoding="utf-8")
        except Exception:
            continue
        for match in re.finditer(r'"(\w+)"', content):
            tested.add(match.group(1))
        for match in re.finditer(r"'(\w+)'", content):
            tested.add(match.group(1))
    return tested


def check_g1(methods: list[dict], registered: set[str]) -> list[str]:
    """G1: method frontmatter tools 引用的工具必须已注册。"""
    errors = []
    for m in methods:
        tools = m["frontmatter"].get("tools", [])
        if isinstance(tools, list):
            for t in tools:
                t_str = str(t).strip()
                if t_str and t_str not in registered:
                    errors.append(f"G1: {m['path']} references '{t_str}' which is not registered")
    return errors


def check_g2(prompt_tools: set[str], registered: set[str]) -> list[str]:
    """G2: prompt.md 反引号工具名必须已注册。"""
    errors = []
    # 排除已知的非工具名和 memory 工具变体
    memory_prefixes = ("query_", "read_", "save_", "list_", "update_",
                        "delete_", "create_", "get_", "set_", "write_",
                        "append_", "ask_")
    for pt in sorted(prompt_tools):
        if pt not in registered:
            # 允许 memory 工具前缀
            if not any(pt.startswith(p) for p in memory_prefixes):
                # 允许包含 in/on/of/by 等看起来像自然语言的名词
                if not any(w in pt for w in ("in_", "on_", "of_", "by_", "to_")):
                    errors.append(f"G2: prompt.md mentions '{pt}' but it is not registered")
    return errors


def check_g3(registered: set[str], tested: set[str]) -> list[str]:
    """G3: 每个工具应有测试。"""
    errors = []
    for t_name in sorted(registered):
        has_test = t_name in tested
        if not has_test:
            for variant in [f"test_{t_name}", f"{t_name}_test"]:
                if variant in tested:
                    has_test = True
                    break
        if not has_test:
            errors.append(f"G3: '{t_name}' has no test coverage")
    return errors


def check_g4(methods: list[dict]) -> list[str]:
    """G4: frontmatter 必含 title/category/summary/tags/tools。"""
    errors = []
    for m in methods:
        fm = m["frontmatter"]
        missing = [f for f in REQUIRED_FRONTMATTER if f not in fm or not fm[f]]
        if missing:
            errors.append(f"G4: {m['path']} missing frontmatter: {missing}")
    return errors


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="tool_gate — CI 工具注册表守门")
    parser.add_argument("--check-methods", action="store_true", default=True,
                        help="Check G1 (default)")
    parser.add_argument("--check-prompt", action="store_true", default=True,
                        help="Check G2 (default)")
    parser.add_argument("--check-tests", action="store_true", default=True,
                        help="Check G3 (default)")
    parser.add_argument("--check-frontmatter", action="store_true", default=True,
                        help="Check G4 (default)")
    parser.add_argument("--g1-only", action="store_true", help="Only G1")
    parser.add_argument("--g2-only", action="store_true", help="Only G2")
    parser.add_argument("--g3-only", action="store_true", help="Only G3")
    parser.add_argument("--g4-only", action="store_true", help="Only G4")
    args = parser.parse_args()

    # 如果指定了 --gX-only，只跑对应规则
    if any([args.g1_only, args.g2_only, args.g3_only, args.g4_only]):
        args.check_methods = args.g1_only
        args.check_prompt = args.g2_only
        args.check_tests = args.g3_only
        args.check_frontmatter = args.g4_only

    all_errors: list[str] = []

    # 只在需要时才加载 agent_tools（避免 pandas 依赖问题在 --g4-only 时阻塞）
    need_registry = args.check_methods or args.check_prompt or args.check_tests
    registered: set[str] = set()
    if need_registry:
        registered = _get_registered_tools()
        if not registered:
            print("❌ tool_gate: 无法加载 agent_tools 注册表", file=sys.stderr)
            return 1

    if args.check_methods or args.check_frontmatter:
        methods = _discover_methods()
        if not methods:
            print("⚠️  tool_gate: 未发现方法文档", file=sys.stderr)

        if args.check_methods:
            all_errors.extend(check_g1(methods, registered))
        if args.check_frontmatter:
            all_errors.extend(check_g4(methods))

    if args.check_prompt:
        prompt_tools = _find_prompt_tools()
        all_errors.extend(check_g2(prompt_tools, registered))

    if args.check_tests:
        tested = _find_tool_tests()
        all_errors.extend(check_g3(registered, tested))

    if all_errors:
        print(f"❌ tool_gate: {len(all_errors)} violation(s):", file=sys.stderr)
        for err in all_errors:
            print(f"  {err}", file=sys.stderr)
        return 1

    tool_count = len(registered) if registered else "?"
    print(f"✅ tool_gate: all checks passed ({tool_count} tools)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
