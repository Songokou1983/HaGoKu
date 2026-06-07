# tests/test_product/test_tool_schema_coverage.py
"""律 4（工具 schema 覆盖完备）契约测试 — CH-6。

每个阶段的用户合理纠正措辞，必须能在对应 Agent 的工具集中找到落点。
落点 = 至少一个工具的 parameters 字段名匹配该维度。
"""
from __future__ import annotations

import pytest
from hagoku.tools.registry import agent_tools

# ── Scout：字段理解 + 角色分配 + 分析范围 ───────────────────────

SCOUT_USER_INTENTS = [
    # display_name / description 维度
    ("把 Code 改成中文名 '店铺编号'", "update_field_understanding", "display_name"),
    ("Code 的含义是唯一标识每个店铺的编码", "update_field_understanding", "description"),
    ("Inc1 的中文名应该是销售额", "update_field_understanding", "display_name"),
    ("Period 其实是周次", "update_field_understanding", "display_name"),
    # suggested_role / used_in_analysis 维度
    ("Inc1 是目标变量", "update_field_role", "target"),
    ("只用 Inc1 Inc2 Inc3 三列分析", "restrict_analysis_to", "included_fields"),
    ("StoreID 是标识列不用分析", "update_field_understanding", "suggested_role"),
    ("销售额应该是 feature 不是 target", "update_field_role", "features"),
    ("除了 StoreID 其他都参与分析", "restrict_analysis_to", "included_fields"),
    # 数据探查工具
    ("Code 列里都有哪些值", "get_sample_rows", "column"),
    ("Inc1 的统计分布如何", "get_column_stats", "column"),
    # 控制路由
    ("好，可以进入清洗阶段了", "route_to", "stage"),
]

CLEANER_USER_INTENTS = [
    # 清洗评估
    ("Code 列不需要清洗", "update_assessment", "action"),
    ("Inc1 缺失率太高应该清理", "update_assessment", "reason"),
    ("Period 列确实有异常值要处理", "update_assessment", "column"),
    # 字段表格更新
    ("StoreID 列暂时跳过", "update_field_table", "columns"),
    ("把 Code 的清洗原因改一下", "update_assessment", "column"),
    # 数据探查
    ("看看 Inc1 列的分布", "get_column_stats", "column"),
    ("Code 列按渠道分组统计", "group_stats", "by"),
    ("列个字段清单", "list_columns", None),  # list_columns 无 required params，tool 存在即通过
    # 提交
    ("确认清洗方案，可以继续了", "submit_assessment", "columns"),
    # 控制路由
    ("进入分析阶段", "route_to", "stage"),
]

ANALYST_USER_INTENTS = [
    # 方法提议
    ("我建议用线性回归分析", "propose_method", "method_name"),
    ("用 t 检验比较两组差异", "run_statistical_test", "test_type"),
    ("做一下相关性分析", "run_statistical_test", "test_type"),
    # 分析范围
    ("把 Inc2 也纳入分析", "update_analysis_scope", "add_columns"),
    ("移除 StoreID 这个字段", "update_analysis_scope", "remove_columns"),
    # 提问
    ("你觉得用哪种方法更合适", "ask_user", "question"),
    ("要不要排除离群值", "ask_user", "options"),
    # 提交
    ("分析完成，可以生成报告了", "submit_analysis", "findings"),
    # 数据探查
    ("看看销售额的统计量", "get_column_stats", "column"),
    # 控制路由
    ("继续到报告阶段", "route_to", "stage"),
]

REPORTER_USER_INTENTS = [
    # 数据探查（Reporter 仅有数据探查工具）
    ("给我看下原始数据的列名", "list_columns", None),
    ("看看 Inc1 的统计分布", "get_column_stats", "column"),
    ("Inc1 有哪些取值", "get_sample_rows", "column"),
    # 字段表格
    ("字段表里有哪几列", "list_columns", None),
    ("验证一下目标变量的数据", "get_column_stats", "column"),
    ("抽样看看数据质量", "get_sample_rows", "n"),
    ("查看 Inc2 的统计信息", "get_column_stats", "column"),
    ("列出所有字段", "list_columns", None),
    # 控制路由
    ("确认完成", "route_to", "stage"),
]


def _get_tools_for(agent: str) -> dict[str, dict]:
    """返回 agent 的工具集，key=name, value=function dict。"""
    tools = agent_tools.to_openai(agent)
    return {t["function"]["name"]: t["function"] for t in tools}


def _assert_param_exists(tools: dict, tool_name: str, param: str | None, utterance: str):
    """断言指定工具存在，且参数（如果指定）在 parameters.properties 中。"""
    tool = tools.get(tool_name)
    assert tool is not None, (
        f"律 4 残缺：工具 '{tool_name}' 不在 {list(tools.keys())} 中\n"
        f"用户说：「{utterance}」→ 无落点"
    )
    if param is not None:
        params = tool.get("parameters", {}).get("properties", {})
        assert param in params, (
            f"律 4 残缺：工具 '{tool_name}' 缺少参数 '{param}'\n"
            f"现有参数：{list(params.keys())}\n"
            f"用户说：「{utterance}」→ 落点缺维度"
        )


class TestScoutToolSchemaCoverage:
    @pytest.mark.parametrize("utterance,tool_name,param", SCOUT_USER_INTENTS)
    def test_scout_coverage(self, utterance, tool_name, param):
        tools = _get_tools_for("scout")
        _assert_param_exists(tools, tool_name, param, utterance)


class TestCleanerToolSchemaCoverage:
    @pytest.mark.parametrize("utterance,tool_name,param", CLEANER_USER_INTENTS)
    def test_cleaner_coverage(self, utterance, tool_name, param):
        tools = _get_tools_for("cleaner")
        _assert_param_exists(tools, tool_name, param, utterance)


class TestAnalystToolSchemaCoverage:
    @pytest.mark.parametrize("utterance,tool_name,param", ANALYST_USER_INTENTS)
    def test_analyst_coverage(self, utterance, tool_name, param):
        tools = _get_tools_for("analyst")
        _assert_param_exists(tools, tool_name, param, utterance)


class TestReporterToolSchemaCoverage:
    @pytest.mark.parametrize("utterance,tool_name,param", REPORTER_USER_INTENTS)
    def test_reporter_coverage(self, utterance, tool_name, param):
        tools = _get_tools_for("reporter")
        _assert_param_exists(tools, tool_name, param, utterance)
