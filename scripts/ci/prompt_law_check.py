#!/usr/bin/env python3
"""pre-commit hook：prompt 文件修改时强制显示铁律 10/11 提醒并扫描违规。

触发条件：
  - hagoku/agents/*/prompt.md
  - hagoku/llm/prompts.py

两件事：
  1. 打印铁律 10/11 提醒
  2. 扫描被修改文件，检测是否引入了提示词层违规（替 LLM 预设业务结论）

违规 → exit(1) 拦截 commit
合规 → exit(0) 打印提醒后放行

使用（.pre-commit-config.yaml）：
  - id: prompt-law-check
    name: "铁律 10/11：prompt 修改前置检查（禁止预设业务结论）"
    entry: .venv/bin/python scripts/ci/prompt_law_check.py
    language: system
    files: ^hagoku/(agents/.*/prompt\\.md|llm/prompts\\.py)$
    pass_filenames: true
    verbose: true
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


# ── 铁律提醒 ──────────────────────────────────────────────────────────────────

_REMINDER = """
╔══════════════════════════════════════════════════════════════════╗
║        ⚠️  你正在修改 prompt 文件 — 铁律 10/11 适用             ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  铁律 10 — 提示词修改慎重                                        ║
║    禁止全文重写 prompt.md                                        ║
║    无 dump 对比不得删 system_prompt 片段                         ║
║    "觉得啰嗦"不是修改理由                                       ║
║    改 prompt 必须：开 dump → 定位 → 最小改 → dump 对比          ║
║                                                                  ║
║  铁律 11 — 提示词层禁止预设业务结论                              ║
║    合法：阶段说明、工具用法、输出格式、分析目标背景              ║
║    违规：强制角色分配、强制意图解读、禁止分析某字段、            ║
║          预设分析方法、用户输入直接映射到字段名                  ║
║                                                                  ║
║  判断方式：这句话是"告诉 LLM 背景"还是"替 LLM 做判断"？       ║
║  如果是后者，删掉它。LLM 看到完整上下文自己会判断。             ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
"""

# ── 违规模式（与 test_doctrine_compliance.py 守门 7 保持同步）────────────────

_VERDICT_PATTERNS: list[tuple[str, str]] = [
    (r"你必须(?:把|将).{0,20}判(?:断|定)为", "强制性字段角色分配"),
    (r"如果用户(?:说|提到|输入).{0,30}你(?:应该|必须)(?:理解成|判断为|视为)", "强制性意图解读"),
    (r"遇到.{0,20}(?:问题|情况|场景).{0,10}必须(?:用|使用|选择)", "预设分析方法"),
    (r"不(?:要|能|许|可以)(?:分析|关注|考虑).{0,20}(?:字段|列|变量)", "禁止性字段过滤"),
    (r"p\s*[值值]\s*[<＜]\s*0\.\d+\s*(?:就|则)(?:必须|应该|要)", "强制性数值阈值结论"),
    (r"用户说.{0,15}就等于.{0,15}字段", "用户输入直接映射"),
    (r"(?:只(?:分析|关注|保留)|排除|忽略)\s+[\u4e00-\u9fa5A-Za-z_]{2,}(?:\s*[、,，]\s*[\u4e00-\u9fa5A-Za-z_]{2,}){2,}",
     "强制字段集合"),
]

_WHITELIST = ["关注点", "##", "例如", "比如", "示例", "三要素", "tool_call"]


def _scan(path: Path) -> list[str]:
    violations: list[str] = []
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        return violations
    for lineno, line in enumerate(content.splitlines(), 1):
        stripped = line.strip()
        if not stripped or any(w in stripped for w in _WHITELIST):
            continue
        for pattern, desc in _VERDICT_PATTERNS:
            if re.search(pattern, stripped):
                violations.append(
                    f"  {path.name}:{lineno}  [{desc}]\n    → {stripped[:120]}"
                )
    return violations


def main(files: list[str]) -> int:
    print(_REMINDER)
    all_violations: list[str] = []
    checked: list[str] = []

    for f in files:
        path = Path(f)
        if not path.exists():
            continue
        checked.append(path.name)
        all_violations.extend(_scan(path))

    if checked:
        print(f"📋 已检查 prompt 文件：{', '.join(checked)}")

    if all_violations:
        print("\n🚫 检测到铁律 11 违规——提示词层预设了业务结论：\n")
        for v in all_violations:
            print(v)
        print(
            "\n如何修复："
            "\n  删掉结论式指令，改为向 LLM 提供背景信息，让它自行判断。"
            "\n  极少数确认合规的行，加入 tests/test_doctrine_compliance.py"
            "\n  → _PROMPT_VERDICT_KNOWN_OK 白名单并附注释说明原因。\n"
        )
        return 1

    print("✅ 未检测到提示词层违规，可提交。请再次确认：")
    print("   1. 改动是否经过 dump 对比（铁律 10）？")
    print("   2. 改动是否只是最小修改，而非全文重写？\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
