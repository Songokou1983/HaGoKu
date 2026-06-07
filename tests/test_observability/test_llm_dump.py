# tests/test_observability/test_llm_dump.py
"""llm_dump 契约守护测试 — CH-4 fixup。

双契约变更：
1. HAGOKU_DUMP_LLM 语义反转：原 =1 才写，现默认开，=0 才关
2. 路径迁移：~/.hagoku/llm_dumps/ → run_dir/llm_dumps/
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from hagoku.observability import llm_dump


def _make_messages():
    return [
        {"role": "system", "content": "你是数据分析师。"},
        {"role": "user", "content": "分析这份数据。"},
    ]


# ── 契约 1：HAGOKU_DUMP_LLM 语义反转 ────────────────────────


def test_dump_default_enabled_no_env_var(monkeypatch):
    """未设 HAGOKU_DUMP_LLM 时默认开启，dump 写入文件。"""
    monkeypatch.delenv("HAGOKU_DUMP_LLM", raising=False)

    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        llm_dump.set_run_dir(run_dir)

        llm_dump.dump_messages("test_stage", _make_messages(), model="test-model")

        dump_dir = run_dir / "llm_dumps"
        files = list(dump_dir.glob("*.json"))
        assert len(files) == 1, f"默认开启时应有 1 个 dump 文件，实际 {len(files)}"


def test_dump_disabled_when_env_zero(monkeypatch):
    """HAGOKU_DUMP_LLM=0 时关闭，不写文件。"""
    monkeypatch.setenv("HAGOKU_DUMP_LLM", "0")

    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        llm_dump.set_run_dir(run_dir)

        llm_dump.dump_messages("test_stage", _make_messages(), model="test-model")

        dump_dir = run_dir / "llm_dumps"
        assert not dump_dir.exists() or len(list(dump_dir.glob("*.json"))) == 0, (
            "HAGOKU_DUMP_LLM=0 时不应有 dump 文件"
        )


def test_dump_disabled_when_env_explicit_one(monkeypatch):
    """HAGOKU_DUMP_LLM=1 时也应开启（非 0 即开）。"""
    monkeypatch.setenv("HAGOKU_DUMP_LLM", "1")

    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        llm_dump.set_run_dir(run_dir)

        llm_dump.dump_messages("test_stage", _make_messages(), model="test-model")

        dump_dir = run_dir / "llm_dumps"
        files = list(dump_dir.glob("*.json"))
        assert len(files) == 1, f"HAGOKU_DUMP_LLM=1 时应有 dump 文件"


# ── 契约 2：路径迁移 run_dir/llm_dumps/ ──────────────────────


def test_dump_path_under_run_dir(monkeypatch):
    """dump 写入 run_dir/llm_dumps/，与 events.jsonl 同目录。"""
    monkeypatch.delenv("HAGOKU_DUMP_LLM", raising=False)

    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        llm_dump.set_run_dir(run_dir)

        llm_dump.dump_messages("scout_infer", _make_messages(), model="qwen")

        dump_dir = run_dir / "llm_dumps"
        assert dump_dir.is_dir(), "run_dir/llm_dumps/ 应被创建"
        files = list(dump_dir.glob("*.json"))
        assert len(files) == 1

        payload = json.loads(files[0].read_text())
        assert payload["stage"] == "scout_infer"
        assert payload["model"] == "qwen"
        assert len(payload["messages"]) == 2
        assert payload["messages"][0]["role"] == "system"
        assert "你是数据分析师" in payload["messages"][0]["content"]


def test_dump_seq_increments_per_call(monkeypatch):
    """per-run _run_dump_seq 每次调用递增，同 run 不重复。"""
    monkeypatch.delenv("HAGOKU_DUMP_LLM", raising=False)

    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        llm_dump.set_run_dir(run_dir)

        llm_dump.dump_messages("stage_A", _make_messages(), model="m")
        llm_dump.dump_messages("stage_B", _make_messages(), model="m")

        dump_dir = run_dir / "llm_dumps"
        files = sorted(dump_dir.glob("*.json"))
        assert len(files) == 2

        p1 = json.loads(files[0].read_text())
        p2 = json.loads(files[1].read_text())
        assert p1["seq"] == 1
        assert p2["seq"] == 2


def test_set_run_dir_resets_seq(monkeypatch):
    """set_run_dir 重新调用时 seq 归零。"""
    monkeypatch.delenv("HAGOKU_DUMP_LLM", raising=False)

    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        llm_dump.set_run_dir(run_dir)
        llm_dump.dump_messages("s1", _make_messages(), model="m")
        dump_dir1 = run_dir / "llm_dumps"
        f1 = json.loads(next(dump_dir1.glob("*.json")).read_text())
        assert f1["seq"] == 1

    # 新 run
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        llm_dump.set_run_dir(run_dir)
        llm_dump.dump_messages("s1", _make_messages(), model="m")
        dump_dir2 = run_dir / "llm_dumps"
        f2 = json.loads(next(dump_dir2.glob("*.json")).read_text())
        assert f2["seq"] == 1, f"新 run 的 seq 应从 1 开始，实际 {f2['seq']}"


def test_dump_messages_with_extra(monkeypatch):
    """extra 字段写入 payload。"""
    monkeypatch.delenv("HAGOKU_DUMP_LLM", raising=False)

    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        llm_dump.set_run_dir(run_dir)

        llm_dump.dump_messages(
            "scout_resp",
            _make_messages(),
            model="m",
            extra={"query": "分析ROI", "response_tool_calls": [{"name": "submit"}]},
        )

        dump_dir = run_dir / "llm_dumps"
        payload = json.loads(next(dump_dir.glob("*.json")).read_text())
        assert payload["extra"]["query"] == "分析ROI"
        assert payload["extra"]["response_tool_calls"][0]["name"] == "submit"
