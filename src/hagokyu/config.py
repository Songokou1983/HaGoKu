"""HaGoKu 全局配置系统"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    """LLM 连接配置"""

    base_url: str = "http://localhost:8000/v1"
    api_key: str = "none"
    model: str = "Qwen3.6-35B-A3B"  # 实际模型：llama-server 上的 Qwen3.6-35B GGUF
    temperature: float = 0.6
    max_tokens: int = 8192
    top_p: float = 0.95
    top_k: int = 20


class ManagerModeConfig(BaseModel):
    """Manager 模式配置"""

    # 预设模式
    mode: str = "local_weak"  # local_weak / local_strong / cloud / pure_rule
    rule_weight: float = 0.9
    llm_weight: float = 0.1

    # LLM 计划生成设置
    llm_plan_enabled: bool = True  # 总开关，本地 LLM 不可用时关闭
    llm_plan_timeout: float = 30.0  # LLM 计划生成超时（秒）
    llm_plan_max_tokens: int = 1024  # 计划生成 max_tokens（计划短，不需要 8192）

    # 质量阈值
    r_squared_warning: float = 0.3  # R² 低于此值预警
    p_value_significance: float = 0.05
    cleaning_impact_warning: float = 0.10  # 清洗影响超过 10% 预警


class OutputConfig(BaseModel):
    """输出配置"""

    base_dir: Path = Field(default_factory=lambda: Path.home() / ".hagokyu" / "projects")
    naming: str = "{project}/report_{date}"
    date_format: str = "%Y%m%d"
    formats: list[str] = Field(default_factory=lambda: ["html"])
    auto_archive: bool = True
    keep_latest_n: int = 10


class UserModeConfig(BaseModel):
    """用户模式配置"""

    # quick / standard / expert
    default_mode: str = "standard"
    # 语义推断置信度阈值：低于此值时需要用户确认
    semantic_confirmation_threshold: float = 0.6
    # 快速模式最大交互点数
    quick_max_interactions: int = 0
    # 普通模式最大交互点数
    standard_max_interactions: int = 5
    # 资深模式最大交互点数（0 = 无限）
    expert_max_interactions: int = 0


class AnalysisConfig(BaseModel):
    """统计分析配置"""

    random_state: int = 42
    shapiro_sample_limit: int = 5000
    p_value_threshold: float = 0.05
    default_k_folds: int = 5
    overfitting_gap_threshold: float = 0.15


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
    def from_env(cls) -> "HaGoKuConfig":
        """从环境变量覆盖配置"""
        config = cls()
        # LLM
        if v := os.getenv("HAGOKYU_LLM_BASE_URL"):
            config.llm.base_url = v
        if v := os.getenv("HAGOKYU_LLM_API_KEY"):
            config.llm.api_key = v
        if v := os.getenv("HAGOKYU_LLM_MODEL"):
            config.llm.model = v
        # Work dir
        if v := os.getenv("HAGOKYU_WORK_DIR"):
            config.work_dir = Path(v).expanduser()
        # Manager mode
        if v := os.getenv("HAGOKYU_MANAGER_MODE"):
            config.manager.mode = v
        return config

    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> "HaGoKuConfig":
        """加载配置：YAML + 环境变量覆盖"""
        # 1. 默认值
        # 2. YAML 文件覆盖
        if config_path is None:
            config_path = Path.home() / ".hagokyu" / "config.yaml"
        config = cls.from_yaml(config_path)
        # 3. 环境变量覆盖
        config = cls._merge_env(config)
        return config

    @classmethod
    def _merge_env(cls, config: "HaGoKuConfig") -> "HaGoKuConfig":
        """环境变量覆盖已有配置"""
        if v := os.getenv("HAGOKYU_LLM_BASE_URL"):
            config.llm.base_url = v
        if v := os.getenv("HAGOKYU_LLM_API_KEY"):
            config.llm.api_key = v
        if v := os.getenv("HAGOKYU_LLM_MODEL"):
            config.llm.model = v
        if v := os.getenv("HAGOKYU_WORK_DIR"):
            config.work_dir = Path(v).expanduser()
        if v := os.getenv("HAGOKYU_MANAGER_MODE"):
            config.manager.mode = v
            # 自动设置权重
            mode_weights = {
                "local_weak": (0.9, 0.1),
                "local_strong": (0.5, 0.5),
                "cloud": (0.1, 0.9),
                "pure_rule": (1.0, 0.0),
            }
            if v in mode_weights:
                config.manager.rule_weight, config.manager.llm_weight = mode_weights[v]
        return config

    def ensure_work_dir(self) -> None:
        """确保工作目录存在"""
        self.work_dir.mkdir(parents=True, exist_ok=True)
        (self.work_dir / "projects").mkdir(exist_ok=True)


# Manager 模式预设权重
MANAGER_MODE_PRESETS = {
    "local_weak": {"rule_weight": 0.9, "llm_weight": 0.1},
    "local_strong": {"rule_weight": 0.5, "llm_weight": 0.5},
    "cloud": {"rule_weight": 0.1, "llm_weight": 0.9},
    "pure_rule": {"rule_weight": 1.0, "llm_weight": 0.0},
}
