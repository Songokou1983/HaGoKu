#!/usr/bin/env python3
"""Pre-commit hook: 禁止在 hagoku/agents/ 和 hagoku/manager/ 直接构造 messages。

规则：
1. 禁止 `messages = [{"role": ...}]` 或 `_messages = [{"role": ...}]`
2. 禁止 `messages.append({"role": ...})`
3. 例外：hagoku/channel.py 本身；test 文件 tests/
4. 例外：dump 用的 messages（行内含 `dump_messages(` 调用——AST 分析）

退出码：违规 → 1；干净 → 0
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

WATCHED_DIRS = ["hagoku/agents", "hagoku/manager"]
EXEMPT_FILES = {"hagoku/channel.py"}

# 正则模式
DIRECT_ASSIGN = re.compile(r'\bmessages\s*=\s*\[\s*\{\s*["\x27]role["\x27]')
APPEND_ROLE = re.compile(r'\bmessages\s*\.\s*append\s*\(\s*\{')


def _is_exempt(filepath: str) -> bool:
    """检查文件是否豁免。"""
    basename = Path(filepath).name
    if basename == "channel.py":
        return True
    for exc in EXEMPT_FILES:
        if filepath.endswith(exc):
            return True
    if "/tests/" in filepath or filepath.startswith("tests/"):
        return True
    return False


def scan(files: list[str]) -> list[str]:
    """扫描指定文件列表，返回违规行列表。"""
    violations: list[str] = []
    for fpath in files:
        if not fpath.endswith(".py"):
            continue
        if _is_exempt(fpath):
            continue
        try:
            content = Path(fpath).read_text(encoding="utf-8")
        except Exception:
            continue

        for lineno, line in enumerate(content.splitlines(), 1):
            stripped = line.strip()
            # 跳过注释和 dump 调用
            if stripped.startswith("#"):
                continue
            if "dump_messages(" in line:
                continue

            if DIRECT_ASSIGN.search(line):
                violations.append(f"{fpath}:{lineno}  messages = [{{...}}] 直接构造（应通过 build_messages / to_messages_for_llm）")
            elif APPEND_ROLE.search(line):
                violations.append(f"{fpath}:{lineno}  messages.append({{...}}) 直接追加（应通过 ProjectContext）")

    return violations


if __name__ == "__main__":
    target_files = sys.argv[1:] if len(sys.argv) > 1 else []
    if not target_files:
        # 默认扫描监控目录
        for d in WATCHED_DIRS:
            p = Path(d)
            if p.exists():
                target_files.extend(str(f) for f in p.rglob("*.py"))

    violations = scan(target_files)
    if violations:
        print("\n".join(violations), file=sys.stderr)
        sys.exit(1)
    sys.exit(0)
