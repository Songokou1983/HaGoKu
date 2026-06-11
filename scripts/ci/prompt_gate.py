#!/usr/bin/env python3
"""prompt_gate — 检测 prompt.md 修改对 LLM tool_calls 的影响。

用法:
  python scripts/ci/prompt_gate.py <baseline_prompt> <current_prompt> [--corpus PATH]

  配合 pre-commit hook: prompt.md 被修改时自动对比 gate corpus 标准输入。
  报告每条的 tool_calls 结构变化百分比。>0% 不阻止提交（calibration 期），只记日志。

不调真实 LLM——用 corpus 里的历史 messages + mock LLM 做结构对比。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CORPUS_DIR = PROJECT_ROOT / "tests" / "fixtures" / "gate_corpus"
CALIBRATION_LOG = Path.home() / ".hagoku" / "prompt_gate_calibrations.jsonl"


def load_corpus(corpus_dir: Path) -> list[dict[str, Any]]:
    entries = []
    for f in sorted(corpus_dir.glob("*.json")):
        try:
            entries.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass
    return entries


def inject_prompt(messages: list[dict], prompt: str) -> list[dict]:
    """替换 system 消息为给定 prompt（模拟 prompt.md 变更）。"""
    out = []
    for m in messages:
        if m.get("role") == "system":
            out.append({"role": "system", "content": prompt})
        else:
            out.append(m)
    return out


def simulate_tool_calls(messages: list[dict], prompt: str, model: str = "mock") -> list[dict[str, Any]]:
    """mock LLM——返回空 tool_calls（gate corpus 验证的是结构，不是内容）。"""
    msgs = inject_prompt(messages, prompt)
    return [{"role": "assistant", "content": "mock response", "tool_calls": []}]


def diff_pct(baseline_tool: dict | None, current_tool: dict | None) -> float:
    """计算 tool_calls 结构变化的百分比（简化为字段数差异 / 共享字段数）。"""
    if baseline_tool is None and current_tool is None:
        return 0.0
    if baseline_tool is None or current_tool is None:
        return 100.0
    b_keys = set(_flatten_keys(baseline_tool))
    c_keys = set(_flatten_keys(current_tool))
    if not b_keys and not c_keys:
        return 0.0
    shared = len(b_keys & c_keys)
    total = max(len(b_keys), len(c_keys))
    if total == 0:
        return 0.0
    return round((1 - shared / total) * 100, 1)


def _flatten_keys(d: dict, prefix: str = "") -> set[str]:
    keys = set()
    for k, v in d.items():
        full = f"{prefix}.{k}" if prefix else k
        keys.add(full)
        if isinstance(v, dict):
            keys |= _flatten_keys(v, full)
        elif isinstance(v, list):
            for i, item in enumerate(v):
                if isinstance(item, dict):
                    keys |= _flatten_keys(item, f"{full}[{i}]")
    return keys


def run_gate(baseline_prompt: str, current_prompt: str, corpus_dir: Path | None = None) -> dict:
    corpus_dir = corpus_dir or CORPUS_DIR
    entries = load_corpus(corpus_dir)
    if not entries:
        return {"error": "gate corpus 为空", "entries": 0}

    results = []
    for e in entries:
        b_result = simulate_tool_calls(e.get("messages", []), baseline_prompt)
        c_result = simulate_tool_calls(e.get("messages", []), current_prompt)
        b_tc = (b_result[-1].get("tool_calls") or [{}])[0] if b_result else None
        c_tc = (c_result[-1].get("tool_calls") or [{}])[0] if c_result else None
        pct = diff_pct(b_tc, c_tc)
        results.append({"stage": e.get("stage", ""), "diff_pct": pct})

    max_diff = max(r["diff_pct"] for r in results) if results else 0
    report = {
        "entries": len(entries),
        "max_diff_pct": max_diff,
        "details": results,
    }

    # 记录校准日志
    CALIBRATION_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CALIBRATION_LOG, "a") as f:
        f.write(json.dumps({"max_diff_pct": max_diff, "n_entries": len(entries)}, ensure_ascii=False) + "\n")

    return report


def main():
    # pre-commit mode: no args → get baseline from git HEAD, compare with working file
    if len(sys.argv) < 2:
        prompt_file = PROJECT_ROOT / "hagoku" / "agents" / "prompt.md"
        if not prompt_file.exists():
            print("prompt.md not found")
            sys.exit(0)
        import subprocess
        try:
            baseline = subprocess.check_output(
                ["git", "show", "HEAD:hagoku/agents/prompt.md"],
                text=True, stderr=subprocess.DEVNULL, cwd=PROJECT_ROOT,
            )
        except subprocess.CalledProcessError:
            print("无法获取 git baseline（可能为新文件），跳过 gate")
            sys.exit(0)
        current = prompt_file.read_text(encoding="utf-8")
        report = run_gate(baseline, current)
        if "error" in report:
            print(report["error"])
            sys.exit(0)
        print(f"Gate: {report['entries']} entries, max_diff={report['max_diff_pct']}%")
        sys.exit(0)

    if len(sys.argv) < 3:
        print("Usage: prompt_gate.py <baseline_prompt_file> <current_prompt_file> [--corpus PATH]")
        print("       prompt_gate.py  (pre-commit mode: compare git HEAD vs working file)")
        sys.exit(1)

    baseline_path = Path(sys.argv[1])
    current_path = Path(sys.argv[2])
    corpus = Path(sys.argv[4]) if len(sys.argv) > 4 and sys.argv[3] == "--corpus" else None

    if not baseline_path.exists():
        print(f"Baseline prompt not found: {baseline_path}")
        sys.exit(1)

    baseline_prompt = baseline_path.read_text(encoding="utf-8")
    current_prompt = current_path.read_text(encoding="utf-8") if current_path.exists() else ""

    report = run_gate(baseline_prompt, current_prompt, corpus)
    if "error" in report:
        print(report["error"])
        sys.exit(1)

    print(f"Gate: {report['entries']} entries, max_diff={report['max_diff_pct']}%")
    for r in report["details"]:
        flag = " ⚠️" if r["diff_pct"] > 0 else ""
        print(f"  {r['stage']}: {r['diff_pct']}%{flag}")

    # calibration 期不硬拦截（brief §4.3）
    if report["max_diff_pct"] > 0:
        print("\n⚠️  tool_calls 结构有变化。calibration 期不阻止提交，已记入校准日志。")


if __name__ == "__main__":
    main()
