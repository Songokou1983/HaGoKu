"""Scout 字段核对：结构化 field_review 载荷（非 Markdown 台词）"""

from hagoku.manager.orchestrator import scout_field_review_pause_payload


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
    assert p["field_review"]["rows"][1]["needs_attention"] is True
