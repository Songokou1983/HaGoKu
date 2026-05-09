"""测试配置系统"""

import os
from pathlib import Path

import pytest

from hagokyu.config import HaGoKuConfig, LLMConfig, ManagerModeConfig, OutputConfig, UserModeConfig


class TestLLMConfig:
    def test_defaults(self):
        config = LLMConfig()
        assert config.base_url == "http://localhost:8000/v1"
        assert config.model == "Qwen3.6-35B-A3B"
        assert config.temperature == 0.6

    def test_custom(self):
        config = LLMConfig(base_url="http://custom:9000/v1", model="custom-model")
        assert config.base_url == "http://custom:9000/v1"
        assert config.model == "custom-model"


class TestManagerModeConfig:
    def test_defaults(self):
        config = ManagerModeConfig()
        assert config.cleaning_impact_warning == 0.3


class TestHaGoKuConfig:
    def test_defaults(self):
        config = HaGoKuConfig()
        assert config.llm.model == "Qwen3.6-35B-A3B"
        assert config.manager.cleaning_impact_warning == 0.3
        assert config.user_mode.default_mode == "standard"

    def test_from_yaml(self, tmp_path):
        yaml_path = tmp_path / "config.yaml"
        yaml_path.write_text("""
llm:
  model: test-model
  temperature: 0.5
manager:
  cleaning_impact_warning: 0.5
""")
        config = HaGoKuConfig.from_yaml(yaml_path)
        assert config.llm.model == "test-model"
        assert config.llm.temperature == 0.5
        assert config.manager.cleaning_impact_warning == 0.5

    def test_from_yaml_nonexistent(self):
        config = HaGoKuConfig.from_yaml(Path("/nonexistent/config.yaml"))
        assert config.llm.model == "Qwen3.6-35B-A3B"  # 默认值

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("HAGOKYU_LLM_BASE_URL", "http://env:7000/v1")
        monkeypatch.setenv("HAGOKYU_LLM_MODEL", "env-model")

        config = HaGoKuConfig()
        config = HaGoKuConfig._merge_env(config)

        assert config.llm.base_url == "http://env:7000/v1"
        assert config.llm.model == "env-model"

    def test_ensure_work_dir(self, tmp_path, monkeypatch):
        work_dir = tmp_path / "test_hagokyu"
        config = HaGoKuConfig(work_dir=work_dir)
        config.ensure_work_dir()
        assert work_dir.exists()
        assert (work_dir / "projects").exists()
