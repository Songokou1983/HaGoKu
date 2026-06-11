#!/usr/bin/env python3
"""health_check — 一键体检：dump 链路 / lesson 重复率 / prompt.md 状态 / memory 目录"""

import json, sys
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PROMPT_PATH = PROJECT_ROOT / "hagoku" / "agents" / "prompt.md"
DUMP_DIR = Path.home() / ".hagoku" / "llm_dumps"
LESSONS_PATH = PROJECT_ROOT / "hagoku" / "memory" / "lessons.jsonl"
MEMORY_DIRS = ["memory/methods/statistics", "memory/projects"]

def check_dump_integrity():
    files = list(DUMP_DIR.glob("*.json")) if DUMP_DIR.exists() else []
    reqs = set()
    resps = set()
    for f in files:
        name = f.name
        if "_response" in name:
            resps.add(name.replace("_response", ""))
        else:
            reqs.add(name)
    missing = reqs - resps
    print(f"Dump 链路: {len(files)} 文件, {len(missing)} 条缺少 _response")
    return len(missing) == 0

def check_lesson_dup():
    if not LESSONS_PATH.exists():
        print("Lesson: 无数据")
        return True
    lines = [l.strip() for l in LESSONS_PATH.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith('{"_schema"')]
    lessons = []
    for line in lines:
        try: lessons.append(json.loads(line))
        except: pass
    # simple similarity: exact scenario + lesson match
    seen = set()
    dups = 0
    for l in lessons:
        key = (l.get("scenario", ""), l.get("lesson", ""))
        if key in seen:
            dups += 1
        seen.add(key)
    dup_pct = round(dups / len(lessons) * 100, 1) if lessons else 0
    print(f"Lesson: {len(lessons)} 条, {dups} 条重复 ({dup_pct}%)")
    return dup_pct < 30

def check_prompt_status():
    if PROMPT_PATH.exists():
        mtime = datetime.fromtimestamp(PROMPT_PATH.stat().st_mtime)
        print(f"prompt.md: {PROMPT_PATH.stat().st_size} bytes, 最后修改 {mtime.isoformat()[:19]}")
        return True
    print("prompt.md: 缺失!")
    return False

def check_memory_dirs():
    ok = True
    for d in MEMORY_DIRS:
        p = PROJECT_ROOT / "hagoku" / d
        if p.is_dir():
            n = len(list(p.rglob("*")))
            print(f"  {d}: ✅ ({n} 条目)")
        else:
            print(f"  {d}: ❌ 缺失")
            ok = False
    return ok

if __name__ == "__main__":
    print("=== HaGoKu Health Check ===")
    d_ok = check_dump_integrity()
    l_ok = check_lesson_dup()
    p_ok = check_prompt_status()
    m_ok = check_memory_dirs()
    print()
    all_ok = d_ok and l_ok and p_ok and m_ok
    print("✅ 全部通过" if all_ok else "⚠️  存在警告")
