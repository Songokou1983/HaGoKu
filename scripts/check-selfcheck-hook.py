#!/usr/bin/env python3
"""Git commit-msg hook：拦截缺少自检答案的 LLM 相关改动。

规则：
  如果本次 commit 涉及 LLM prompt/工具 schema/Agent 输出的改动
  （变更文件中含 agent.py / orchestrator.py / types.py / prompts/ / prompt.md），
  则 commit message 必须包含「【自检】」标记。

用法：
  cp scripts/check-selfcheck-hook.sh .git/hooks/commit-msg
  chmod +x .git/hooks/commit-msg
"""

import re
import subprocess
import sys

# 检测 LLM 交互相关文件
LLM_SENSITIVE_GLOBS = [
    r"agent\.py$",
    r"orchestrator\.py$",
    r"types\.py$",
    r"prompts?/",
    r"prompt\.md$",
    r"llm/",
    r"guardrails/",
]


def get_changed_files() -> list[str]:
    """获取本次 commit 涉及的文件列表"""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        capture_output=True, text=True,
    )
    return result.stdout.strip().split("\n") if result.stdout.strip() else []


def is_llm_sensitive(path: str) -> bool:
    for pattern in LLM_SENSITIVE_GLOBS:
        if re.search(pattern, path):
            return True
    return False


def main():
    commit_msg_file = sys.argv[1]
    with open(commit_msg_file) as f:
        msg = f.read()

    # 检查 commit message 是否含自检标记
    has_selfcheck = "【自检】" in msg

    files = get_changed_files()
    llm_files = [f for f in files if is_llm_sensitive(f)]

    if llm_files and not has_selfcheck:
        print("=" * 60)
        print("❌ 铁律 0：本次改动涉及 LLM 交互代码，但 commit message 缺少自检答案。")
        print()
        print("  涉及文件：")
        for f in llm_files:
            print(f"    {f}")
        print()
        print("  请在 commit message 中加入：")
        print("    【自检】判断：LLM 拿到分析目标和数据后能自己判断 [X] 吗？")
        print("    答案：能 → 不写规则，只送数据 / 不能 → 代码的活")
        print()
        print("  用 git commit --amend 或 git commit -e 修改提交信息。")
        print("=" * 60)
        sys.exit(1)

    if llm_files and has_selfcheck:
        print(f"✅ 铁律 0 自检通过（{len(llm_files)} 个 LLM 敏感文件）")


if __name__ == "__main__":
    main()
