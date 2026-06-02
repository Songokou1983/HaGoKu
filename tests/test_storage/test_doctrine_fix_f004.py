"""F-004 验证：learn_from_run 持久化列语义时必须保留 description / display_name。

当前 ColumnSemanticDef(...) 构造不传 description / display_name，
导致用户在 run 1 纠正的字段语义在 run 2 丢失。
"""

from unittest.mock import MagicMock, patch

from hagoku.storage.memory import ColumnSemanticDef, MemoryManager


def test_f004_learn_from_run_preserves_description_and_display_name():
    """F-004 红灯：learn_from_run 构造 ColumnSemanticDef 时不传 description/display_name。

    验证修复后，save_column_semantic 收到的 ColumnSemanticDef 包含 description 和 display_name。
    """
    db = MagicMock()
    mm = MemoryManager(db)

    # 模拟 save_column_semantic 以捕获传入的 ColumnSemanticDef
    captured: list[ColumnSemanticDef] = []

    def capture(_pid, _col, sem_def):
        captured.append(sem_def)

    mm.save_column_semantic = capture

    # 构造含 description / display_name 的 context
    context = {
        "column_semantics": [
            {
                "column_name": "Sales",
                "confidence": 0.95,
                "evidence": "用户确认销售额是门店日营收",
                "inferred_type": "numeric",
                "suggested_role": "target",
                "confirmed_by_user": True,
                "display_name": "日销售额",
                "description": "每个门店每日的销售总收入（元）",
            }
        ]
    }
    mm.learn_from_run("test_proj", context, [], None)

    assert len(captured) == 1, f"预期 save_column_semantic 调用 1 次，实际 {len(captured)}"
    sem_def = captured[0]

    # F-004 红灯断言：当前代码不传 description / display_name，两个字段应均为 None/默认值
    # 修复后这里应等于原始值
    assert sem_def.display_name == "日销售额", (
        f"F-004 失败：display_name 应为 '日销售额'，实际 {sem_def.display_name!r}。"
        f"ColumnSemanticDef(...) 缺少 display_name 参数。"
    )
    assert sem_def.description == "每个门店每日的销售总收入（元）", (
        f"F-004 失败：description 应为 '每个门店每日的销售总收入（元）'，"
        f"实际 {sem_def.description!r}。ColumnSemanticDef(...) 缺少 description 参数。"
    )
