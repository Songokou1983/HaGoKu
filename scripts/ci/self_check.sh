#!/bin/bash
# HaGoKu 自检 —— 每次修改后必须跑通全部
set -e
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

echo "=== 1. 语法 ==="
python3 -c "import py_compile; py_compile.compile('$ROOT/hagoku/agents/agent.py', doraise=True)"
python3 -c "import py_compile; py_compile.compile('$ROOT/hagoku/manager/llm_dispatch/reply_handlers.py', doraise=True)"
python3 -c "import py_compile; py_compile.compile('$ROOT/hagoku/manager/orchestrator.py', doraise=True)"
echo "  ✅ 语法通过"

echo "=== 2. 铁律测试 ==="
cd "$ROOT" && python3 -m pytest tests/test_doctrine_compliance.py -q --noconftest
echo "  ✅ 铁律通过"

echo "=== 3. TypeScript ==="
cd "$ROOT/hagoku_web" && npx tsc --noEmit 2>&1
echo "  ✅ TS 通过"

echo "=== 4. 流式通道 ==="
grep -q "stream_chat_completion" "$ROOT/hagoku/agents/agent.py" && echo "  ✅ infer 流式" || { echo "  ❌ infer 流式缺失"; exit 1; }

echo "=== 5. 堵路检查 ==="
grep -q "if tc_list:" "$ROOT/hagoku/agents/agent.py" && echo "  ✅ 工具后续轮" || { echo "  ❌ 工具后续轮缺失"; exit 1; }
grep -q "not txt.strip()" "$ROOT/hagoku/agents/agent.py" && { echo "  ❌ txt.strip() 阻断续轮"; exit 1; } || echo "  ✅ 无 txt 阻断"
grep -q "只确认完成\|禁止沉默\|禁止回复" "$ROOT/hagoku/agents/prompt.md" && { echo "  ❌ 沉默指令"; exit 1; } || echo "  ✅ 无沉默指令"
grep -q 'phase_hint.*==.*"scout"' "$ROOT/hagoku/agents/agent.py" 2>/dev/null && { echo "  ❌ scout 工具锁"; exit 1; } || echo "  ✅ 无工具锁"

echo "=== 6. 消息去重 ==="
grep -q "false && assistant_pre_text" "$ROOT/hagoku_web/src/components/ToolExchangeTurn.tsx" && echo "  ✅ pre_text 已禁用" || { echo "  ❌ pre_text 重复"; exit 1; }

echo "=== ✅ 全部通过 ==="
