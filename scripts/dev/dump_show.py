#!/usr/bin/env python3
"""dump_show — 渲染单条 LLM dump 给人看，高亮 role"""

import json, sys
from pathlib import Path
from datetime import datetime

DUMP_DIR = Path.home() / ".hagoku" / "llm_dumps"

def show(dump_path: Path):
    d = json.loads(dump_path.read_text(encoding="utf-8"))
    print(f"Stage: {d.get('stage','?')}  Model: {d.get('model','?')}  Time: {d.get('timestamp','?')[:19]}")
    print(f"Run: {d.get('run_id','?')}  Seq: {d.get('seq','?')}")
    print("=" * 60)
    for i, m in enumerate(d.get("messages", [])):
        role = m.get("role", "?").upper()
        prefix = {"SYSTEM": "📋", "USER": "👤", "ASSISTANT": "🤖", "TOOL": "🔧"}.get(role, "❓")
        content = str(m.get("content", ""))[:500]
        print(f"\n{prefix} [{i}] {role}")
        print(content)
        if "tool_calls" in m:
            for tc in m["tool_calls"]:
                fn = tc.get("function", {})
                print(f"   → {fn.get('name','?')}({fn.get('arguments','')[:200]})")
        if "tool_call_id" in m:
            print(f"   ↩ tool_call_id={m['tool_call_id'][:20]}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        files = sorted(DUMP_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)[:20]
        print(f"Recent {len(files)} dumps in {DUMP_DIR}:")
        for f in files:
            print(f"  {f.name}")
        print("\nUsage: dump_show.py <dump_file>")
        sys.exit(0)
    
    path = Path(sys.argv[1])
    if not path.exists():
        path = DUMP_DIR / sys.argv[1]
    if not path.exists():
        print(f"Not found: {sys.argv[1]}")
        sys.exit(1)
    show(path)
