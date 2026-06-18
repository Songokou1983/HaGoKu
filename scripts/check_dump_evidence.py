#!/usr/bin/env python3
"""commit-msg hook: 强制要求改代码的 commit 包含诊断证据。

检查：
1. 如果修改了 hagoku/ 下的 Python 文件
2. commit message 必须包含 'dump:' 或 '证据:' 或 '【自检】'
3. 不满足 → 拒绝提交
"""
import sys, subprocess, re

commit_msg_file = sys.argv[1]
with open(commit_msg_file) as f:
    msg = f.read()

# 检查是否修改了代码文件
result = subprocess.run(
    ["git", "diff", "--cached", "--name-only"],
    capture_output=True, text=True
)
files = result.stdout.strip().split("\n")
code_changed = any(
    f.endswith(".py") and ("hagoku/" in f or "tests/" in f)
    for f in files if f
)

if not code_changed:
    sys.exit(0)  # 没有代码改动，放行

# 检查 commit message 是否有诊断证据
if re.search(r'dump:|证据:|【自检】', msg, re.IGNORECASE):
    sys.exit(0)

print("=" * 60)
print("❌ 铁律 0：commit 缺少诊断证据。")
print()
print("   修改了代码文件但 commit message 不含 dump 证据。")
print("   请在 commit message 中加入 dump/path/gap 信息。")
print()
print("   涉及文件：")
for f in files:
    if f and (f.endswith(".py") and ("hagoku/" in f or "tests/" in f)):
        print(f"     {f}")
print("=" * 60)
sys.exit(1)
