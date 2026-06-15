"""tool_gate 测试 — G1-G4 确定性守门规则"""
import tempfile
from pathlib import Path

import pytest

# 将被测函数导入路径
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.ci.tool_gate import (
    check_g1,
    check_g2,
    check_g3,
    check_g4,
    _parse_frontmatter,
)


class TestFrontmatterParsing:
    def test_parse_valid(self):
        text = """---
title: Test
category: stats
summary: A test
tags: [a, b]
tools:
  - tool_a
---
Body
"""
        fm = _parse_frontmatter(text)
        assert fm["title"] == "Test"
        assert fm["category"] == "stats"
        assert "tool_a" in fm["tools"]

    def test_parse_empty(self):
        assert _parse_frontmatter("No frontmatter") == {}
        assert _parse_frontmatter("---\n---\nBody") == {}


class TestG1:
    """G1: method frontmatter 工具引用必须已注册"""

    def test_all_valid(self):
        methods = [
            {"path": "methods/a.md", "frontmatter": {"tools": ["tool_a", "tool_b"]}},
        ]
        registered = {"tool_a", "tool_b", "tool_c"}
        errors = check_g1(methods, registered)
        assert errors == []

    def test_missing_tool(self):
        methods = [
            {"path": "methods/a.md", "frontmatter": {"tools": ["tool_a", "fake_tool"]}},
        ]
        registered = {"tool_a", "tool_b"}
        errors = check_g1(methods, registered)
        assert len(errors) == 1
        assert "fake_tool" in errors[0]
        assert "methods/a.md" in errors[0]

    def test_no_tools_field(self):
        methods = [
            {"path": "methods/a.md", "frontmatter": {"title": "X"}},
        ]
        registered = {"tool_a"}
        errors = check_g1(methods, registered)
        assert errors == []  # 没有 tools 字段则不产生错误


class TestG2:
    """G2: prompt.md 反引号工具名必须已注册"""

    def test_all_registered(self):
        prompt_tools = {"tool_a", "tool_b"}
        registered = {"tool_a", "tool_b", "tool_c"}
        errors = check_g2(prompt_tools, registered)
        assert errors == []

    def test_fake_tool(self):
        prompt_tools = {"tool_a", "fake_tool_xyz"}
        registered = {"tool_a", "tool_b"}
        errors = check_g2(prompt_tools, registered)
        assert len(errors) >= 1
        assert any("fake_tool_xyz" in e for e in errors)

    def test_memory_prefix_exempt(self):
        """memory 工具前缀应被豁免。"""
        prompt_tools = {"query_something", "save_something", "read_something"}
        registered = set()
        errors = check_g2(prompt_tools, registered)
        assert errors == []


class TestG3:
    """G3: 每个工具应有测试"""

    def test_tool_with_test(self):
        registered = {"tool_a"}
        tested = {"tool_a", "test_tool_a"}
        errors = check_g3(registered, tested)
        # tool_a 在 tested 中，或者 test_tool_a 在 tested 中
        assert "tool_a" not in [e.split("'")[1] for e in errors if "'" in e]

    def test_tool_without_test(self):
        registered = {"untested_tool"}
        tested = {"tool_a"}
        errors = check_g3(registered, tested)
        assert len(errors) == 1
        assert "untested_tool" in errors[0]


class TestG4:
    """G4: frontmatter 必含字段"""

    def test_all_present(self):
        methods = [
            {"path": "methods/a.md", "frontmatter": {
                "title": "T", "category": "C", "summary": "S",
                "tags": ["t"], "tools": ["x"],
            }},
        ]
        errors = check_g4(methods)
        assert errors == []

    def test_missing_title(self):
        methods = [
            {"path": "methods/incomplete.md", "frontmatter": {
                "category": "C", "summary": "S", "tags": ["t"], "tools": ["x"],
            }},
        ]
        errors = check_g4(methods)
        assert len(errors) == 1
        assert "title" in errors[0]
        assert "methods/incomplete.md" in errors[0]

    def test_missing_multiple(self):
        methods = [
            {"path": "methods/bad.md", "frontmatter": {}},
        ]
        errors = check_g4(methods)
        assert len(errors) == 1
        assert "title" in errors[0]
        assert "category" in errors[0]

    def test_empty_values_treated_as_missing(self):
        """空字符串或空列表应视为缺失。"""
        methods = [
            {"path": "methods/empty.md", "frontmatter": {
                "title": "", "category": "C", "summary": "S",
                "tags": [], "tools": [],
            }},
        ]
        errors = check_g4(methods)
        assert len(errors) == 1
        assert "title" in errors[0]
        assert "tags" in errors[0]
        assert "tools" in errors[0]
