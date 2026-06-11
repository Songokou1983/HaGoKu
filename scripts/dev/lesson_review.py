#!/usr/bin/env python3
"""lesson_review — 列最近 N 条 lesson 表格，不调 LLM"""

import json, sys
from pathlib import Path
from datetime import datetime

LESSONS_PATH = Path(__file__).resolve().parent.parent.parent / "hagoku" / "memory" / "lessons.jsonl"

def review(limit: int = 20):
    if not LESSONS_PATH.exists():
        print("lessons.jsonl 不存在（无数据）")
        return
    lines = [l.strip() for l in LESSONS_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    lessons = []
    for line in lines:
        if line.startswith('{"_schema"'):
            continue
        try:
            lessons.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    lessons.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    recent = lessons[:limit]
    if not recent:
        print("0 条 lesson")
        return
    print(f"最近 {len(recent)} 条 lesson（共 {len(lessons)} 条）：")
    print(f"{'ID':<10} {'时间':<22} {'项目':<15} {'场景':<20} {'置信度':<8}")
    print("-" * 80)
    for l in recent:
        ts = l.get("timestamp", "")[:19]
        pid = l.get("project_id", "")[:14]
        scenario = l.get("scenario", "")[:19]
        conf = l.get("confidence", "?")
        lid = l.get("id", "")[:8]
        print(f"{lid:<10} {ts:<22} {pid:<15} {scenario:<20} {conf:<8}")

if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    review(limit)
