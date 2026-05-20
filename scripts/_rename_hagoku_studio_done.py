#!/usr/bin/env python3
"""
安全的批量替换：将对外展示文本中的 'HaGoKu Studio' 替换为 'HaGoKu Studio'。
规则：
  - 不替换代码标识符（HaGoKuConfig, HaGoKuDB, from hagoku 等）
  - 不替换包名/导入路径
  - 不替换 dist/ 构建产物
  - 已有 'HaGoKu Studio' 的不重复替换
"""

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# 排除的目录
EXCLUDE_DIRS = {
    ".git", "__pycache__", "node_modules", "dist",
    "UI_CHANGELOG_backup_*",  # 但这些已被 glob 排除
}

# 需要处理的文件扩展名
INCLUDE_EXTS = {".py", ".md", ".html", ".tsx", ".ts", ".toml", ".txt", ".json", ".yaml", ".yml", ".env"}

# 不需要修改的文件（具体路径，相对于 repo root）
EXCLUDE_FILES = {
    # 构建产物
    "hagoku_web/dist/assets/index-BeNlRjhM.js",
}

# 需要排除的目录路径
EXCLUDE_DIR_PATHS = {
    "hagoku_web/dist",
    ".git",
    "__pycache__",
    "node_modules",
}


def should_process_file(filepath: Path) -> bool:
    """判断文件是否应该被处理"""
    try:
        rel = filepath.resolve().relative_to(REPO_ROOT.resolve())
    except ValueError:
        return False

    rel_str = str(rel)

    # 排除构建产物
    if rel_str in EXCLUDE_FILES:
        return False

    # 排除目录
    for excl_dir in EXCLUDE_DIR_PATHS:
        if rel_str.startswith(excl_dir + "/") or rel_str == excl_dir:
            return False

    # 处理备份文件（这些是历史快照，不修改）
    if "UI_CHANGELOG_backup" in rel_str:
        return False

    # 检查扩展名
    ext = filepath.suffix
    if ext not in INCLUDE_EXTS:
        return False

    return True


def replace_in_content(content: str, filepath: Path) -> tuple[str, int]:
    """
    将对外展示文本中的 'HaGoKu Studio' 替换为 'HaGoKu Studio'。
    规则：
      - 不替换已经是 'HaGoKu Studio' 的（防重复）
      - 不替换标识符中的 HaGoKuConfig/HaGoKuDB 等
      - 不替换包名 hagoku（小写，不会匹配 HaGoKu Studio）
    """
    result_lines = []
    total_count = 0

    for line in content.split("\n"):
        pos = 0
        line_result = ""

        while pos < len(line):
            idx = line.find("HaGoKu Studio", pos)
            if idx == -1:
                line_result += line[pos:]
                break

            after_idx = idx + 6  # len("HaGoKu Studio")

            # 规则 1：后面紧跟大写字母 → 标识符（如 HaGoKuConfig），跳过
            if after_idx < len(line) and line[after_idx].isupper():
                line_result += line[pos:after_idx]
                pos = after_idx
                continue

            # 规则 2：已经是 "HaGoKu Studio"，跳过（防重复）
            if idx + 13 <= len(line) and line[idx:idx + 13] == "HaGoKu Studio":
                line_result += line[pos:idx + 13]
                pos = idx + 13
                continue

            # 规则 3：位于另一标识符内部（前一个字符是字母/数字/下划线），跳过
            if idx > 0 and (line[idx - 1].isalnum() or line[idx - 1] == "_"):
                line_result += line[pos:after_idx]
                pos = after_idx
                continue

            # 通过所有检查 → 替换
            line_result += line[pos:idx] + "HaGoKu Studio"
            total_count += 1
            pos = after_idx

        result_lines.append(line_result)

    return "\n".join(result_lines), total_count


def main():
    changed_files = []
    total_replacements = 0

    # 遍历所有文件
    for filepath in REPO_ROOT.rglob("*"):
        if not filepath.is_file():
            continue
        
        if not should_process_file(filepath):
            continue

        try:
            content = filepath.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError, IsADirectoryError):
            continue

        new_content, count = replace_in_content(content, filepath)
        
        if new_content != content:
            try:
                filepath.write_text(new_content, encoding="utf-8")
                changed_files.append(str(filepath.relative_to(REPO_ROOT)))
                total_replacements += count
                print(f"[OK] {filepath.relative_to(REPO_ROOT)} ({count} occurrences)")
            except Exception as e:
                print(f"[ERROR] {filepath.relative_to(REPO_ROOT)}: {e}", file=sys.stderr)

    print(f"\n--- Summary ---")
    print(f"Files changed: {len(changed_files)}")
    print(f"Total occurrences replaced: {total_replacements}")
    
    if changed_files:
        print("\nChanged files:")
        for f in changed_files:
            print(f"  {f}")


if __name__ == "__main__":
    main()