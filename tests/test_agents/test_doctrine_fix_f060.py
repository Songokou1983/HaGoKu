"""F-060 验证：_apply_project_memory 不得覆盖当前 run 用户已纠正的字段。

律 10 要求：confirmed_by_user 标记的字段在当前 run 有最高优先级，
项目记忆不应覆盖用户刚刚纠正的内容。
"""

from hagoku.agents.scout.agent import ScoutAgent


def test_f060_apply_project_memory_respects_confirmed_by_user():
    """F-060 红灯：_apply_project_memory 覆盖 user 已纠正字段。

    修复后：confirmed_by_user=True 的字段不应被项目记忆覆盖。
    """
    agent = ScoutAgent.__new__(ScoutAgent)

    # 场景：Sales 列已被用户在本 run 纠正（confirmed_by_user=True）
    # 项目记忆中 Sales 有旧定义，但不应覆盖用户纠正
    context = {
        "column_semantics": [
            {
                "column_name": "Sales",
                "confidence": 1.0,
                "confirmed_by_user": True,  # 本 run 用户已纠正
            },
            {
                "column_name": "Traffic",
                "confidence": 0.5,
                "confirmed_by_user": False,  # 未被纠正，可被记忆覆盖
            },
        ],
        "column_descriptions": {
            "Sales": "用户纠正后的定义：门店日营收",
        },
        "column_display_names": {},
    }

    memory_project = {
        "fields": {"Sales": "旧记忆中的定义：有可能是月营收"},
        "display_names": {"Sales": "月营收"},
    }

    agent._apply_project_memory(context, memory_project)

    # F-060 红灯断言：当前代码不检查 confirmed_by_user，
    # 会直接用旧记忆覆盖用户纠正
    assert context["column_descriptions"]["Sales"] == "用户纠正后的定义：门店日营收", (
        f"F-060 失败：用户纠正的 Sales 描述被项目记忆覆盖。"
        f"实际 {context['column_descriptions']['Sales']!r}。"
        f"_apply_project_memory 应跳过 confirmed_by_user=True 的字段。"
    )
