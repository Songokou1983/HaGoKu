"""守门测试：STATE_REGISTRY.md 与源代码一致性。

不解析 AST、不解析 Markdown。只做数量校验。
"""
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ANALYZE_DIR = ROOT / "hagoku_web" / "src" / "panels" / "AnalyzePanel"


def count_usestate_in_file(path: Path) -> int:
    """grep '= useState' 匹配实际 hook 调用（排除 import 行），返回匹配行数。"""
    result = subprocess.run(
        ["grep", "-c", r"= useState", str(path)],
        capture_output=True, text=True,
    )
    return int(result.stdout.strip() or 0)


def test_analyze_panel_usestate_count():
    """AnalyzePanel.tsx 的 useState 数量应与注册表一致。"""
    fpath = ANALYZE_DIR.parent / "AnalyzePanel.tsx"
    actual = count_usestate_in_file(fpath)
    # 注册表记录 9 个本地 useState
    expected = 9
    assert actual == expected, (
        f"AnalyzePanel.tsx 有 {actual} 个 useState，"
        f"注册表记录 {expected} 个。如有增删请同步更新 STATE_REGISTRY.md"
    )


def test_use_analyze_session_usestate_count():
    """useAnalyzeSession.ts 的 useState 数量应与注册表一致。"""
    actual = count_usestate_in_file(
        ANALYZE_DIR / "hooks" / "useAnalyzeSession.ts"
    )
    # 注册表记录 14 个 sess state
    expected = 14
    assert actual == expected, (
        f"useAnalyzeSession.ts 有 {actual} 个 useState，"
        f"注册表记录 {expected} 个。如有增删请同步更新 STATE_REGISTRY.md"
    )


def test_no_missing_handlers():
    """注册表中不应有 '缺失' 标记的 handler。"""
    registry = ANALYZE_DIR / "STATE_REGISTRY.md"
    content = registry.read_text()
    lines_with_missing = [
        line for line in content.split("\n")
        if "缺失" in line and "handler" in line.lower()
    ]
    assert len(lines_with_missing) == 0, (
        f"STATE_REGISTRY.md 中有 {len(lines_with_missing)} 行标记为 '缺失'：\n"
        + "\n".join(lines_with_missing[:5])
    )


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
