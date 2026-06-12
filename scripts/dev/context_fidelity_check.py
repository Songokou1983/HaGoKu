#!/usr/bin/env python3
"""context_fidelity_check.py — 上下文保真度自查工具

用途：在重构（如 4 合 1、通道改造）前后运行，对比 to_messages_for_llm 的输出，
确保重构没有悄悄压缩或截断上下文。

用法：
  # 重构前保存基线
  python scripts/dev/context_fidelity_check.py --save-baseline

  # 重构后对比（发现退化立即报告）
  python scripts/dev/context_fidelity_check.py --compare

  # 直接显示当前快照（不对比）
  python scripts/dev/context_fidelity_check.py --show

文件存放：
  ~/.hagoku/fidelity_baseline.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# 基线文件路径
_BASELINE_FILE = Path.home() / ".hagoku" / "fidelity_baseline.json"

# 标准测试场景（固定，不依赖真实数据）
_GOAL = "分析每个店铺的月度收入趋势"
_COLUMNS = [
    {"column_name": "StoreID", "suggested_role": "identifier", "used_in_analysis": True,
     "display_name": "店铺编号", "needs_user_input": False},
    {"column_name": "Period",  "suggested_role": "feature",    "used_in_analysis": True,
     "display_name": "时间周期", "needs_user_input": False},
    {"column_name": "Inc1",    "suggested_role": "target",     "used_in_analysis": True,
     "display_name": "店铺收入", "needs_user_input": False},
    {"column_name": "BU",      "suggested_role": "feature",    "used_in_analysis": False,
     "display_name": "事业部",  "needs_user_input": False},
]

# 5 个标准场景（从简单到复杂）
_SCENARIOS = {
    "scout_1round": {
        "desc": "Scout 1 轮纠正",
        "stage": "scout",
        "corrections": ["第一轮：Inc1 是净利润"],
    },
    "scout_3rounds": {
        "desc": "Scout 3 轮纠正",
        "stage": "scout",
        "corrections": [
            "第一轮：Inc1 是净利润不是总收入",
            "第二轮：BU 不参与分析",
            "第三轮：Period 是财务周",
        ],
    },
    "scout_5rounds": {
        "desc": "Scout 5 轮纠正（压力测试）",
        "stage": "scout",
        "corrections": [f"第{i}轮纠正：内容_{i * 1111}" for i in range(1, 6)],
    },
    "cross_stage_cleaner": {
        "desc": "跨阶段 scout→cleaner",
        "stage": "cleaner",
        "corrections": ["Scout 阶段纠正：Inc1 是净利润"],
        "pre_stage": "scout",
    },
    "cross_stage_analyst": {
        "desc": "跨阶段 scout+cleaner→analyst",
        "stage": "analyst",
        "corrections": ["Scout 纠正：Inc1 是净利润"],
        "pre_stage": "scout",
        "extra_corrections": [("cleaner", "Cleaner 纠正：Inc1 有 3% 缺失值，中位数填充")],
    },
}


def _build_scenario(scenario_name: str) -> dict[str, Any]:
    """构建指定场景的 ProjectContext 并运行 to_messages_for_llm，返回快照。"""
    from hagoku.context.project_context import ProjectContext

    s = _SCENARIOS[scenario_name]
    stage = s["stage"]
    corrections = s["corrections"]
    pre_stage = s.get("pre_stage")
    extra_corrections = s.get("extra_corrections", [])

    pc = ProjectContext(run_id=f"fidelity-{scenario_name}", analysis_goal=_GOAL)
    context: dict[str, Any] = {
        "query": _GOAL,
        "column_semantics": _COLUMNS,
        "target": "Inc1",
        "features": ["Period"],
        "_project_context": pc,
    }

    # 如果有前置阶段（cross-stage 测试）
    if pre_stage:
        for i, c in enumerate(corrections, 1):
            pc.add_user_feedback(pre_stage, i, raw_text=c)
            pc.add_agent_response(pre_stage, i, content=f"已处理_{pre_stage}_{i}",
                                  snapshot={"target": "Inc1", "features": ["Period"]})
        pc.add_stage_transition(stage)
        # 额外其他阶段
        for extra_stage, extra_text in extra_corrections:
            pc.add_user_feedback(extra_stage, 1, raw_text=extra_text)
            pc.add_agent_response(extra_stage, 1, content=f"已处理_{extra_stage}",
                                  snapshot={"target": "Inc1"})
            pc.add_stage_transition(stage)
        user_input = "开始分析"
    else:
        for i, c in enumerate(corrections, 1):
            pc.add_user_feedback(stage, i, raw_text=c)
            pc.add_agent_response(stage, i, content=f"已处理_{i}")
        user_input = "确认以上修改"

    msgs = pc.to_messages_for_llm(stage, context, user_input)

    # 收集快照
    snapshot: dict[str, Any] = {
        "scenario": scenario_name,
        "desc": s["desc"],
        "message_count": len(msgs),
        "roles": [m.get("role", "") for m in msgs],
        "role_counts": {
            "system": sum(1 for m in msgs if m.get("role") == "system"),
            "user": sum(1 for m in msgs if m.get("role") == "user"),
            "assistant": sum(1 for m in msgs if m.get("role") == "assistant"),
            "tool": sum(1 for m in msgs if m.get("role") == "tool"),
        },
        "system_len": sum(len(m.get("content", "")) for m in msgs if m.get("role") == "system"),
        "total_content_len": sum(
            len(m.get("content", "")) for m in msgs if isinstance(m.get("content"), str)
        ),
        "goal_in_messages": _GOAL in " ".join(
            m.get("content", "") for m in msgs if isinstance(m.get("content"), str)
        ),
        "corrections_preserved": {
            c: (c in " ".join(
                m.get("content", "") for m in msgs if isinstance(m.get("content"), str)
            ))
            for c in (corrections if not pre_stage else corrections + [e[1] for e in extra_corrections])
        },
    }
    return snapshot


def _run_all_scenarios() -> dict[str, dict]:
    results = {}
    for name in _SCENARIOS:
        try:
            results[name] = _build_scenario(name)
        except Exception as e:
            results[name] = {"scenario": name, "error": str(e)}
    return results


def _print_snapshot(snapshot: dict) -> None:
    print(f"\n  场景: {snapshot.get('desc', snapshot.get('scenario', ''))}")
    if "error" in snapshot:
        print(f"  ❌ 构建失败: {snapshot['error']}")
        return
    rc = snapshot.get("role_counts", {})
    print(f"  messages 条数: {snapshot['message_count']}  "
          f"(sys={rc.get('system',0)} user={rc.get('user',0)} "
          f"asst={rc.get('assistant',0)} tool={rc.get('tool',0)})")
    print(f"  system 长度: {snapshot['system_len']} 字符 | "
          f"总内容: {snapshot['total_content_len']} 字符")
    print(f"  分析目标在 messages 中: {'✅' if snapshot.get('goal_in_messages') else '❌'}")
    preserved = snapshot.get("corrections_preserved", {})
    if preserved:
        all_ok = all(preserved.values())
        print(f"  纠正保留情况: {'✅ 全部' if all_ok else '❌ 有丢失'}")
        if not all_ok:
            for text, ok in preserved.items():
                status = "  ✅" if ok else "  ❌"
                short = text[:50] + ("…" if len(text) > 50 else "")
                print(f"    {status} {short}")


def _compare_snapshots(baseline: dict[str, dict], current: dict[str, dict]) -> list[str]:
    """对比基线和当前快照，返回退化描述列表。空列表表示无退化。"""
    regressions = []

    for name in _SCENARIOS:
        b = baseline.get(name, {})
        c = current.get(name, {})

        if "error" in b:
            continue  # 基线本身构建失败，跳过对比
        if "error" in c:
            regressions.append(f"[{name}] 当前构建失败: {c['error']}")
            continue

        # 1. messages 条数不得减少
        b_count = b.get("message_count", 0)
        c_count = c.get("message_count", 0)
        if c_count < b_count:
            regressions.append(
                f"[{name}] messages 条数退化: {b_count} → {c_count} "
                f"（减少了 {b_count - c_count} 条）"
            )

        # 2. system 消息不得变短超过 20%
        b_sys = b.get("system_len", 0)
        c_sys = c.get("system_len", 0)
        if b_sys > 0 and c_sys < b_sys * 0.8:
            regressions.append(
                f"[{name}] system 消息缩短超过 20%: {b_sys} → {c_sys} 字符"
            )

        # 3. 纠正保留情况不得变差
        b_preserved = b.get("corrections_preserved", {})
        c_preserved = c.get("corrections_preserved", {})
        for text, was_ok in b_preserved.items():
            if was_ok and not c_preserved.get(text, True):
                regressions.append(
                    f"[{name}] 纠正原话在重构后消失: 「{text[:60]}」"
                )

        # 4. 分析目标不得从 messages 中消失
        if b.get("goal_in_messages") and not c.get("goal_in_messages"):
            regressions.append(f"[{name}] 分析目标从 messages 中消失")

    return regressions


def cmd_show() -> int:
    print("\n📋 当前上下文保真度快照\n" + "=" * 60)
    results = _run_all_scenarios()
    for name in _SCENARIOS:
        _print_snapshot(results.get(name, {"scenario": name, "error": "构建失败"}))
    print()
    return 0


def cmd_save_baseline() -> int:
    print("\n💾 正在保存上下文保真度基线...\n" + "=" * 60)
    results = _run_all_scenarios()

    errors = [name for name, r in results.items() if "error" in r]
    if errors:
        print(f"⚠️  以下场景构建失败，不保存基线: {errors}")
        print("请先修复这些场景，再保存基线。")
        return 1

    for name in _SCENARIOS:
        _print_snapshot(results[name])

    _BASELINE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _BASELINE_FILE.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"\n✅ 基线已保存到: {_BASELINE_FILE}")
    print("下次重构后运行 --compare 对比退化情况。")
    return 0


def cmd_compare() -> int:
    if not _BASELINE_FILE.exists():
        print(f"❌ 基线文件不存在: {_BASELINE_FILE}")
        print("请先运行 --save-baseline 保存基线。")
        return 1

    baseline = json.loads(_BASELINE_FILE.read_text())
    print("\n🔍 正在对比上下文保真度（当前 vs 基线）\n" + "=" * 60)

    current = _run_all_scenarios()

    print("\n[ 当前快照 ]")
    for name in _SCENARIOS:
        _print_snapshot(current.get(name, {"scenario": name, "error": "构建失败"}))

    regressions = _compare_snapshots(baseline, current)

    print("\n" + "=" * 60)
    if not regressions:
        print("✅ 无退化：上下文保真度与基线一致。")
        print("   重构前后的 messages 结构、长度、纠正保留情况均未变差。")
        return 0
    else:
        print(f"❌ 检测到 {len(regressions)} 处退化：\n")
        for r in regressions:
            print(f"  • {r}")
        print(
            "\n如何修复："
            "\n  1. 找到导致退化的代码变更（to_messages_for_llm / build_prompt / ProjectContext）"
            "\n  2. 恢复被压缩或截断的 messages 历史"
            "\n  3. 重新运行 --compare 直到无退化"
            "\n  注意：修复方式是恢复上下文，而不是调低基线。"
        )
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="上下文保真度自查工具 — 重构前后对比 to_messages_for_llm 输出"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--show", action="store_true", help="显示当前快照")
    group.add_argument("--save-baseline", action="store_true", help="保存当前快照为基线")
    group.add_argument("--compare", action="store_true", help="与基线对比，检测退化")

    args = parser.parse_args()

    if args.show:
        return cmd_show()
    elif args.save_baseline:
        return cmd_save_baseline()
    elif args.compare:
        return cmd_compare()
    return 0


if __name__ == "__main__":
    sys.exit(main())
