"""Cleaner 暂停：结构化 cleaning_review 载荷。"""

from __future__ import annotations

from dataclasses import dataclass

from hagoku.manager.orchestrator import _normalize_cleaning_operation, cleaning_review_pause_payload


@dataclass
class FakeOp:
    column: str
    strategy: str
    reason: str
    rows_affected: int = 0

    def to_dict(self) -> dict:
        return {
            "column": self.column,
            "strategy": self.strategy,
            "reason": self.reason,
            "rows_affected": self.rows_affected,
        }


class FakeReport:
    total_rows_original = 1000
    total_rows_after = 980
    bias_risk = "medium"
    warnings: list[str] = ["注意：高缺失列"]
    operations = [
        FakeOp("Inc1", "fill_median", "缺失率较高，用中位数填充", 120),
    ]


def test_normalize_cleaning_op_dataclass():
    op = FakeOp("a", "winsorize", "x", 3)
    d = _normalize_cleaning_operation(op)
    assert d["column"] == "a"
    assert d["strategy"] == "winsorize"
    assert d["rows_affected"] == 3


def test_cleaning_review_pause_payload_shape():
    p = cleaning_review_pause_payload(FakeReport(), data_quality="good", impact_rate=0.02)
    assert p["message"] == ""
    cr = p["cleaning_review"]
    assert cr is not None
    assert cr["n_ops"] == 1
    assert cr["total_rows_original"] == 1000
    assert cr["rows_removed"] == 20
    assert cr["impact_rate"] == 0.02
    assert len(cr["rows"]) == 1
    assert cr["rows"][0]["column"] == "Inc1"
    assert len(cr["warnings"]) >= 1


def test_winsorize_no_row_delete_shows_dash_quality():
    class R2:
        total_rows_original = 620
        total_rows_after = 620
        bias_risk = "low"
        warnings: list[str] = []
        operations = [FakeOp("Inc1", "winsorize", "x", 62)]

    p = cleaning_review_pause_payload(R2(), data_quality="unknown", impact_rate=0.0)
    cr = p["cleaning_review"]
    assert cr["rows_removed"] == 0
    assert cr["data_quality"] == "—"
    assert cr["impact_rate"] == 0.0
