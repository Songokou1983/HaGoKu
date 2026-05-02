"""HaGoKu 全局配置系统"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    """LLM 连接配置 — 只需三个参数"""

    model: str = "Qwen3.6-35B-A3B"  # 模型名称
    base_url: str = "http://localhost:8000/v1"  # API 地址
    api_key: str = "none"  # API Key（本地模型填 none）
    temperature: float = 0.6  # 生成温度
    max_tokens: int = 8192  # 最大 token 数


class ManagerModeConfig(BaseModel):
    """Manager 模式配置"""

    mode: str = "balanced"  # balanced(规则+AI) / rule(纯规则) / ai(AI优先)
    llm_plan_enabled: bool = True
    llm_plan_max_tokens: int = 1024
    llm_plan_timeout: int = 30
    cleaning_impact_warning: float = 0.3  # 是否使用 AI 生成计划


class OutputConfig(BaseModel):
    """输出配置"""

    base_dir: Path = Field(default_factory=lambda: Path.home() / ".hagokyu" / "projects")
    formats: list[str] = Field(default_factory=lambda: ["html"])


class UserModeConfig(BaseModel):
    """用户模式配置"""

    default_mode: str = "standard"  # quick / standard / expert


class AnalysisConfig(BaseModel):
    """统计分析配置"""

    random_state: int = 42
    p_value_threshold: float = 0.05
    shapiro_sample_limit: int = 5000
    overfitting_gap_threshold: float = 0.2


class CleaningConfig(BaseModel):
    """数据清洗配置"""

    isolation_forest_n_estimators: int = 100
    iterative_imputer_max_iter: int = 10
    random_state: int = 42


class HaGoKuConfig(BaseModel):
    """HaGoKu 全局配置"""

    llm: LLMConfig = Field(default_factory=LLMConfig)
    manager: ManagerModeConfig = Field(default_factory=ManagerModeConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    user_mode: UserModeConfig = Field(default_factory=UserModeConfig)
    analysis: AnalysisConfig = Field(default_factory=AnalysisConfig)
    cleaning: CleaningConfig = Field(default_factory=CleaningConfig)
    work_dir: Path = Field(default_factory=lambda: Path.home() / ".hagokyu")

    @classmethod
    def from_yaml(cls, path: Path) -> "HaGoKuConfig":
        """从 YAML 文件加载配置"""
        if not path.exists():
            return cls()
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        return cls(**data)

    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> "HaGoKuConfig":
        """加载配置：YAML + 环境变量覆盖"""
        if config_path is None:
            config_path = Path.home() / ".hagokyu" / "config.yaml"
        config = cls.from_yaml(config_path)
        config = cls._merge_env(config)
        return config

    @classmethod
    def _merge_env(cls, config: "HaGoKuConfig") -> "HaGoKuConfig":
        """环境变量覆盖已有配置"""
        if v := os.getenv("HAGOKYU_LLM_MODEL"):
            config.llm.model = v
        if v := os.getenv("HAGOKYU_LLM_BASE_URL"):
            config.llm.base_url = v
        if v := os.getenv("HAGOKYU_LLM_API_KEY"):
            config.llm.api_key = v
        if v := os.getenv("HAGOKYU_WORK_DIR"):
            config.work_dir = Path(v).expanduser()
        if v := os.getenv("HAGOKYU_MANAGER_MODE"):
            config.manager.mode = v
        return config

    def ensure_work_dir(self) -> None:
        """确保工作目录存在"""
        self.work_dir.mkdir(parents=True, exist_ok=True)
        (self.work_dir / "projects").mkdir(exist_ok=True)
