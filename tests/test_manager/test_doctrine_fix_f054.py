"""F-054 验证：analyst.submit_analysis 返回的 dict key 与 orchestrator 调用侧一致。

当前 orch.py:1949-1963 使用不存在的 key（preliminary_findings/suggested_focus/
power_warnings/business_metrics），而 submit_analysis handler 实际返回
{findings, method_used, summary}。
"""

from hagoku.tools.agent_tool_defs import _handle_submit_analysis


def test_f054_submit_analysis_returns_expected_keys():
    """F-054 红灯：验证 submit_analysis handler 返回的 key 集合。

    这个测试记录 _handle_submit_analysis 的返回契约。
    orchestrator 调用方必须使用这里定义的 key。
    """
    result = _handle_submit_analysis(
        args={
            "findings": [
                {
                    "title": "销售额与客流量正相关",
                    "detail": "Pearson r=0.85, p<0.001",
                    "evidence_columns": ["Sales", "Traffic"],
                    "confidence": "high",
                }
            ],
            "method_used": ["pearson_correlation", "linear_regression"],
            "summary": "分析发现销售额与客流量呈强正相关",
        },
        ctx={},
        _df=None,
    )

    # 契约：返回 dict 必须包含这三个 key
    assert isinstance(result, dict)
    assert "findings" in result
    assert "method_used" in result
    assert "summary" in result

    # 契约：findings 是列表，每项有 title/detail/evidence_columns/confidence
    assert isinstance(result["findings"], list)
    assert len(result["findings"]) == 1
    f0 = result["findings"][0]
    assert f0["title"] == "销售额与客流量正相关"

    # 契约：不存在 orchestrator 旧代码期望的 key
    assert "preliminary_findings" not in result
    assert "suggested_focus" not in result
    assert "power_warnings" not in result
    assert "business_metrics" not in result
