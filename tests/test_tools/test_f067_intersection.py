"""F-067 R 等级验证：update_analysis_scope 交集检测"""
import pytest
from hagoku.tools.agent_tool_defs import _handle_update_analysis_scope

def test_normal_add():
    """正常添加列"""
    ctx = {"column_semantics": [{"column_name": "A", "used_in_analysis": False}]}
    result = _handle_update_analysis_scope(
        {"add_columns": ["A"], "remove_columns": [], "reason": "test"}, ctx, None
    )
    assert result["added"] == ["A"]
    assert result["removed"] == []
    assert ctx["column_semantics"][0]["used_in_analysis"] is True

def test_normal_remove():
    """正常移除列"""
    ctx = {"column_semantics": [{"column_name": "A", "used_in_analysis": True}]}
    result = _handle_update_analysis_scope(
        {"add_columns": [], "remove_columns": ["A"], "reason": "test"}, ctx, None
    )
    assert result["added"] == []
    assert result["removed"] == ["A"]
    assert ctx["column_semantics"][0]["used_in_analysis"] is False

def test_conflict_raises():
    """同一列同时 add+remove → ValueError"""
    ctx = {"column_semantics": [{"column_name": "A", "used_in_analysis": False}]}
    with pytest.raises(ValueError, match="同时出现在"):
        _handle_update_analysis_scope(
            {"add_columns": ["A"], "remove_columns": ["A"], "reason": "test"}, ctx, None
        )

def test_empty_columns():
    """空 add/remove 不抛异常"""
    ctx = {"column_semantics": [{"column_name": "A"}]}
    result = _handle_update_analysis_scope(
        {"add_columns": [], "remove_columns": [], "reason": ""}, ctx, None
    )
    assert result["added"] == []
    assert result["removed"] == []
