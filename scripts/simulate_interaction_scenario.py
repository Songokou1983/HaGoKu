#!/usr/bin/env python3
"""加载并校验「互动场景」夹具，打印一页纸剧本（便于评审 / 对需求）。

示例：

    python3 scripts/simulate_interaction_scenario.py --validate-all
    python3 scripts/simulate_interaction_scenario.py --script full_web_pause_flow
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 仓库根目录
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from hagoku.devtools.interaction_scenarios import (  # noqa: E402
    default_fixtures_dir,
    format_scenario_script,
    iter_scenario_files,
    load_scenario,
    validate_scenario_document,
)


def main() -> int:
    p = argparse.ArgumentParser(description="Validate / print HaGoKu interaction scenario fixtures.")
    p.add_argument("--validate-all", action="store_true", help="Validate every JSON in tests/fixtures/interaction_scenarios/")
    p.add_argument("--script", metavar="ID", help="Print human script for scenario id (json stem or id field)")
    p.add_argument("--json", metavar="PATH", help="Validate a single JSON file path")
    args = p.parse_args()

    if args.json:
        path = Path(args.json)
        doc = load_scenario(path)
        errs = validate_scenario_document(doc, source=str(path))
        if errs:
            for e in errs:
                print(e, file=sys.stderr)
            return 1
        print("OK", path)
        return 0

    if args.validate_all:
        files = iter_scenario_files()
        if not files:
            print("No scenario files under", default_fixtures_dir(), file=sys.stderr)
            return 1
        bad = 0
        for path in files:
            doc = load_scenario(path)
            errs = validate_scenario_document(doc, source=str(path))
            if errs:
                bad += 1
                print(f"FAIL {path}", file=sys.stderr)
                for e in errs:
                    print(f"  {e}", file=sys.stderr)
            else:
                print("OK", path)
        return 1 if bad else 0

    if args.script:
        target = args.script
        for path in iter_scenario_files():
            doc = load_scenario(path)
            if path.stem == target or doc.get("id") == target:
                print(format_scenario_script(doc), end="")
                gaps = 0
                for st in doc.get("steps", []):
                    if isinstance(st, dict) and isinstance(st.get("gap"), str) and st["gap"].strip():
                        gaps += 1
                print(f"\n# 标注了 {gaps} 个「缺口 / 目标态」（gap 字段），供迭代 LLM 互动时对照。\n")
                return 0
        print("Scenario not found:", target, file=sys.stderr)
        return 1

    p.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
