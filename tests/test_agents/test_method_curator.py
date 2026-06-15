"""MethodCurator 测试 — frontmatter 解析、缺失工具检测、报告生成"""
import importlib.util
import sys
import tempfile
from pathlib import Path

import pytest

# 直接加载模块文件，绕过 hagoku.agents.__init__ 的 pandas 依赖
def _load_module(name, filepath):
    spec = importlib.util.spec_from_file_location(name, filepath)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

_agent_mod = _load_module(
    "method_curator_agent",
    Path(__file__).resolve().parent.parent.parent / "hagoku" / "agents" / "method_curator" / "agent.py",
)

_parse_frontmatter = _agent_mod._parse_frontmatter
_parse_tools_list = _agent_mod._parse_tools_list
_strip_frontmatter = _agent_mod._strip_frontmatter
_discover_methods = _agent_mod._discover_methods
_get_registered_tool_names = _agent_mod._get_registered_tool_names
MethodCurator = _agent_mod.MethodCurator
REQUIRED_FRONTMATTER = _agent_mod.REQUIRED_FRONTMATTER


class TestFrontmatterParsing:
    """MC-01: frontmatter 解析"""

    def test_parse_valid_frontmatter(self):
        text = """---
title: t 检验选择指南
category: statistics
tags: [t检验, 假设检验]
summary: t 检验的选择逻辑
tools:
  - check_test_assumptions
  - run_statistical_test
---
# Body
"""
        fm = _parse_frontmatter(text)
        assert fm["title"] == "t 检验选择指南"
        assert fm["category"] == "statistics"
        assert fm["summary"] == "t 检验的选择逻辑"
        assert "check_test_assumptions" in fm["tools"]
        assert "run_statistical_test" in fm["tools"]

    def test_parse_no_frontmatter(self):
        text = "# Just a heading\n\nSome content."
        fm = _parse_frontmatter(text)
        assert fm == {}

    def test_parse_empty_frontmatter(self):
        text = "---\n---\n# Body"
        fm = _parse_frontmatter(text)
        assert fm == {}

    def test_parse_missing_fields(self):
        text = """---
title: Only Title
---
# Body
"""
        fm = _parse_frontmatter(text)
        assert fm["title"] == "Only Title"
        assert "category" not in fm

    def test_parse_tools_list_inline(self):
        yaml_str = "tools: [calc_roi, calc_roas]"
        tools = _parse_tools_list(yaml_str)
        assert "calc_roi" in tools
        assert "calc_roas" in tools

    def test_parse_tools_list_multiline(self):
        yaml_str = "tools:\n  - tool_a\n  - tool_b"
        tools = _parse_tools_list(yaml_str)
        assert "tool_a" in tools
        assert "tool_b" in tools


class TestStripFrontmatter:
    def test_strip(self):
        text = "---\ntitle: X\n---\n\n# Real Body\ncontent here"
        body = _strip_frontmatter(text)
        assert "# Real Body" in body
        assert "content here" in body
        assert "title: X" not in body

    def test_no_frontmatter(self):
        text = "# Just body"
        body = _strip_frontmatter(text)
        assert body == text


class TestDiscoverMethods:
    def test_discovers_real_methods(self):
        """验证能发现真实的 method 文件（至少 5 篇统计文档）。"""
        methods = _discover_methods()
        assert len(methods) >= 5, f"Expected >=5 methods, got {len(methods)}"
        # 每个 method 应有 path, frontmatter, body_preview
        for m in methods:
            assert "path" in m
            assert "frontmatter" in m
            assert "body_preview" in m

    def test_methods_have_frontmatter(self):
        """所有真实 method 文档前端应有 title。"""
        methods = _discover_methods()
        for m in methods:
            fm = m["frontmatter"]
            # 大部分应有 title，跳过可能的空文件
            if fm:
                assert "title" in fm, f"{m['path']} missing title"


class TestRegisteredTools:
    def test_get_registered_tool_names(self):
        """验证能获取已注册工具名（可能因环境依赖问题返回空集）。"""
        names = _get_registered_tool_names()
        # 在正常环境应有工具；在受限环境返回空集也接受
        assert isinstance(names, set)
        if names:
            core_tools = {"get_column_stats", "list_columns", "run_statistical_test"}
            found = names & core_tools
            assert found, f"Core tools missing from registry: {core_tools - names}"


class TestMethodCuratorAudit:
    def test_audit_produces_report(self, tmp_path):
        """审计应产生非空报告。"""
        # 创建临时方法文档
        methods_dir = tmp_path / "methods" / "statistics"
        methods_dir.mkdir(parents=True)
        (methods_dir / "test_method.md").write_text("""---
title: Test Method
category: statistics
tags: [test]
summary: A test method
tools:
  - run_statistical_test
---
# Test Method

## 适用场景
For testing.

## 假设
None.

## 局限
Limited.

## 报告格式
Standard.
""", encoding="utf-8")

        # 直接设置模块属性
        _agent_mod._METHODS_ROOT = methods_dir

        curator = MethodCurator()
        # 不走 LLM audit
        curator._prompt_path = tmp_path / "nonexistent.md"
        report = curator.audit()

        assert report.total_methods == 1
        assert len(report.missing_frontmatter) == 0  # 已齐全
        assert "run_statistical_test" in report.tools_referenced

    def test_detects_missing_frontmatter(self, tmp_path):
        """检测 frontmatter 缺少必含字段（MC-01）。"""
        methods_dir = tmp_path / "methods" / "statistics"
        methods_dir.mkdir(parents=True)
        (methods_dir / "incomplete.md").write_text("""---
title: Only Title
---
# Body
""", encoding="utf-8")

        _agent_mod._METHODS_ROOT = methods_dir

        curator = MethodCurator()
        curator._prompt_path = tmp_path / "nonexistent.md"
        report = curator.audit()

        assert len(report.missing_frontmatter) >= 1
        missing_item = report.missing_frontmatter[0]
        assert "incomplete.md" in missing_item["path"]
        assert "category" in missing_item["missing"]

    def test_detects_unregistered_tool_ref(self, tmp_path):
        """检测方法文档引用未注册工具（MC-02）。"""
        methods_dir = tmp_path / "methods" / "statistics"
        methods_dir.mkdir(parents=True)
        (methods_dir / "bad_ref.md").write_text("""---
title: Bad Ref
category: statistics
tags: [test]
summary: test
tools:
  - nonexistent_tool_xyz
---
# Body
""", encoding="utf-8")

        _agent_mod._METHODS_ROOT = methods_dir

        curator = MethodCurator()
        curator._prompt_path = tmp_path / "nonexistent.md"
        report = curator.audit()

        missing = [m for m in report.missing_tools if m["tool"] == "nonexistent_tool_xyz"]
        assert len(missing) >= 1, f"Expected to find unregistered tool 'nonexistent_tool_xyz' in {report.missing_tools}"

    def test_write_report(self, tmp_path):
        """报告应写入指定路径。"""
        _agent_mod.AUDIT_DIR = tmp_path / "audits"
        methods_dir = tmp_path / "methods" / "statistics"
        methods_dir.mkdir(parents=True)
        (methods_dir / "ok.md").write_text("""---
title: OK
category: statistics
tags: [ok]
summary: ok
tools: []
---
# OK
""", encoding="utf-8")
        _agent_mod._METHODS_ROOT = methods_dir

        curator = MethodCurator()
        curator._prompt_path = tmp_path / "nonexistent.md"
        report = curator.audit()
        path = curator.write_report(report)

        assert path.exists()
        content = path.read_text()
        assert "# Method Audit" in content
        assert "Total methods" in content
