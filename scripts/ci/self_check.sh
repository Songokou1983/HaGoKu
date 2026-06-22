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
grep -q "for _round in range" "$ROOT/hagoku/agents/agent.py" && echo "  ✅ 工具循环(while)" || { echo "  ❌ 工具循环缺失"; exit 1; }
grep -q "not txt.strip()" "$ROOT/hagoku/agents/agent.py" && { echo "  ❌ txt.strip() 阻断续轮"; exit 1; } || echo "  ✅ 无 txt 阻断"
grep -q "只确认完成\|禁止沉默\|禁止回复" "$ROOT/hagoku/agents/prompt.md" && { echo "  ❌ 沉默指令"; exit 1; } || echo "  ✅ 无沉默指令"
grep -q 'phase_hint.*==.*"scout"' "$ROOT/hagoku/agents/agent.py" 2>/dev/null && { echo "  ❌ scout 工具锁"; exit 1; } || echo "  ✅ 无工具锁"

echo "=== 6. 消息去重 ==="
grep -q "false && assistant_pre_text" "$ROOT/hagoku_web/src/components/ToolExchangeTurn.tsx" && echo "  ✅ pre_text 已禁用" || { echo "  ❌ pre_text 重复"; exit 1; }

echo "=== 7. P1 假 agent response ==="
grep -q 'add_agent_response.*理解.*个字段\|add_agent_response.*字段推断完成' "$ROOT/hagoku/manager/orchestrator.py" && { echo "  ❌ orchestrator 仍在写假 agent response"; exit 1; } || echo "  ✅ orchestrator 无假 agent response"
grep -q 'AGENT_COMPLETED.*add_agent_response' "$ROOT/hagoku/context/project_context.py" && { echo "  ❌ project_context 仍在 AGENT_COMPLETED 写假 response"; exit 1; } || echo "  ✅ project_context AGENT_COMPLETED 已清理"

echo "=== 8. 代码不替 LLM 出内容 ==="
# 通道原则：用户看到的一切只能是 LLM 输出。代码禁止生成 field_review/cleaning_assessment/analyst_review 等结构化展示数据。
# 检查 1: 禁止从 context 非 LLM 字段构造 rows（如 _column_info / _column_profiles）
python3 -c "
import ast, sys
failed = False
for subdir in ['manager/payloads', 'manager/llm_dispatch', 'agents']:
    import os, glob
    for pyfile in glob.glob(f'$ROOT/hagoku/{subdir}/**/*.py', recursive=True):
        with open(pyfile) as f:
            try:
                tree = ast.parse(f.read())
            except SyntaxError:
                continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                keys = [k.s if isinstance(k, ast.Constant) else '' for k in node.keys if isinstance(k, ast.Constant)]
                rowlike = {'field_name','chinese_name','meaning'} & set(keys)
                if len(rowlike) >= 2:
                    print(f'{pyfile}:{node.lineno} 代码构造 field_review rows (keys={sorted(keys)[:6]})')
                    failed = True
if failed:
    sys.exit(1)
print('✅ 无代码生成结构化展示数据')
" || { echo "  ❌"; exit 1; }

# 检查 2: 禁止从非 LLM 输出源构造 field_review/cleaning_assessment payload
python3 -c "
import ast, sys
forbidden_keys = {'field_review', 'cleaning_assessment', 'analyst_review', 'fieldReview'}
for subdir in ['manager/payloads', 'manager/llm_dispatch', 'agents']:
    import os, glob
    for pyfile in glob.glob(f'$ROOT/hagoku/{subdir}/**/*.py', recursive=True):
        with open(pyfile) as f:
            try:
                tree = ast.parse(f.read())
            except SyntaxError:
                continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                keys = {k.s if isinstance(k, ast.Constant) else k.value if isinstance(k, ast.Constant) else '' for k in node.keys if hasattr(k, 's') or hasattr(k, 'value')}
                keys = {str(k) for k in keys if k}
                if keys & forbidden_keys:
                    src = getattr(node, 'lineno', '?')
                    print(f'{pyfile}:{src} 代码构造禁止的展示 payload (keys={sorted(keys & forbidden_keys)})')
                    sys.exit(1)
print('✅ 无代码构造 field_review/cleaning_assessment payload')
" || { echo "  ❌"; exit 1; }

echo "=== 9. 刹车 G — prompt/tool描述 不用禁止堵 ==="
# 检测 prompt.md 和 tool descriptions 中是否出现「禁止/不要/不准」来堵行为
VIOLATIONS=$(grep -c '禁止' "$ROOT/hagoku/agents/prompt.md" 2>/dev/null || echo 0)
# prompt.md 已有的「禁止说'请用工具'」是合法工具使用规则，不是mismatch堵
TOOL_VIOLATIONS=$(grep -rn '禁止.*调用\|不要.*调用\|不要.*使用\|不准.*输出\|不准.*使用' "$ROOT/hagoku/tools/agent_tool_defs.py" 2>/dev/null | wc -l)
if [ "$TOOL_VIOLATIONS" -gt 0 ]; then
    echo "  ❌ agent_tool_defs.py 存在刹车G违规"
    exit 1
fi
echo "  ✅ 通过"

echo "=== 10. commit-msg hook 已安装 ==="
if [ -x "$ROOT/.git/hooks/commit-msg" ]; then
    echo "  ✅ dump证据检查hook就位"
else
    echo "  ❌ 缺失: cp scripts/check_dump_evidence.py .git/hooks/commit-msg"
    exit 1
fi

echo "=== ✅ 全部通过 ==="
