"""
HaGoKu Studio Agent 层共享常量 —— 消除魔术字 / 硬编码阈值。

所有模块级常量集中在此，供 analyst / reporter / scout / cleaner 引用。
"""
from __future__ import annotations

# ═══════════════════════════════════════════════════════════════
# 统计分析通用阈值
# ═══════════════════════════════════════════════════════════════

# 显著性判定
SIGNIFICANCE_THRESHOLD: float = 0.05
SIGNIFICANCE_LABEL_SIG: str = "significant"
SIGNIFICANCE_LABEL_NOT_SIG: str = "not_significant"
SIGNIFICANCE_LABEL_CORRECTED: str = "not_significant_after_correction"

# ── 功效预检 ──
POWER_MIN_TOTAL_SAMPLE = 30        # 总样本量下限
POWER_MIN_PER_GROUP_SAMPLE = 15    # 每组最低样本量
POWER_ADEQUATE_PER_GROUP = 30      # 每组充足样本量
POWER_EFFECT_SIZE_DEFAULT = 0.5    # 默认中等效应量（Cohen's d）
POWER_TARGET_PCT = 80              # 目标检验功效百分比
POWER_REGRESSION_RATIO = 10        # 回归 n / predictor 最小比例

# ── 相关性强度 ──
CORRELATION_THRESHOLD_STRONG_ABS: float = 0.7
CORRELATION_THRESHOLD_MODERATE_ABS: float = 0.4
CORRELATION_LABEL_STRONG: str = "强"
CORRELATION_LABEL_MODERATE: str = "中"
CORRELATION_LABEL_WEAK: str = "弱"
CORRELATION_DIRECTION_POS: str = "正"
CORRELATION_DIRECTION_NEG: str = "负"

# ── 交叉验证 ──
CROSS_VALIDATION_FOLDS_DEFAULT: int = 5

# ═══════════════════════════════════════════════════════════════
# 数据类型推断 — 角色标签
# ═══════════════════════════════════════════════════════════════

ROLE_IDENTIFIER: str = "identifier"
ROLE_TIME_INDEX: str = "time_index"
ROLE_BINARY_FEATURE: str = "binary_feature"
ROLE_TARGET: str = "target"
ROLE_NUMERIC_FEATURE: str = "numeric_feature"
ROLE_CATEGORICAL_FEATURE: str = "categorical_feature"
ROLE_TEXT_FEATURE: str = "text_feature"
ROLE_UNKNOWN: str = "unknown"

# 推断类型
INFERRED_TYPE_ID: str = "id"
INFERRED_TYPE_DATETIME: str = "datetime"
INFERRED_TYPE_BOOLEAN: str = "boolean"
INFERRED_TYPE_NUMERIC: str = "numeric"
INFERRED_TYPE_CATEGORICAL: str = "categorical"
INFERRED_TYPE_TEXT: str = "text"
INFERRED_TYPE_UNKNOWN: str = "unknown"

# ═══════════════════════════════════════════════════════════════
# Reporter — 分析类型 → 展示标签
# ═══════════════════════════════════════════════════════════════

ANALYSIS_TYPE_DISPLAY_MAP: dict[str, str] = {
    "regression": "📈 回归分析",
    "hypothesis_test": "🔬 假设检验",
    "trend_analysis": "📈 趋势分析",
    "correlation": "🔗 相关性分析",
}
ANALYSIS_TYPE_DISPLAY_FALLBACK: str = "📊 分析结果"

# ═══════════════════════════════════════════════════════════════
# Reporter — 商业指标类型
# ═══════════════════════════════════════════════════════════════

BUSINESS_METRIC_ROI: str = "roi"
BUSINESS_METRIC_ROAS: str = "roas"
BUSINESS_METRIC_ROI_LABEL: str = "ROI"
BUSINESS_METRIC_ROAS_LABEL: str = "ROAS"
BUSINESS_METRIC_ROI_FORMAT: str = "{:.1f}%"
BUSINESS_METRIC_ROAS_FORMAT: str = "{:.1f}x"
BUSINESS_METRIC_SECTION_TITLE: str = "💰 商业指标"

# ═══════════════════════════════════════════════════════════════
# Reporter — Headline / 展示截断
# ═══════════════════════════════════════════════════════════════

REPORTER_HEADLINE_MAX_LEN: int = 80
REPORTER_FINDING_PREVIEW_MAX_LEN: int = 77
REPORTER_FINDING_HEADLINE_MAX_LEN: int = 60
REPORTER_FINDING_HEADLINE_TRUNC: int = 57

# ═══════════════════════════════════════════════════════════════
# Cleaner — 策略枚举值
# ═══════════════════════════════════════════════════════════════

from enum import Enum as _Enum

class CleanerStrategyLabels:
    """Cleaner 策略中文展示标签（与 CleaningStrategy 枚举值解耦）。"""
    DROP_NULL: str = "删除空值"
    DROP_DUPLICATE: str = "删除重复"
    FILL_MEDIAN: str = "中位数填充"
    FILL_MEAN: str = "均值填充"
    FILL_MODE: str = "众数填充"
    FILL_ZERO: str = "填零"
    FILL_CUSTOM: str = "自定义填充"
    REPLACE_VALUE: str = "替换值"
    DROP_ROW: str = "删除行"
    DROP_OUTLIER_IQR: str = "IQR 离群值删除"
    CLIP_EXTREME: str = "截尾"
    REMOVE_AHEAD: str = "移除超期"
    REMOVE_PAST: str = "移除过期"
    CAST_DTYPE: str = "类型转换"
    PARSE_DATE: str = "日期解析"
    FILTER_RANGE: str = "区间筛选"
    FILTER_EXACT: str = "精确筛选"
    NO_ACTION: str = "无操作"

    @classmethod
    def for_strategy(cls, strategy_value: str) -> str:
        """根据策略枚举值返回中文标签，未知策略返回原文。"""
        mapping: dict[str, str] = {
            "drop_null": cls.DROP_NULL,
            "drop_duplicate": cls.DROP_DUPLICATE,
            "fill_median": cls.FILL_MEDIAN,
            "fill_mean": cls.FILL_MEAN,
            "fill_mode": cls.FILL_MODE,
            "fill_zero": cls.FILL_ZERO,
            "fill_custom": cls.FILL_CUSTOM,
            "replace_value": cls.REPLACE_VALUE,
            "drop_row": cls.DROP_ROW,
            "drop_outlier_iqr": cls.DROP_OUTLIER_IQR,
            "clip_extreme": cls.CLIP_EXTREME,
            "remove_ahead": cls.REMOVE_AHEAD,
            "remove_past": cls.REMOVE_PAST,
            "cast_dtype": cls.CAST_DTYPE,
            "parse_date": cls.PARSE_DATE,
            "filter_range": cls.FILTER_RANGE,
            "filter_exact": cls.FILTER_EXACT,
            "no_action": cls.NO_ACTION,
        }
        return mapping.get(strategy_value, strategy_value)

# ═══════════════════════════════════════════════════════════════
# 质量 / 偏差风险
# ═══════════════════════════════════════════════════════════════

CLEANING_IMPACT_HIGH_THRESHOLD: float = 0.12
CLEANING_IMPACT_MEDIUM_THRESHOLD: float = 0.04

# Durbin-Watson 自相关阈值
DW_LOWER_BOUND: float = 1.5
DW_UPPER_BOUND: float = 2.5

# Token 速率最低阈值 (tok/s)
LLM_TOKEN_RATE_MIN: float = 5.0

# ═══════════════════════════════════════════════════════════════
# Scout — 字段解析 / 样本显示截断
# ═══════════════════════════════════════════════════════════════

SCOUT_COLNAME_MAX_LEN: int = 64            # LLM 输出列名长度上限
SCOUT_SAMPLE_TRUNCATE_LEN: int = 20         # 样本值显示截断阈值
SCOUT_SAMPLE_PREVIEW_LEN: int = 17          # 截断后保留字符数
SCOUT_LABEL_TRUNCATE_LEN: int = 30          # top_values 标签截断阈值
SCOUT_LABEL_PREVIEW_LEN: int = 27           # 截断后保留字符数
SCOUT_TOP_VALUES_MAX_UNIQUE: int = 100      # 展示 top-values 的唯一值数上限

# Scout — LLM 调用参数
SCOUT_INFER_MAX_TOKENS: int = 8192
SCOUT_INFER_TEMPERATURE: float = 0.0
SCOUT_CONFIRM_MAX_TOKENS: int = 1200
SCOUT_CONFIRM_TEMPERATURE: float = 0.5

# Scout — 学习/去重阈值
SCOUT_LEARN_CONFIDENCE_MIN: float = 0.85    # 只学习置信度 ≥ 此值的推断
SCOUT_DEDUP_SIMILARITY: float = 0.9         # 知识去重相似度

# ═══════════════════════════════════════════════════════════════
# 知识去重相似度（Agent 间不一致，保留旧值直到统一）
# ═══════════════════════════════════════════════════════════════

ANALYST_DEDUP_SIMILARITY: float = 0.85

# ═══════════════════════════════════════════════════════════════
# Scribe — 日志/兜底截断
# ═══════════════════════════════════════════════════════════════

SCRIBE_THOUGHT_TRUNCATE: int = 100
SCRIBE_SUMMARY_TRUNCATE: int = 80
SCRIBE_FALLBACK_TOKEN_PER_COL: int = 64      # 兜底 LLM token 每列估算
SCRIBE_FALLBACK_MIN_TOKENS: int = 256
SCRIBE_FALLBACK_TEMPERATURE: float = 0.1

# 交叉验证最小样本公式参数
CROSS_VAL_MIN_N_PER_FEATURE: int = 3        # min_n = len(features) + 此值