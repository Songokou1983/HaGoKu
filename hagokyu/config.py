"""HaGoKu 全局配置系统"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# 加载 ~/.hagokyu/.env 中的环境变量
_load_env_path = Path.home() / ".hagokyu" / ".env"
if _load_env_path.exists():
    load_dotenv(_load_env_path)


class LLMConfig(BaseModel):
    """LLM 连接配置 — 只需三个参数"""

    model: str = "Qwen3.6-35B-A3B"  # 模型名称
    base_url: str = "http://localhost:8000/v1"  # API 地址
    api_key: str = "none"  # API Key（本地模型填 none）

    def __repr__(self) -> str:
        """调试输出时 api_key 只显示前8位"""
        return (
            f"LLMConfig(model={self.model!r}, "
            f"base_url={self.base_url!r}, "
            f"api_key={self.api_key[:8] + '***' if self.api_key else '(none)'!r}, "
            f"temperature={self.temperature}, max_tokens={self.max_tokens})"
        )
    temperature: float = 0.6  # 生成温度
    max_tokens: int = 8192  # 最大 token 数


class ManagerModeConfig(BaseModel):
    """Manager 模式配置"""

    mode: str = "balanced"  # balanced(规则+AI) / rule(纯规则) / ai(AI优先)
    llm_plan_enabled: bool = True
    llm_plan_max_tokens: int = 1024
    llm_plan_timeout: int = 30
    cleaning_impact_warning: float = 0.3  # 清洗影响率阈值（超过此比例触发警告）


class OutputConfig(BaseModel):
    """输出配置"""

    project_dir: Path = Field(default_factory=lambda: Path.home() / ".hagokyu" / "projects")
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
        """从 YAML 文件加载配置（失败则返回默认值）"""
        if not path.exists():
            return cls()
        try:
            with open(path) as f:
                data = yaml.safe_load(f) or {}
            return cls(**data)
        except Exception:
            # YAML 格式错误 → 使用默认配置，不阻断
            return cls()

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
        if v := os.getenv("HAGOKYU_PROJECT_DIR"):
            config.output.project_dir = Path(v).expanduser()
        if v := os.getenv("HAGOKYU_MANAGER_MODE"):
            config.manager.mode = v
        return config

    def ensure_work_dir(self) -> None:
        """确保工作目录存在（失败则使用临时目录，不阻断）"""
        try:
            self.work_dir.mkdir(parents=True, exist_ok=True)
            (self.work_dir / "projects").mkdir(exist_ok=True)
        except PermissionError:
            # 权限不足 → 回退到临时目录
            import tempfile
            self.work_dir = Path(tempfile.gettempdir()) / ".hagokyu"
            self.work_dir.mkdir(exist_ok=True)
            (self.work_dir / "projects").mkdir(exist_ok=True)

    def save(self, config_path: Path | None = None) -> None:
        """保存配置到 YAML 文件"""
        if config_path is None:
            config_path = Path.home() / ".hagokyu" / "config.yaml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        # 排除 work_dir（这些由系统决定，不写入用户配置）
        data = self.model_dump(mode="json", exclude={"work_dir"})
        with open(config_path, "w") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)

    def sensitive_fields(self) -> dict[str, str]:
        """返回敏感字段的脱敏值（用于日志/调试输出）"""
        return {
            "api_key": f"{self.llm.api_key[:8]}***" if self.llm.api_key else "(未设置)",
        }

    def __repr__(self) -> str:
        """调试输出时自动脱敏 api_key"""
        safe = self.sensitive_fields()
        return (
            f"HaGoKuConfig(model={self.llm.model!r}, "
            f"base_url={self.llm.base_url!r}, "
            f"api_key={safe['api_key']!r}, "
            f"mode={self.manager.mode})"
        )

