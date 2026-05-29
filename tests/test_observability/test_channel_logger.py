import json
import tempfile
from pathlib import Path
from hagoku.observability.channel_logger import ChannelLogger


def test_log_writes_jsonl_line():
    """log() 应写入一行 JSON 到 run.log"""
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        cl = ChannelLogger(run_dir)
        cl.log("scout", "llm_call", model="Qwen", prompt_len=1000)
        lines = (run_dir / "run.log").read_text().strip().split("\n")
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["agent"] == "scout"
        assert record["event"] == "llm_call"
        assert record["model"] == "Qwen"
        assert "ts" in record


def test_log_llm_writes_full_record():
    """log_llm() 应写入完整 LLM 记录到 llm.log"""
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        cl = ChannelLogger(run_dir)
        cl.log_llm("scout", "Qwen", "sys prompt", "user prompt",
                   [{"name": "submit", "arguments": {}}],
                   tokens=500, duration_ms=1200)
        lines = (run_dir / "llm.log").read_text().strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["agent"] == "scout"
        assert data["system_prompt"] == "sys prompt"
        assert data["tokens"] == 500


def test_trace_value_records_source():
    """trace_value() 应记录值来源"""
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        cl = ChannelLogger(run_dir)
        cl.trace_value("scout", "StoreID", "used_in_analysis", False, "llm")
        record = json.loads((run_dir / "run.log").read_text())
        assert record["event"] == "uia_set"
        assert record["column"] == "StoreID"
        assert record["value"] is False
        assert record["source"] == "llm"


def test_trace_value_unknown_field():
    """trace_value() 未映射字段用 {field}_set"""
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        cl = ChannelLogger(run_dir)
        cl.trace_value("scout", "StoreID", "custom_field", 42, "rule")
        record = json.loads((run_dir / "run.log").read_text())
        assert record["event"] == "custom_field_set"
        assert record["column"] == "StoreID"
        assert record["value"] == 42
        assert record["source"] == "rule"


def test_summary_writes_channel_health():
    """summary() 应写通道健康摘要"""
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        cl = ChannelLogger(run_dir)
        cl.summary(True, "6 true / 2 false", [])
        record = json.loads((run_dir / "run.log").read_text())
        assert record["event"] == "channel_summary"
        assert record["query_arrived"] is True


def test_log_llm_appends_not_overwrites():
    """两次 log_llm 调用应追加而非覆盖"""
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        cl = ChannelLogger(run_dir)
        cl.log_llm("scout", "Qwen", "s1", "u1", tokens=100)
        cl.log_llm("analyst", "GPT4", "s2", "u2", tokens=200)
        lines = (run_dir / "llm.log").read_text().strip().split("\n")
        assert len(lines) == 2
        r1 = json.loads(lines[0])
        assert r1["agent"] == "scout"
        assert r1["tokens"] == 100
        r2 = json.loads(lines[1])
        assert r2["agent"] == "analyst"
        assert r2["tokens"] == 200


def test_multiple_events_appended():
    """多次调用应追加而非覆盖"""
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        cl = ChannelLogger(run_dir)
        cl.log("a", "e1")
        cl.log("a", "e2")
        lines = (run_dir / "run.log").read_text().strip().split("\n")
        assert len(lines) == 2
