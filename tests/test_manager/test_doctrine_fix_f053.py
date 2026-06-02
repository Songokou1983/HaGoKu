"""F-053 验证：_apply_field_corrections 必须同步 description / display_name 到 column_semantics。

当前只写 evidence 和 needs_user_input，漏了 description 和 display_name，
导致 column_semantics 与 column_descriptions 不同步。
"""

from hagoku.config import HaGoKuConfig
from hagoku.manager.orchestrator import Orchestrator


def test_f053_apply_field_corrections_syncs_description_and_display_name():
    """F-053 红灯：_apply_field_corrections 不同步 description / display_name。

    修复后，column_semantics 中对应字段的 description 和 display_name 应被更新。
    """
    orch = Orchestrator(HaGoKuConfig())

    context = {
        "column_semantics": [
            {
                "column_name": "Sales",
                "evidence": "",
                "needs_user_input": True,
                "description": "",
                "display_name": "",
            }
        ],
        "column_descriptions": {},
    }
    corrections: dict = {}
    updates = {
        "Sales": {
            "chinese_name": "日销售额",
            "business_meaning": "每个门店每日的销售总收入",
        }
    }

    orch._apply_field_corrections(context, corrections, updates)

    sem = context["column_semantics"][0]

    # F-053 红灯断言：当前代码不写 description / display_name
    assert sem["description"] == "每个门店每日的销售总收入", (
        f"F-053 失败：description 应为 '每个门店每日的销售总收入'，"
        f"实际 {sem['description']!r}。_apply_field_corrections 漏写 s['description']。"
    )
    assert sem["display_name"] == "日销售额", (
        f"F-053 失败：display_name 应为 '日销售额'，"
        f"实际 {sem['display_name']!r}。_apply_field_corrections 漏写 s['display_name']。"
    )
