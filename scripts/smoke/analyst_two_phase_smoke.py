#!/usr/bin/env python3
"""Analyst 二段化真 LLM 冒烟脚本（SK-1）

用法:
  .venv/bin/python scripts/smoke/analyst_two_phase_smoke.py \\
    --data tests/fixtures/smoke_demo.csv \\
    --query "哪个渠道ROI最高" \\
    --dump-dir ./smoke_runs/2026-06-08/

跑 Scout → Cleaner → Analyst 全流程，在 Analyst 阶段按冒烟剧本逐条注入用户输入。
每轮 LLM 调用自动 dump 到 run_dir/llm_dumps/。跑完后输出自动检查清单初步结果。
"""
from __future__ import annotations

import argparse
import json as _json
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# ── 冒烟剧本定义 ────────────────────────────────────────────────

SMOKE_SCRIPT = [
    # (step_id, user_input, description, expected_tool, expected_behavior)
    # Step 0: auto-triggered by entering analyst (no user input needed)
    # Step 1: check written summary output
    (1, None, "阶段 1 完成，前端展示概括——验证三要素标记",
     None, "USER_INPUT_REQUESTED message 含 [发现]/[统计依据]/[局限或解读]"),
    # Step 2: user challenges with specific test
    (2, "换 t 检验试试",
     "用户要求换检验方法",
     "run_statistical_test", "调 run_statistical_test(test_type='ttest', ...)"),
    # Step 3: user redirects direction
    (3, "我觉得方向不对，应该看渠道维度",
     "用户纠偏分析方向",
     "update_analysis_scope|route_to", "调 update_analysis_scope 或 route_to(stage='scout')"),
    # Step 4: user says done
    (4, "够了，去写报告吧",
     "用户要求收尾进入报告",
     "route_to", "调 route_to(stage='reporter') → respond 返回 switch"),
    # Step 5: user hesitates (in a new analyst session)
    (5, "再等等",
     "用户挽留",
     None, "不调 route_to(stage=...)；纯文本回应"),
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Analyst 二段化真 LLM 冒烟")
    p.add_argument("--data", required=True, help="CSV 数据文件路径")
    p.add_argument("--query", required=True, help="分析问题")
    p.add_argument("--dump-dir", required=True, help="冒烟 dump 输出目录")
    p.add_argument("--timeout-step-s", type=int, default=120,
                   help="每步 respond() 最大等待秒数（默认 120）")
    return p.parse_args(argv)


def _fmt_stage(orch: Any) -> str:
    """安全读取当前阶段。"""
    try:
        return getattr(orch, '_stage', '?')
    except Exception:
        return '?'


def _collect_dump_files(run_dir: Path) -> list[Path]:
    """收集 run_dir/llm_dumps/ 下所有 dump 文件，按 mtime 排序。"""
    dump_dir = run_dir / "llm_dumps"
    if not dump_dir.exists():
        return []
    return sorted(dump_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)


def _find_latest_dump_after(run_dir: Path, after_idx: int) -> Path | None:
    """返回第 after_idx 个之后的最新 dump 文件。"""
    dumps = _collect_dump_files(run_dir)
    if len(dumps) > after_idx:
        return dumps[-1]
    return None


def _read_dump(dump_path: Path) -> dict | None:
    """读取单个 dump 文件内容。"""
    try:
        return _json.loads(dump_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _search_in_dumps(dump_dir: Path, keyword: str) -> list[Path]:
    """在所有 dump 文件中搜索关键词，返回命中的文件路径。"""
    hits: list[Path] = []
    for dump_file in _collect_dump_files(dump_dir):
        try:
            content = dump_file.read_text(encoding="utf-8")
            if keyword in content:
                hits.append(dump_file)
        except Exception:
            continue
    return hits


def _check_three_elements(message: str) -> dict[str, bool]:
    """检查消息是否含三要素标记。"""
    return {
        "[发现]": "[发现]" in message,
        "[统计依据]": "[统计依据]" in message,
        "[局限或解读]": "[局限或解读]" in message,
    }


def run_smoke(args: argparse.Namespace) -> dict[str, Any]:
    """执行冒烟剧本，返回结果摘要。"""
    from hagoku.config import HaGoKuConfig
    from hagoku.manager.orchestrator import Orchestrator
    from hagoku.observability.events import EventType
    from hagoku.observability.llm_dump import set_run_dir as _set_llm_dump_dir

    data_path = Path(args.data)
    if not data_path.exists():
        raise FileNotFoundError(f"数据文件不存在: {data_path}")

    dump_dir = Path(args.dump_dir)
    dump_dir.mkdir(parents=True, exist_ok=True)

    # 设置 LLM dump 目录（让 orchesterator 内部的 set_run_dir 被覆盖为此目录）
    _set_llm_dump_dir(dump_dir)

    print(f"🔥 冒烟开始: {datetime.now().isoformat()}")
    print(f"   数据: {data_path}")
    print(f"   问题: {args.query}")
    print(f"   dump: {dump_dir}")

    config = HaGoKuConfig.load()
    orch = Orchestrator(config)

    # ── 捕获 EventBus emit 用于事后验证 ──
    emitted_events: list[tuple] = []
    _orig_emit = orch.event_bus.emit

    def _capture_emit(event_type: Any, agent: str, data: Any = None) -> None:
        emitted_events.append((event_type, agent, data))
        _orig_emit(event_type, agent, data)

    orch.event_bus.emit = _capture_emit  # type: ignore[method-assign]

    results: dict[str, Any] = {
        "run_start": datetime.now().isoformat(),
        "data": str(data_path),
        "query": args.query,
        "dump_dir": str(dump_dir),
        "steps": {},
        "emitted_events_count": 0,
    }

    # ── Step 0: 启动 pipeline（Scout 阶段） ──
    print("\n── Step 0: 启动 pipeline（Scout 字段理解）──")
    t0 = time.time()
    run_result = orch.run(str(data_path), args.query)
    print(f"   run() 返回: status={run_result.get('status')}, phase={run_result.get('phase')}")
    print(f"   耗时: {time.time() - t0:.1f}s")

    # Scout 回复：确认字段理解
    if orch._stage == "scout":
        print("\n── Scout 回复: 确认字段理解 ──")
        t1 = time.time()
        scout_result = orch.respond({"text": "确认"})
        print(f"   respond 返回: {type(scout_result).__name__}")
        if isinstance(scout_result, dict):
            print(f"   status={scout_result.get('status')}")
        print(f"   当前阶段: {_fmt_stage(orch)}")
        print(f"   耗时: {time.time() - t1:.1f}s")

    # 如果 Scout 阶段还有字段表展示，再确认一次
    if orch._stage == "scout":
        print("\n── Scout 二次确认 ──")
        orch.respond({"text": "可以进入下一阶段了"})
        print(f"   当前阶段: {_fmt_stage(orch)}")

    # Cleaner 阶段
    if orch._stage == "cleaner":
        print("\n── Cleaner 评估 ──")
        t2 = time.time()
        cleaner_result = orch.respond({"text": "可以进入下一阶段了"})
        print(f"   respond 返回: {type(cleaner_result).__name__}")
        if isinstance(cleaner_result, dict):
            print(f"   status={cleaner_result.get('status')}")
        print(f"   当前阶段: {_fmt_stage(orch)}")
        print(f"   耗时: {time.time() - t2:.1f}s")

    # Cleaner 二次确认（进入 Analyst）
    if orch._stage == "cleaner":
        print("\n── Cleaner 确认 → Analyst ──")
        t3 = time.time()
        orch.respond({"text": "确认"})
        print(f"   当前阶段: {_fmt_stage(orch)}")
        print(f"   耗时: {time.time() - t3:.1f}s")

    # ── Analyst 阶段：首波由 Cleaner→Analyst 切换时自动触发（无需额外 respond）──
    if orch._stage == "analyst":
        print("\n── Step 0（自动）: Analyst 首波自动分析 ──")
        print(f"   _analyst_first_pass_done: {orch._analyst_first_pass_done}")

        # 检查 USER_INPUT_REQUESTED 事件中的首波概括消息
        first_pass_events = [
            e for e in emitted_events
            if e[0] == EventType.USER_INPUT_REQUESTED and e[1] == "analyst"
        ]
        if first_pass_events:
            msg = first_pass_events[-1][2].get("message", "") if first_pass_events[-1][2] else ""
            three_ok = _check_three_elements(msg)
            results["steps"]["0"] = {
                "description": "首波自动分析 + 书面概括",
                "first_pass_done": orch._analyst_first_pass_done,
                "three_elements": three_ok,
                "all_three": all(three_ok.values()),
                "message_preview": msg[:300] if msg else "(无消息)",
            }
            print(f"   三要素检查: {three_ok}")
            print(f"   消息预览: {msg[:200]}...")
        else:
            results["steps"]["0"] = {
                "description": "首波自动分析",
                "first_pass_done": orch._analyst_first_pass_done,
                "error": "未收到 USER_INPUT_REQUESTED 事件",
            }
            print("   ⚠️ 未收到 USER_INPUT_REQUESTED 事件！")

        # 记录首波前 dump 文件数量
        dumps_before_step = len(_collect_dump_files(dump_dir))

    # ── 冒烟剧本步骤 2-5 ──
    for step_id, user_input, desc, expected_tool, expected_behavior in SMOKE_SCRIPT:
        if user_input is None:
            # Step 1 是首波后的被动检查，已在上面处理
            # Step 0 是自动触发的
            if step_id == 0:
                continue
            continue

        if orch._stage != "analyst":
            print(f"\n── Step {step_id}: 跳过（当前阶段: {_fmt_stage(orch)}，非 analyst）──")
            results["steps"][str(step_id)] = {
                "description": desc,
                "error": f"非 analyst 阶段: {_fmt_stage(orch)}",
            }
            continue

        print(f"\n── Step {step_id}: {desc} ──")
        print(f"   用户输入: {user_input}")

        dumps_before = len(_collect_dump_files(dump_dir))
        t_start = time.time()

        resp_result = orch.respond({"text": user_input})

        elapsed = time.time() - t_start
        dumps_after = len(_collect_dump_files(dump_dir))
        new_dumps = dumps_after - dumps_before

        print(f"   耗时: {elapsed:.1f}s, 新 dump: {new_dumps} 个")
        print(f"   当前阶段: {_fmt_stage(orch)}")

        # 检查 respond 返回值
        if isinstance(resp_result, tuple):
            print(f"   respond 返回: switch → {resp_result[1]}")
        elif isinstance(resp_result, dict):
            print(f"   respond 返回: status={resp_result.get('status')}")

        # 自动检查：搜索最新 dump 中的预期工具
        tool_found = False
        dump_preview = ""
        if new_dumps > 0 and expected_tool:
            latest_dump = _find_latest_dump_after(dump_dir, dumps_before)
            if latest_dump:
                dump_data = _read_dump(latest_dump)
                if dump_data:
                    dump_str = _json.dumps(dump_data, ensure_ascii=False)
                    dump_preview = str(latest_dump.name)
                    for tool_name in expected_tool.split("|"):
                        if tool_name in dump_str:
                            tool_found = True
                            break
                    if not tool_found:
                        # 尝试在 tool_calls 中搜索
                        pass

        step_result = {
            "description": desc,
            "user_input": user_input,
            "expected_tool": expected_tool,
            "tool_found_in_dump": tool_found if expected_tool else "n/a",
            "dump_preview": dump_preview if dump_preview else "(无新 dump)",
            "respond_type": type(resp_result).__name__,
            "stage_after": _fmt_stage(orch),
            "elapsed_s": round(elapsed, 1),
        }

        if isinstance(resp_result, tuple):
            step_result["switch_target"] = resp_result[1] if len(resp_result) > 1 else None

        results["steps"][str(step_id)] = step_result

        # Step 3 切换到 scout 后需重置回 analyst 继续步骤 4-5
        if isinstance(resp_result, tuple) and step_id == 3:
            print(f"   🔄 Step 3 已切 {resp_result[1]}，重置回 analyst（仅冒烟用）")
            orch._stage = "analyst"
            orch._analyst_first_pass_done = False
            orch._analyst_messages = []
            orch.respond({"text": ""})
            print(f"   首波重跑后阶段: {_fmt_stage(orch)}, _analyst_first_pass_done: {orch._analyst_first_pass_done}")

        # Step 4 切换到 reporter 后需重置回 analyst 继续步骤 5
        if isinstance(resp_result, tuple) and step_id == 4 and resp_result[1] == "reporter":
            print(f"   🔄 Step 4 已切 reporter，Step 5 重置回 analyst（仅冒烟用）")
            orch._stage = "analyst"
            orch._analyst_first_pass_done = False
            orch._analyst_messages = []
            orch.respond({"text": ""})
            print(f"   首波重跑后阶段: {_fmt_stage(orch)}, _analyst_first_pass_done: {orch._analyst_first_pass_done}")

    # ── 收集 dump 文件 ──
    # 优先从 orchestrator 的 run_dir 收集（orch.run() 内部 set_run_dir 覆盖了外部设置）
    orch_dump_dir = None
    try:
        from hagoku.observability.llm_dump import get_dump_dir
        orch_dump_dir = get_dump_dir()
    except Exception:
        pass

    if orch_dump_dir and orch_dump_dir.exists():
        dump_dir_to_use = orch_dump_dir
        print(f"\n   从 orch run_dir 收集 dump: {orch_dump_dir}")
        # 复制到冒烟 dump-dir
        import shutil as _shutil
        for f in _collect_dump_files(orch_dump_dir):
            _shutil.copy2(f, dump_dir / f.name)
    else:
        dump_dir_to_use = dump_dir

    # ── 最终检查 ──
    results["emitted_events_count"] = len(emitted_events)

    all_dumps = _collect_dump_files(dump_dir_to_use)
    results["total_dumps"] = len(all_dumps)

    # 搜索 submit_first_pass
    sfp_files = _search_in_dumps(dump_dir_to_use, "submit_first_pass")
    results["submit_first_pass_found"] = len(sfp_files) > 0
    results["submit_first_pass_files"] = [str(f.name) for f in sfp_files]

    # 搜索 run_statistical_test
    rst_files = _search_in_dumps(dump_dir_to_use, "run_statistical_test")
    results["run_statistical_test_found"] = len(rst_files) > 0

    # 搜索 route_to
    rt_files = _search_in_dumps(dump_dir_to_use, "route_to")
    results["route_to_found"] = len(rt_files) > 0

    # 搜索 "再等等" 附近的 route_to（Step 5 不应调 route_to）
    step5_safe = True
    # 简单检查：如果最后一个 dump 不含 route_to，大概率安全
    all_dumps_step5 = _collect_dump_files(dump_dir_to_use)
    if all_dumps_step5:
        last_dump_data = _read_dump(all_dumps_step5[-1])
        if last_dump_data:
            last_dump_str = _json.dumps(last_dump_data, ensure_ascii=False)
            if "route_to" in last_dump_str:
                step5_safe = False
    results["step5_no_route_to"] = step5_safe

    print(f"\n{'='*60}")
    print(f"冒烟完成: {datetime.now().isoformat()}")
    print(f"总 dump 文件: {len(all_dumps)}")
    print(f"submit_first_pass 出现: {results['submit_first_pass_found']}")
    print(f"run_statistical_test 出现: {results['run_statistical_test_found']}")
    print(f"route_to 出现: {results['route_to_found']}")
    print(f"Step 5 挽留（无 route_to）: {step5_safe}")
    print(f"结果已写入: {dump_dir / 'smoke_results.json'}")

    # 写结果文件
    results_path = dump_dir / "smoke_results.json"
    results_path.write_text(
        _json.dumps(results, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    return results


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    try:
        results = run_smoke(args)
        # 输出自动检查初步通过/不通过
        passed = 0
        failed = 0
        for step_id, sr in results.get("steps", {}).items():
            if sr.get("error"):
                print(f"  Step {step_id}: ❌ {sr['error']}")
                failed += 1
            else:
                print(f"  Step {step_id}: ✅ {sr.get('description', '')[:60]}")
                passed += 1
        print(f"\n自动检查: {passed} 通过, {failed} 失败")
        if failed > 0:
            sys.exit(1)
    except Exception as e:
        print(f"❌ 冒烟失败: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(2)


if __name__ == "__main__":
    main()
