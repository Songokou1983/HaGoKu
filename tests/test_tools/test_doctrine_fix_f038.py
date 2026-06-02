"""F-038 验证：business.py 计算函数不得返回硬编码中文 interpretation/health 字符串。

铁律 1（零硬编码）：业务结论（"回报丰厚"/"效果优秀"/"健康度差"）应由 LLM 解读，
代码只负责计算和返回 raw 数值。
"""

import pandas as pd

from hagoku.tools.business import calc_roi, calc_roas, calc_ltv_cac_ratio


def test_f038_calc_roi_no_interpretation_string():
    """F-038 红灯：calc_roi 不应返回硬编码中文 interpretation。

    修复后应只返回 raw 数值（roi、net_profit 等），interpretation 由 LLM 生成。
    """
    result = calc_roi(revenue=1000.0, cost=400.0)
    assert "interpretation" not in result, (
        f"F-038 失败：calc_roi 返回了硬编码 interpretation 字符串。"
        f"业务结论应由 LLM 根据 raw 数值自行解读。"
        f"返回 key: {list(result.keys())}"
    )


def test_f038_calc_roas_no_interpretation_string():
    """F-038 红灯：calc_roas 不应返回硬编码中文 interpretation。"""
    result = calc_roas(revenue=2000.0, ad_spend=500.0)
    assert "interpretation" not in result, (
        f"F-038 失败：calc_roas 返回了硬编码 interpretation 字符串。"
        f"返回 key: {list(result.keys())}"
    )


def test_f038_calc_ltv_cac_ratio_no_health_string():
    """F-038 红灯：calc_ltv_cac_ratio 不应返回硬编码中文 health 字符串。

    修复后应只返回 raw ratio 数值，健康度结论由 LLM 解读。
    """
    result = calc_ltv_cac_ratio(ltv=500.0, cac=100.0)
    assert "health" not in result, (
        f"F-038 失败：calc_ltv_cac_ratio 返回了硬编码 health 字符串。"
        f"返回 key: {list(result.keys())}"
    )
