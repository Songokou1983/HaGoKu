"""SK-1: 冒烟工具结构验证 — 仅断言可 import + 参数解析正确，不验真 LLM"""
import sys
from pathlib import Path


def test_smoke_script_importable():
    """验证冒烟脚本可 import。"""
    # 将 scripts/smoke 加入 sys.path
    smoke_dir = Path(__file__).parent.parent.parent / "scripts" / "smoke"
    sys.path.insert(0, str(smoke_dir))
    try:
        import analyst_two_phase_smoke as smoke_mod
        assert smoke_mod is not None
    finally:
        sys.path.pop(0)


def test_smoke_script_parse_args():
    """验证参数解析正确。"""
    smoke_dir = Path(__file__).parent.parent.parent / "scripts" / "smoke"
    sys.path.insert(0, str(smoke_dir))
    try:
        from analyst_two_phase_smoke import parse_args
        args = parse_args([
            "--data", "/tmp/test.csv",
            "--query", "测试问题",
            "--dump-dir", "/tmp/smoke_test/",
        ])
        assert args.data == "/tmp/test.csv"
        assert args.query == "测试问题"
        assert args.dump_dir == "/tmp/smoke_test/"
    finally:
        sys.path.pop(0)


def test_smoke_script_has_smoke_script_constant():
    """验证冒烟剧本 SMOKE_SCRIPT 为列表且每项含 step_id + description。"""
    smoke_dir = Path(__file__).parent.parent.parent / "scripts" / "smoke"
    sys.path.insert(0, str(smoke_dir))
    try:
        from analyst_two_phase_smoke import SMOKE_SCRIPT
        assert isinstance(SMOKE_SCRIPT, list), "SMOKE_SCRIPT 应为列表"
        assert len(SMOKE_SCRIPT) >= 5, f"至少 5 步，实际 {len(SMOKE_SCRIPT)}"
        for step in SMOKE_SCRIPT:
            assert len(step) >= 4, f"每步至少 4 元素，实际 {len(step)}: {step}"
            step_id, user_input, desc, expected_tool = step[:4]
            assert isinstance(step_id, int), f"step_id 应为 int: {step_id}"
            assert isinstance(desc, str), f"desc 应为 str: {desc}"
    finally:
        sys.path.pop(0)


def test_smoke_script_has_run_smoke_function():
    """验证 run_smoke 函数存在且有正确签名。"""
    import inspect
    smoke_dir = Path(__file__).parent.parent.parent / "scripts" / "smoke"
    sys.path.insert(0, str(smoke_dir))
    try:
        from analyst_two_phase_smoke import run_smoke
        sig = inspect.signature(run_smoke)
        params = list(sig.parameters.keys())
        assert "args" in params, f"run_smoke 应有 args 参数，实际: {params}"
    finally:
        sys.path.pop(0)
