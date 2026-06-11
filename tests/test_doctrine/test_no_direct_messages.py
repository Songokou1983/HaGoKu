"""通道守门：hagoku/agents/ 和 hagoku/manager/ 不许直接构造 messages。

这是 pre-commit hook 的 CI 镜像，确保即使 hook 被绕过，CI 也会拦下。
"""

import subprocess
import sys
from pathlib import Path


def test_no_direct_messages_assignment_in_agents():
    """grep: messages = [{"role" 在 agents/ 和 manager/ 中必须 0 命中。"""
    root = Path(__file__).resolve().parent.parent.parent
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / "check_no_direct_messages.py")],
        capture_output=True, text=True, cwd=str(root),
    )
    violations = [l for l in result.stderr.splitlines() if l.strip()]
    assert result.returncode == 0, (
        f"直接构造 messages 违规:\n" + "\n".join(violations)
    )


def test_hook_returns_nonzero_on_violation(tmp_path):
    """验证 hook 真的会拦下违规代码。"""
    root = Path(__file__).resolve().parent.parent.parent
    bad_file = tmp_path / "bad.py"
    bad_file.write_text('messages = [{"role": "user", "content": "test"}]')
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / "check_no_direct_messages.py"), str(bad_file)],
        capture_output=True, text=True, cwd=str(root),
    )
    assert result.returncode != 0, "违规代码应被 hook 拦下"


def test_hook_exempts_channel_py(tmp_path):
    """channel.py 本身豁免。"""
    root = Path(__file__).resolve().parent.parent.parent
    ok_file = tmp_path / "channel.py"
    ok_file.write_text('messages = [{"role": "system", "content": "test"}]')
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / "check_no_direct_messages.py"), str(ok_file)],
        capture_output=True, text=True, cwd=str(root),
    )
    assert result.returncode == 0, "channel.py 应豁免"
