"""CO-T30: 测试 query_method frontmatter tags 命中"""

from hagoku.tools.registry import agent_tools
from hagoku.tools.memory_tools import _METHODS_ROOT


class TestQueryMethod:
    """测试 query_method 和 read_method 增强"""

    def test_query_method_tags_hit(self):
        """query_method('功效分析') 命中 power-analysis.md"""
        handler = agent_tools.get("query_method").handler
        result = handler({"question": "功效分析"}, {}, None)
        assert "matches" in result
        assert result["count"] >= 1
        paths = [m["path"] for m in result["matches"]]
        assert any("power-analysis" in p for p in paths), f"未命中 power-analysis，命中: {paths}"

    def test_query_method_ttest_hit(self):
        """query_method('t检验') 命中 ttest.md"""
        handler = agent_tools.get("query_method").handler
        result = handler({"question": "t检验 独立样本"}, {}, None)
        paths = [m["path"] for m in result["matches"]]
        assert any("ttest" in p for p in paths), f"未命中 ttest，命中: {paths}"

    def test_query_method_scope_filter(self):
        """scope 过滤只搜索指定目录"""
        handler = agent_tools.get("query_method").handler
        result = handler({"question": "选择", "scope": ["statistics"]}, {}, None)
        paths = [m["path"] for m in result["matches"]]
        # 所有结果应在 statistics/ 下
        assert all(p.startswith("statistics/") for p in paths), f"scope 过滤失败: {paths}"

    def test_query_method_returns_tags(self):
        """query_method 返回 frontmatter tags"""
        handler = agent_tools.get("query_method").handler
        result = handler({"question": "t检验"}, {}, None)
        for m in result["matches"]:
            assert "tags" in m
            assert isinstance(m["tags"], list)

    def test_read_method_returns_tools(self):
        """read_method 返回 tools 列表"""
        handler = agent_tools.get("read_method").handler
        result = handler({"path": "statistics/ttest.md"}, {}, None)
        assert "tools" in result
        assert isinstance(result["tools"], list)
        assert "run_statistical_test" in result["tools"] or "check_test_assumptions" in result["tools"]

    def test_read_method_returns_title(self):
        """read_method 返回 frontmatter title"""
        handler = agent_tools.get("read_method").handler
        result = handler({"path": "statistics/power-analysis.md"}, {}, None)
        assert "title" in result
        assert "title" in result
        assert len(result["title"]) > 0

    def test_read_method_invalid_path(self):
        """非法路径返回 error"""
        handler = agent_tools.get("read_method").handler
        result = handler({"path": "../etc/passwd"}, {}, None)
        assert "error" in result

    def test_query_method_empty_question(self):
        """空 question 返回 error"""
        handler = agent_tools.get("query_method").handler
        result = handler({"question": ""}, {}, None)
        assert "error" in result

    def test_methods_root_exists(self):
        """方法库根目录存在且有文件"""
        assert _METHODS_ROOT.exists()
        mds = list(_METHODS_ROOT.rglob("*.md"))
        assert len(mds) >= 5, f"方法文档不足，只有 {len(mds)} 篇"
