"""HaGoKu Studio 全局配置系统"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# 加载 ~/.hagoku/.env 中的环境变量
_load_env_path = Path.home() / ".hagoku" / ".env"
if _load_env_path.exists():
    load_dotenv(_load_env_path, override=True)


class LLMConfig(BaseModel):
    """LLM 连接配置 — 只需三个参数"""

    model: str = ""  # 模型名称 — 用户通过设置功能配置，禁止写死默认值（铁律 9）
    base_url: str = ""  # OpenAI 兼容 LLM — 用户通过设置功能配置，禁止写死默认值（铁律 9）
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
    stream_enabled: bool = True  # 流式输出开关（CO-21）；false 时回退 batch emit 整段 message

class MetaLLMConfig(BaseModel):
    """HaGoKu Doctor 独立 LLM 配置。全部留空则复用 pipeline LLM。"""

    base_url: str = ""
    api_key: str = "none"
    model: str = ""





class ManagerModeConfig(BaseModel):
    """Manager 模式配置"""

    cleaning_impact_warning: float = 0.3  # 清洗影响率阈值（超过此比例触发警告）


class OutputConfig(BaseModel):
    """输出配置"""

    project_dir: Path = Field(default_factory=lambda: Path.home() / ".hagoku" / "projects")
    formats: list[str] = Field(default_factory=lambda: ["html"])
    date_format: str = "%Y%m%d_%H%M%S"
    naming: str = "{project}_{date}"


class AnalysisConfig(BaseModel):
    """统计分析配置"""

    random_state: int = 42
    p_value_threshold: float = 0.05
    shapiro_sample_limit: int = 5000
    overfitting_gap_threshold: float = 0.2
    k_folds: int = 5  # cross_validate 的折数


class KnowledgeConfig(BaseModel):
    """知识库配置 — 跨项目知识检索参数"""

    similarity_threshold: float = 0.45  # 向量检索相似度阈值（0~1），低于此值的知识条目不回显给 LLM
    top_k_recall: int = 3  # 每个字段检索的历史知识条目数上限
    dedup_similarity: float = 0.85  # learn() 去重阈值：现有条目相似度 > 此值则跳过写入
    learn_confidence_min: float = 0.70  # 仅 confidence ≥ 此值的字段推断才写入知识库


class CleaningConfig(BaseModel):
    """数据清洗配置

    所有阈值均可通过 YAML 配置文件或运行时 set_cleaning_config() 覆盖。
    """

    # ── 异常值检测 ──
    iqr_factor: float = 1.5  # IQR 倍数（异常值判定灵敏度）
    zscore_threshold: float = 3.0  # Z-score 阈值
    isolation_forest_n_estimators: int = 100
    isolation_forest_contamination: float = 0.05  # Isolation Forest 预期异常比例
    min_samples_for_zscore: int = 30  # z-score 最小样本量
    min_samples_for_iforest: int = 50  # Isolation Forest 最小样本量
    max_outlier_pct: float = 0.20  # 离群比例上限（超过此值则标记但不 winsorize）

    # ── 缺失值检测 ──
    mcar_test_alpha: float = 0.05  # Little's MCAR 检验显著性水平
    missing_mechanism_alpha: float = 0.05  # 缺失机制 t 检验显著性
    sig_rate_mcar_below: float = 0.2  # 显著比例 < 此值 → 判定为 MCAR
    sig_rate_mnar_above: float = 0.6  # 显著比例 > 此值 → 判定为 MNAR

    # ── Winsorize 截断 ──
    winsorize_lower_pct: float = 0.05  # 下截断分位数（默认 5%）
    winsorize_upper_pct: float = 0.05  # 上截断分位数（默认 5%）

    # ── 清洗策略推荐阈值 ──
    drop_column_null_rate: float = 0.5  # 缺失率 > 此值 → 建议删除列
    drop_rows_null_rate: float = 0.02  # 缺失率 < 此值 → 删除行影响极小
    mcar_drop_rows_null_rate: float = 0.1  # MCAR 时缺失率 < 此值 → 可安全删行

    # ── 清洗影响评估 ──
    impact_warning_threshold: float = 0.10  # 影响率超过此值触发警告
    large_shift_sigma: float = 0.1  # 分布变化 > 此 σ 值 → 标记为"分布变化"
    bias_large_shift_sigma: float = 0.3  # assess_bias_risk 中判定"大偏移"的 σ 阈值
    row_deletion_bias_risk: float = 0.05  # 删行率 > 此值 → 偏差风险升 medium

    # ── 其他 ──
    iterative_imputer_max_iter: int = 10
    random_state: int = 42


class EmbeddingConfig(BaseModel):
    """向量嵌入配置"""

    base_url: str = ""
    api_key: str = "none"
    model: str = ""  # 用户配置（铁律 9：不写死模型名）
    dimension: int = 1536


class HaGoKuConfig(BaseModel):
    """HaGoKu Studio 全局配置"""

    llm: LLMConfig = Field(default_factory=LLMConfig)
    meta_llm: MetaLLMConfig = Field(default_factory=MetaLLMConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    manager: ManagerModeConfig = Field(default_factory=ManagerModeConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    analysis: AnalysisConfig = Field(default_factory=AnalysisConfig)
    knowledge: KnowledgeConfig = Field(default_factory=KnowledgeConfig)
    cleaning: CleaningConfig = Field(default_factory=CleaningConfig)
    work_dir: Path = Field(default_factory=lambda: Path.home() / ".hagoku")

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
            config_path = Path.home() / ".hagoku" / "config.yaml"
        config = cls.from_yaml(config_path)
        config = cls._merge_env(config)
        return config

    @classmethod
    def _merge_env(cls, config: "HaGoKuConfig") -> "HaGoKuConfig":
        """环境变量覆盖已有配置（HAGOKU_ 前缀，HAGOKYU_ 前缀向后兼容）"""
        # 优先使用 HAGOKU_ 前缀，回退到 HAGOKYU_ 前缀
        if v := os.getenv("HAGOKU_LLM_MODEL") or os.getenv("HAGOKYU_LLM_MODEL"):
            config.llm.model = v
        if v := os.getenv("HAGOKU_LLM_BASE_URL") or os.getenv("HAGOKYU_LLM_BASE_URL"):
            config.llm.base_url = v
        if v := os.getenv("HAGOKU_LLM_API_KEY") or os.getenv("HAGOKYU_LLM_API_KEY"):
            config.llm.api_key = v
        if v := os.getenv("HAGOKU_META_LLM_BASE_URL"):
            config.meta_llm.base_url = v
        if v := os.getenv("HAGOKU_META_LLM_API_KEY"):
            config.meta_llm.api_key = v
        if v := os.getenv("HAGOKU_META_LLM_MODEL"):
            config.meta_llm.model = v
        if v := os.getenv("HAGOKU_WORK_DIR") or os.getenv("HAGOKYU_WORK_DIR"):
            config.work_dir = Path(v).expanduser()
        if v := os.getenv("HAGOKU_PROJECT_DIR") or os.getenv("HAGOKYU_PROJECT_DIR"):
            config.output.project_dir = Path(v).expanduser()
        if v := os.getenv("HAGOKU_EMBEDDING_BASE_URL") or os.getenv("HAGOKYU_EMBEDDING_BASE_URL"):
            config.embedding.base_url = v
        if v := os.getenv("HAGOKU_EMBEDDING_API_KEY") or os.getenv("HAGOKYU_EMBEDDING_API_KEY"):
            config.embedding.api_key = v
        if v := os.getenv("HAGOKU_EMBEDDING_MODEL") or os.getenv("HAGOKYU_EMBEDDING_MODEL"):
            config.embedding.model = v
        # CO-21: stream_enabled from env
        if (v := os.getenv("HAGOKU_LLM_STREAM_ENABLED")) is not None:
            config.llm.stream_enabled = v.strip().lower() in ("true", "1", "yes")
        return config

    def ensure_work_dir(self) -> None:
        """确保工作目录存在（失败则使用临时目录，不阻断）"""
        try:
            self.work_dir.mkdir(parents=True, exist_ok=True)
            (self.work_dir / "projects").mkdir(exist_ok=True)
        except PermissionError:
            # 权限不足 → 回退到临时目录
            import tempfile
            self.work_dir = Path(tempfile.gettempdir()) / ".hagoku"
            self.work_dir.mkdir(exist_ok=True)
            (self.work_dir / "projects").mkdir(exist_ok=True)

    def save(self, config_path: Path | None = None) -> None:
        """保存配置到 YAML 文件"""
        if config_path is None:
            config_path = Path.home() / ".hagoku" / "config.yaml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        # 排除 work_dir（这些由系统决定，不写入用户配置）
        data = self.model_dump(mode="json", exclude={"work_dir"})
        with open(config_path, "w") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)

    def sensitive_fields(self) -> dict[str, str]:
        """返回敏感字段的脱敏值（用于日志/调试输出）"""
        return {
            "api_key": f"{self.llm.api_key[:8]}***" if self.llm.api_key else "(未设置)",
            "embedding_api_key": f"{self.embedding.api_key[:8]}***" if self.embedding.api_key else "(未设置)",
        }

    def __repr__(self) -> str:
        """调试输出时自动脱敏 api_key"""
        safe = self.sensitive_fields()
        return (
            f"HaGoKuConfig(model={self.llm.model!r}, "
            f"base_url={self.llm.base_url!r}, "
            f"api_key={safe['api_key']!r})"
        )