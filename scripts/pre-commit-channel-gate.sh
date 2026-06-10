#!/bin/bash
# HaGoKu 通道守门 — pre-commit hook
# 铁律 11 + Phase 0：禁止在 agents/ 和 manager/ 中直接构造 messages
# 所有 Agent 调 LLM 必须通过 hagoku/channel.py 的 build_messages()

set -e

# 只检查 Python 文件
CHANGED=$(git diff --cached --name-only --diff-filter=ACM | grep '^hagoku/\(agents\|manager\)/.*\.py$' || true)

if [ -z "$CHANGED" ]; then
    exit 0
fi

# 检查是否有直接构造 messages 的代码
if git diff --cached -- $CHANGED | grep -E '^\+\s*messages\s*=\s*\[.*"role"' > /dev/null 2>&1; then
    echo ""
    echo "❌ 通道守门拦截 — Phase 0"
    echo ""
    echo "   禁止在 hagoku/agents/ 或 hagoku/manager/ 中直接构造 messages。"
    echo "   所有 Agent 调 LLM 必须通过 hagoku/channel.py 的 build_messages()。"
    echo ""
    echo "   违规代码："
    git diff --cached -- $CHANGED | grep -nE '^\+\s*messages\s*=\s*\[.*"role"' | head -5
    echo ""
    echo "   修复："
    echo "   from hagoku.channel import build_messages"
    echo "   messages = build_messages(query=..., user_input=..., history=...)"
    echo ""
    exit 1
fi

# 检查是否有 messages.append 直接操作
if git diff --cached -- $CHANGED | grep -E '^\+\s*messages\.append\(' > /dev/null 2>&1; then
    echo ""
    echo "❌ 通道守门拦截 — Phase 0"
    echo ""
    echo "   禁止在 hagoku/agents/ 或 hagoku/manager/ 中直接操作 messages。"
    echo "   所有 messages 构造必须通过 build_messages()。"
    echo ""
    echo "   违规代码："
    git diff --cached -- $CHANGED | grep -nE '^\+\s*messages\.append\(' | head -5
    echo ""
    exit 1
fi

exit 0
