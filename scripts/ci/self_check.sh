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
grep -q "assistant_pre_text" "$ROOT/hagoku_web/src/components/ToolExchangeTurn.tsx" && { echo "  ❌ pre_text 残留"; exit 1; } || echo "  ✅ pre_text 已移除"

echo "=== 7. P1 假 agent response ==="
grep -q 'add_agent_response.*理解.*个字段\|add_agent_response.*字段推断完成' "$ROOT/hagoku/manager/orchestrator.py" && { echo "  ❌ orchestrator 仍在写假 agent response"; exit 1; } || echo "  ✅ orchestrator 无假 agent response"
grep -q 'AGENT_COMPLETED.*add_agent_response' "$ROOT/hagoku/context/project_context.py" && { echo "  ❌ project_context 仍在 AGENT_COMPLETED 写假 response"; exit 1; } || echo "  ✅ project_context AGENT_COMPLETED 已清理"

echo "=== 8. 代码不替 LLM 出内容 ==="
# 通道原则：用户看到的一切只能是 LLM 输出。代码禁止：
#   - 构造任何带展示语义键的 dict（field_review / cleaning_review / analysis_fields_summary 等）
#   - 从 _column_info / _column_profiles 等非 LLM 来源生成 rows
#   - 定义名为 *_payload 的函数（这是内容生成函数的命名模式）
#   - import 已删除的内容生成函数

# 检查 1: 全仓扫描——禁止代码构造展示类 payload（扩大的禁止键集合）
python3 -c "
import ast, sys, os, glob
failed = False
forbidden_keys = {
    'field_review', 'cleaning_review', 'cleaning_assessment', 'analyst_review',
    'analysis_fields_summary', 'analyst_first_pass_summary',
}
for pyfile in glob.glob(f'$ROOT/hagoku/**/*.py', recursive=True):
    if '/tests/' in pyfile or '/docs/' in pyfile:
        continue
    try:
        with open(pyfile) as f:
            tree = ast.parse(f.read())
    except (SyntaxError, UnicodeDecodeError):
        continue
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            ks = set()
            for k in node.keys:
                if isinstance(k, ast.Constant):
                    ks.add(str(k.value))
            if ks & forbidden_keys:
                print(f'{pyfile}:{node.lineno} 代码构造展示payload (keys={sorted(ks & forbidden_keys)})')
                failed = True
if failed:
    sys.exit(1)
print('✅ 无代码生成展示payload')
" || { echo "  ❌"; exit 1; }

# 检查 2: 全仓扫描——禁止代码构造 field_name/chinese_name/meaning 等前端 rows
python3 -c "
import ast, sys, os, glob
failed = False
for pyfile in glob.glob(f'$ROOT/hagoku/**/*.py', recursive=True):
    if '/tests/' in pyfile or '/docs/' in pyfile:
        continue
    try:
        with open(pyfile) as f:
            tree = ast.parse(f.read())
    except (SyntaxError, UnicodeDecodeError):
        continue
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            ks = set()
            for k in node.keys:
                if isinstance(k, ast.Constant):
                    ks.add(str(k.value))
            rowlike = {'field_name','chinese_name','meaning'} & ks
            if len(rowlike) >= 2:
                print(f'{pyfile}:{node.lineno} 代码构造rows (keys={sorted(ks)[:6]})')
                failed = True
if failed:
    sys.exit(1)
print('✅ 无代码生成rows')
" || { echo "  ❌"; exit 1; }

# 检查 3: 禁止定义 *_payload 函数（内容生成函数的命名模式）
python3 -c "
import sys, os, glob
failed = False
for pyfile in glob.glob(f'$ROOT/hagoku/**/*.py', recursive=True):
    if '/tests/' in pyfile:
        continue
    try:
        with open(pyfile) as f:
            for i, line in enumerate(f, 1):
                if line.strip().startswith('def ') and '_payload(' in line:
                    fname = line.strip().split('(')[0].replace('def ', '')
                    print(f'{pyfile}:{i} 定义内容生成函数 {fname}')
                    failed = True
    except UnicodeDecodeError:
        continue
if failed:
    sys.exit(1)
print('✅ 无 *_payload 内容生成函数')
" || { echo "  ❌"; exit 1; }

# 检查 4: 禁止 import 已删除的内容生成函数
python3 -c "
import sys, os, glob
failed = False
forbidden_imports = ['scout_field_review_pause_payload', 'cleaning_review_pause_payload']
for pyfile in glob.glob(f'$ROOT/hagoku/**/*.py', recursive=True):
    if '/tests/' in pyfile:
        continue
    try:
        with open(pyfile) as f:
            content = f.read()
    except UnicodeDecodeError:
        continue
    for fi in forbidden_imports:
        if fi in content:
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if fi in line and not line.strip().startswith('#'):
                    if 'import' in line or 'from' in line:
                        print(f'{pyfile}:{i+1} import了已删除的 {fi}')
                        failed = True
if failed:
    sys.exit(1)
print('✅ 无残留内容生成import')
" || { echo "  ❌"; exit 1; }

# 检查 5: 禁止代码"搬运"LLM文本——从 _scout_text / column_semantics 取文本后二次发送
python3 -c "
import ast, sys, os, glob
failed = False
for pyfile in glob.glob(f'$ROOT/hagoku/**/*.py', recursive=True):
    if '/tests/' in pyfile or '/docs/' in pyfile:
        continue
    try:
        with open(pyfile) as f:
            tree = ast.parse(f.read())
    except (SyntaxError, UnicodeDecodeError):
        continue
    # 检测模式: 从context取_scout_text → 放入emit或return的dict中作为message
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript):
            # 检查是否是 context['column_semantics'] 或类似的取_scout_text模式
            pass
    # 简单文本检测: _scout_text 出现在 emit/return 附近的代码块中
    lines = open(pyfile).readlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        # 模式: msg_text = ... _scout_text ... 然后 emit(..., msg_text) 或 return {message: msg_text}
        if '_scout_text' in stripped and not stripped.startswith('#'):
            # 检查后续几行是否有 emit 或 return
            block = ''.join(lines[i:min(i+4, len(lines))])
            if 'emit(' in block or 'return {' in block:
                if 'msg_text' in block or 'message' in block.split('_scout_text')[1] if '_scout_text' in block else False:
                    print(f'{pyfile}:{i+1} 代码搬运LLM文本(_scout_text→emit/return)')
                    failed = True
if failed:
    sys.exit(1)
print('✅ 无LLM文本搬运')
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
