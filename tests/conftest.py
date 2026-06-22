"""测试 conftest — Phase D: 唯一 DataAnalystAgent，无需记忆隔离"""
from __future__ import annotations
import pytest
from hagoku.agents.agent import DataAnalystAgent  # noqa: F401


@pytest.fixture(autouse=True)
def _reset_dump_dir() -> None:
    """每个测试后重置 _run_dump_dir，防止测试 dump 污染生产 run 目录。"""
    yield
    from hagoku.observability.llm_dump import reset_run_dir
    reset_run_dir()
