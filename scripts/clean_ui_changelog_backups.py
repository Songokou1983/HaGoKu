#!/usr/bin/env python3
"""
列出或删除仓库内的 UI_CHANGELOG_backup_* 本地快照（见 CLAUDE.md、.gitignore）。

默认只打印（dry-run）；真正删除须加 --apply。
可选 --older-than DAYS：仅处理修改时间早于「今天 − DAYS」的文件。
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def skip_dir_parts(parts: tuple[str, ...]) -> bool:
    skip = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache", "dist", "build"}
    return any(x in skip for x in parts)


def iter_backup_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        try:
            rel = p.relative_to(root)
        except ValueError:
            continue
        if skip_dir_parts(rel.parts):
            continue
        if p.name.startswith("UI_CHANGELOG_backup_"):
            out.append(p)
    return sorted(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="执行删除（默认仅列出）",
    )
    parser.add_argument(
        "--older-than",
        type=int,
        metavar="DAYS",
        default=0,
        help="仅处理最后修改时间早于「当前 UTC 日期 − DAYS」天的文件；0 表示不限制",
    )
    args = parser.parse_args()
    root = repo_root()
    if not root.joinpath("pyproject.toml").is_file():
        print("error: pyproject.toml not found next to scripts/ — wrong cwd?", file=sys.stderr)
        return 2

    files = iter_backup_files(root)
    cutoff: datetime | None = None
    if args.older_than > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=args.older_than)

    selected: list[Path] = []
    for p in files:
        if cutoff is not None:
            m = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
            if m >= cutoff:
                continue
        selected.append(p)

    if not selected:
        print("No UI_CHANGELOG_backup_* files" + (" matching age filter" if cutoff else "") + ".")
        return 0

    total_bytes = sum(p.stat().st_size for p in selected)
    print(f"Found {len(selected)} file(s), ~{total_bytes / 1024:.1f} KiB total")
    for p in selected:
        print(f"  {p.relative_to(root)}")

    if not args.apply:
        print("\nDry-run only. Pass --apply to delete, or --older-than N to narrow by mtime.")
        return 0

    removed = 0
    for p in selected:
        try:
            p.unlink()
            removed += 1
        except OSError as e:
            print(f"warn: could not remove {p}: {e}", file=sys.stderr)
    print(f"\nRemoved {removed}/{len(selected)} file(s).")
    return 0 if removed == len(selected) else 1


if __name__ == "__main__":
    raise SystemExit(main())
