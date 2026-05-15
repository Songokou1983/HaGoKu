"""Scout 字段核对：结构化 field_review 载荷（非 Markdown 台词）"""

from hagoku.config import HaGoKuConfig
from hagoku.manager.orchestrator import Orchestrator, scout_field_review_pause_payload


def test_scout_field_review_payload_shape():
    ctx = {
        "n_rows": 10,
        "column_semantics": [
            {"column_name": "id", "needs_user_input": False},
            {"column_name": "amt", "needs_user_input": True},
        ],
        "column_descriptions": {
            "id": "多为标识字段（例：1, 2）",
            "amt": "多为收入侧指标（例：3.5）",
        },
        "column_display_names": {},
    }
    p = scout_field_review_pause_payload(ctx)
    assert p["message"] == ""
    assert p["field_review"] is not None
    assert p["field_review"]["n_rows"] == 10
    assert p["field_review"]["n_cols"] == 2
    assert len(p["field_review"]["rows"]) == 2
    assert p["field_review"]["rows"][0]["field_name"] == "id"
    # chinese_name 优先 column_display_names；否则从含义中抽短标签
    assert "标识" in p["field_review"]["rows"][0]["chinese_name"]
    assert "标识" in p["field_review"]["rows"][0]["meaning"]
    assert p["field_review"]["rows"][1]["needs_attention"] is True
    assert "收入" in p["field_review"]["rows"][1]["chinese_name"]
    assert "收入" in p["field_review"]["rows"][1]["meaning"]


def test_scout_field_review_chinese_name_from_display_names():
    ctx = {
        "n_rows": 1,
        "column_semantics": [
            {
                "column_name": "Inc01",
                "needs_user_input": False,
                "inferred_type": "float",
                "suggested_role": "measure",
            },
        ],
        "column_descriptions": {"Inc01": "业务口径下的收入金额，单位与源表一致。"},
        "column_display_names": {"Inc01": "收入01"},
    }
    p = scout_field_review_pause_payload(ctx)
    row = p["field_review"]["rows"][0]
    assert row["field_name"] == "Inc01"
    assert row["chinese_name"] == "收入01"
    assert "收入" in row["meaning"] or "业务" in row["meaning"]


def test_scout_pause_attach_leaves_message_empty():
    """Scout 字段暂停：不在编排层注入对话气泡文案。"""
    orch = Orchestrator(HaGoKuConfig())
    ctx = {
        "n_rows": 1,
        "column_semantics": [{"column_name": "x", "needs_user_input": True}],
        "column_descriptions": {},
        "column_display_names": {},
    }
    p = scout_field_review_pause_payload(ctx)
    p["interaction_revision"] = 3
    out = orch._attach_pause_dialogue_message("scout", p)
    assert out.get("message") == ""
