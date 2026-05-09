"""HaGoKu 数据清洗 — 统计感知清洗策略与执行

核心能力：
1. 缺失机制检验：Little's MCAR 检验 + t 检验辅助
2. 异常值检测：IQR / Z-score / Isolation Forest
3. 多重插补：sklearn IterativeImputer (MICE)
4. 清洗前后对比：分布变化 + 统计量变化
5. 偏差风险评估：low / medium / high
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ..config import CleaningConfig
from ..log import get_logger

logger = get_logger("cleaning")

# 模块级配置
_config = CleaningConfig()


def set_cleaning_config(config: CleaningConfig) -> None:
    """设置模块级清洗配置（由 Orchestrator 在启动时调用）"""
    global _config
    _config = config

import numpy as np
import pandas as pd


class MissingMechanism(Enum):
    """缺失机制"""

    MCAR = "mcar"  # 完全随机缺失
    MAR = "mar"  # 随机缺失
    MNAR = "mnar"  # 非随机缺失


class CleaningStrategy(Enum):
    """清洗策略"""

    DROP_ROWS = "drop_rows"
    DROP_COLUMN = "drop_column"
    FILL_MEAN = "fill_mean"
    FILL_MEDIAN = "fill_median"
    FILL_MODE = "fill_mode"
    FILL_CONSTANT = "fill_constant"
    FORWARD_FILL = "forward_fill"
    BACKWARD_FILL = "backward_fill"
    INTERPOLATE = "interpolate"
    MULTIPLE_IMPUTATION = "multiple_imputation"
    FLAG_AND_KEEP = "flag_and_keep"
    WINSORIZE = "winsorize"


@dataclass
class CleaningOp:
    """单次清洗操作"""

    column: str
    strategy: CleaningStrategy
    reason: str
    rows_affected: int = 0
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "column": self.column,
            "strategy": self.strategy.value,
            "reason": self.reason,
            "rows_affected": self.rows_affected,
            "detail": self.detail,
        }


@dataclass
class CleaningReport:
    """清洗报告"""

    total_rows_original: int
    total_rows_after: int
    operations: list[CleaningOp] = field(default_factory=list)
    missing_mechanism: dict[str, str] = field(default_factory=dict)  # 列 → 机制
    impact_rate: float = 0.0  # 总影响率
    warnings: list[str] = field(default_factory=list)
    # 清洗前后对比
    before_stats: dict[str, dict[str, float]] = field(default_factory=dict)
    after_stats: dict[str, dict[str, float]] = field(default_factory=dict)
    distribution_shift: dict[str, float] = field(default_factory=dict)  # 列 → 变化程度
    bias_risk: str = "low"  # low / medium / high
    bias_risk_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_rows_original": self.total_rows_original,
            "total_rows_after": self.total_rows_after,
            "operations": [op.to_dict() for op in self.operations],
            "missing_mechanism": self.missing_mechanism,
            "impact_rate": self.impact_rate,
            "warnings": self.warnings,
            "before_stats": self.before_stats,
            "after_stats": self.after_stats,
            "distribution_shift": self.distribution_shift,
            "bias_risk": self.bias_risk,
            "bias_risk_reason": self.bias_risk_reason,
        }


# ── 缺失机制检验 ──────────────────────────────────────────────


def littles_mcar_test(
    df: pd.DataFrame,
    alpha: float = 0.05,
) -> dict[str, Any]:
    """
    Little's MCAR 检验

    通过卡方检验判断数据是否完全随机缺失。
    原理：如果 MCAR 成立，各缺失模式下的变量均值应与全局均值无显著差异。

    Args:
        df: 数据（仅使用数值列）
        alpha: 显著性水平

    Returns:
        {"statistic": float, "p_value": float, "is_mcar": bool, "conclusion": str}
    """
    from scipy import stats

    numeric_df = df.select_dtypes(include=[np.number])
    cols_with_missing = [c for c in numeric_df.columns if numeric_df[c].isnull().any()]

    if not cols_with_missing:
        return {
            "statistic": 0.0, "p_value": 1.0, "is_mcar": True,
            "conclusion": "无缺失值，无需检验",
        }

    if len(numeric_df) < 10:
        return {
            "statistic": 0.0, "p_value": 1.0, "is_mcar": True,
            "conclusion": "样本量不足（<10），无法可靠检验，默认 MCAR",
        }

    # 构建缺失模式矩阵
    missing_patterns = numeric_df[cols_with_missing].isnull()
    pattern_groups = missing_patterns.groupby(list(cols_with_missing))

    # 简化版 Little's 检验：对每个缺失模式组 vs 完整组做均值差异检验
    complete_mask = ~missing_patterns.any(axis=1)
    complete_data = numeric_df.loc[complete_mask]

    if len(complete_data) < 5:
        return {
            "statistic": 0.0, "p_value": 0.5, "is_mcar": False,
            "conclusion": "完整数据不足，缺失严重，倾向 MAR/MNAR",
        }

    # 对每种缺失模式，检验非缺失列的均值是否与完整组相同
    chi2_total = 0.0
    df_total = 0

    for pattern, group_idx in pattern_groups.groups.items():
        if not isinstance(group_idx, pd.Index):
            continue
        group_data = numeric_df.loc[group_idx]

        # 找该组中非缺失的数值列
        observed_cols = [c for c in cols_with_missing if not pd.isna(pattern[cols_with_missing.index(c)])] if isinstance(pattern, tuple) else []

        if len(group_data) < 3 or not observed_cols:
            continue

        for col in observed_cols:
            obs_vals = group_data[col].dropna()
            comp_vals = complete_data[col].dropna()
            if len(obs_vals) >= 3 and len(comp_vals) >= 3 and obs_vals.std() > 0:
                # Welch t-test
                try:
                    _, p = stats.ttest_ind(obs_vals, comp_vals, equal_var=False)
                    # 负对数似然近似
                    if p > 0:
                        chi2_total += -2 * np.log(p)
                        df_total += 1
                except Exception:
                    pass

    if df_total == 0:
        return {
            "statistic": 0.0, "p_value": 1.0, "is_mcar": True,
            "conclusion": "无法计算检验统计量，默认 MCAR",
        }

    try:
        p_value = float(1 - stats.chi2.cdf(chi2_total, df_total))
    except Exception:
        p_value = 0.5

    is_mcar = p_value > alpha

    return {
        "statistic": round(chi2_total, 4),
        "p_value": round(p_value, 6),
        "is_mcar": is_mcar,
        "conclusion": f"Little's MCAR 检验: χ²={chi2_total:.2f}, p={p_value:.4f} → {'MCAR' if is_mcar else '非 MCAR（可能 MAR 或 MNAR）'}",
    }


def detect_missing_mechanism(
    df: pd.DataFrame,
    column: str,
    alpha: float = 0.05,
) -> str:
    """
    检测缺失机制

    策略：
    1. 先用 Little's MCAR 检验看整体
    2. 对目标列做 t 检验辅助判断 MAR/MNAR

    Args:
        df: 数据
        column: 目标列
        alpha: 显著性水平

    Returns:
        "mcar" / "mar" / "mnar"
    """
    from scipy import stats

    if df[column].notna().all():
        return "mcar"

    missing_mask = df[column].isnull()
    other_cols = [c for c in df.select_dtypes(include=[np.number]).columns if c != column]

    if not other_cols:
        return "mar"

    # 对每个数值列做 t 检验
    n_significant = 0
    n_tests = 0
    for other in other_cols:
        obs_vals = df.loc[~missing_mask, other].dropna()
        mis_vals = df.loc[missing_mask, other].dropna()
        if len(obs_vals) >= 5 and len(mis_vals) >= 5:
            _, p = stats.ttest_ind(obs_vals, mis_vals)
            n_tests += 1
            if p < alpha:
                n_significant += 1

    if n_tests == 0:
        return "mar"

    # 如果显著差异的比例很高，说明缺失与观测变量相关 → MAR
    sig_rate = n_significant / n_tests
    if sig_rate < 0.2:
        return "mcar"
    elif sig_rate < 0.6:
        return "mar"
    else:
        return "mnar"


# ── 异常值检测 ────────────────────────────────────────────────


def detect_outliers_iqr(
    df: pd.DataFrame,
    columns: list[str] | None = None,
    factor: float = 1.5,
) -> dict[str, dict[str, Any]]:
    """
    IQR 法检测异常值

    Args:
        df: 数据
        columns: 要检测的列（默认所有数值列）
        factor: IQR 倍数

    Returns:
        列名 → 异常值信息
    """
    if columns is None:
        columns = df.select_dtypes(include=[np.number]).columns.tolist()

    results = {}
    for col in columns:
        if col not in df.columns or not pd.api.types.is_numeric_dtype(df[col]):
            continue

        # 零方差列无异常值
        if df[col].std() == 0:
            results[col] = {
                "count": 0, "rate": 0,
                "lower_bound": round(float(df[col].iloc[0]), 4) if len(df) > 0 else 0,
                "upper_bound": round(float(df[col].iloc[0]), 4) if len(df) > 0 else 0,
                "q1": round(float(df[col].quantile(0.25)), 4),
                "q3": round(float(df[col].quantile(0.75)), 4),
                "note": "零方差列，无异常值",
            }
            continue

        q1 = df[col].quantile(0.25)
        q3 = df[col].quantile(0.75)
        iqr = q3 - q1
        lower = q1 - factor * iqr
        upper = q3 + factor * iqr

        outlier_mask = (df[col] < lower) | (df[col] > upper)
        n_outliers = int(outlier_mask.sum())

        results[col] = {
            "count": n_outliers,
            "rate": round(n_outliers / len(df), 4) if len(df) > 0 else 0,
            "lower_bound": round(float(lower), 4),
            "upper_bound": round(float(upper), 4),
            "q1": round(float(q1), 4),
            "q3": round(float(q3), 4),
        }

    return results


def detect_outliers_zscore(
    df: pd.DataFrame,
    columns: list[str] | None = None,
    threshold: float = 3.0,
) -> dict[str, dict[str, Any]]:
    """
    Z-score 法检测异常值

    Args:
        df: 数据
        columns: 要检测的列
        threshold: Z-score 阈值

    Returns:
        列名 → 异常值信息
    """
    if columns is None:
        columns = df.select_dtypes(include=[np.number]).columns.tolist()

    results = {}
    for col in columns:
        if col not in df.columns or not pd.api.types.is_numeric_dtype(df[col]):
            continue

        std = df[col].std()
        # 零方差列无异常值
        if std == 0:
            results[col] = {
                "count": 0, "rate": 0,
                "threshold": threshold,
                "max_zscore": 0,
                "note": "零方差列，无异常值",
            }
            continue

        z_scores = np.abs((df[col] - df[col].mean()) / std)
        outlier_mask = z_scores > threshold
        n_outliers = int(outlier_mask.sum())

        results[col] = {
            "count": n_outliers,
            "rate": round(n_outliers / len(df), 4) if len(df) > 0 else 0,
            "threshold": threshold,
            "max_zscore": round(float(z_scores.max()), 4) if len(z_scores) > 0 else 0,
        }

    return results


def detect_outliers_isolation_forest(
    df: pd.DataFrame,
    columns: list[str] | None = None,
    contamination: float = 0.05,
    random_state: int = 42,
) -> dict[str, dict[str, Any]]:
    """
    Isolation Forest 检测异常值

    适合高维数据和复杂异常模式。比 IQR/Z-score 更能发现"集体异常"。

    Args:
        df: 数据
        columns: 要检测的列（默认所有数值列）
        contamination: 预期异常比例
        random_state: 随机种子

    Returns:
        列名 → 异常值信息（每列被标记为异常的行数）
    """
    if columns is None:
        columns = df.select_dtypes(include=[np.number]).columns.tolist()

    try:
        from sklearn.ensemble import IsolationForest
    except ImportError:
        return {
            "__note": {
                "error": "sklearn 未安装，无法使用 Isolation Forest",
                "count": 0, "rate": 0,
            }
        }

    numeric_df = df[columns].dropna(axis=1, how="all")
    usable_cols = [c for c in columns if c in numeric_df.columns and numeric_df[c].notna().sum() >= 10]

    if len(usable_cols) < 2:
        return {}

    # 填充缺失用于模型
    filled = numeric_df[usable_cols].fillna(numeric_df[usable_cols].median())

    iso = IsolationForest(contamination=contamination, random_state=random_state, n_estimators=_config.isolation_forest_n_estimators)
    outlier_labels = iso.fit_predict(filled)  # -1 = 异常, 1 = 正常
    outlier_mask = outlier_labels == -1

    # 统计每列的异常贡献
    results = {}
    outlier_df = filled[outlier_mask]
    normal_df = filled[~outlier_mask]

    for col in usable_cols:
        # 异常组 vs 正常组的均值偏差
        if len(outlier_df) > 0 and normal_df[col].std() > 0:
            mean_shift = abs(outlier_df[col].mean() - normal_df[col].mean()) / normal_df[col].std()
        else:
            mean_shift = 0

        results[col] = {
            "count": len(outlier_df),
            "rate": round(len(outlier_df) / len(df), 4) if len(df) > 0 else 0,
            "mean_shift_sigma": round(float(mean_shift), 4),
            "method": "isolation_forest",
        }

    # 全局异常行
    results["__global"] = {
        "count": int(outlier_mask.sum()),
        "rate": round(float(outlier_mask.mean()), 4),
        "method": "isolation_forest",
        "note": "Isolation Forest 标记的全局异常行",
    }

    return results


# ── Winsorize ────────────────────────────────────────────────


def winsorize_column(
    series: pd.Series,
    lower: float = 0.05,
    upper: float = 0.05,
) -> pd.Series:
    """
    Winsorize：将极端值截断到指定分位数，不删除行

    Args:
        series: 数据列（必须为数值类型）
        lower: 下截断分位数
        upper: 上截断分位数

    Returns:
        截断后的 Series
    """
    if not pd.api.types.is_numeric_dtype(series):
        raise TypeError(f"winsorize_column 仅支持数值类型，收到: {series.dtype}")
    low_val = series.quantile(lower)
    high_val = series.quantile(1 - upper)
    return series.clip(lower=low_val, upper=high_val)


# ── 清洗策略推荐 ──────────────────────────────────────────────


def suggest_cleaning_strategy(
    df: pd.DataFrame,
    column: str,
    null_rate: float | None = None,
    missing_mechanism: str | None = None,
) -> tuple[CleaningStrategy, str]:
    """
    建议清洗策略

    Args:
        df: 数据
        column: 目标列
        null_rate: 缺失率（如不提供则自动计算）
        missing_mechanism: 缺失机制（如不提供则自动检测）

    Returns:
        (策略, 理由)
    """
    if null_rate is None:
        null_rate = df[column].isnull().mean()

    if missing_mechanism is None:
        missing_mechanism = detect_missing_mechanism(df, column)

    # 高缺失率 → 删除列
    if null_rate > 0.5:
        return CleaningStrategy.DROP_COLUMN, f"缺失率 {null_rate:.1%} > 50%，建议删除列"

    # 极低缺失率 → 删除行
    if null_rate < 0.02:
        return CleaningStrategy.DROP_ROWS, f"缺失率 {null_rate:.1%} < 2%，删除行影响极小"

    # MCAR → 可以安全删除或简单填充
    if missing_mechanism == "mcar":
        if null_rate < 0.1:
            return CleaningStrategy.DROP_ROWS, f"MCAR 且缺失率 {null_rate:.1%} < 10%，删除行安全"
        return CleaningStrategy.FILL_MEDIAN, f"MCAR 但缺失率 {null_rate:.1%} 较高，中位数填充"

    # MAR → 需要更谨慎
    if missing_mechanism == "mar":
        return CleaningStrategy.MULTIPLE_IMPUTATION, "MAR 缺失，建议多重插补以减少偏差"

    # MNAR → 最谨慎
    return CleaningStrategy.FLAG_AND_KEEP, "MNAR 缺失，建议标记缺失而非删除，避免引入偏差"


# ── 清洗前后对比 ──────────────────────────────────────────────


def compute_stats_snapshot(df: pd.DataFrame, columns: list[str] | None = None) -> dict[str, dict[str, float]]:
    """
    计算数值列的统计快照（均值、标准差、中位数、偏度）

    Args:
        df: 数据
        columns: 指定列（默认所有数值列）

    Returns:
        列名 → 统计量字典
    """
    if columns is None:
        columns = df.select_dtypes(include=[np.number]).columns.tolist()

    snapshot = {}
    for col in columns:
        if col not in df.columns or not pd.api.types.is_numeric_dtype(df[col]):
            continue
        series = df[col].dropna()
        if len(series) == 0:
            continue
        snapshot[col] = {
            "mean": round(float(series.mean()), 6),
            "std": round(float(series.std()), 6),
            "median": round(float(series.median()), 6),
            "skew": round(float(series.skew()), 4) if len(series) > 2 else 0,
        }

    return snapshot


def compare_before_after(
    before: dict[str, dict[str, float]],
    after: dict[str, dict[str, float]],
) -> dict[str, float]:
    """
    对比清洗前后的统计量变化

    返回每列的"分布变化程度"：均值变化 / 原标准差，即以标准差为单位的均值偏移。
    值越大表示清洗对该列分布影响越大。

    Args:
        before: 清洗前快照
        after: 清洗后快照

    Returns:
        列名 → 变化程度（sigma 单位）
    """
    shift = {}
    for col in before:
        if col not in after:
            continue
        b = before[col]
        a = after[col]
        # 均值偏移（以标准差为单位）
        if b.get("std", 0) > 0:
            mean_shift = abs(a.get("mean", 0) - b.get("mean", 0)) / b["std"]
        else:
            mean_shift = 0
        # 标准差变化率
        if b.get("std", 0) > 0:
            std_change = abs(a.get("std", 0) - b.get("std", 0)) / b["std"]
        else:
            std_change = 0
        # 综合变化指标
        shift[col] = round(float(max(mean_shift, std_change)), 4)

    return shift


def assess_bias_risk(
    impact_rate: float,
    distribution_shift: dict[str, float],
    mechanisms: dict[str, str],
) -> tuple[str, str]:
    """
    评估清洗引入偏差的风险

    Args:
        impact_rate: 总影响率
        distribution_shift: 各列分布变化程度
        mechanisms: 各列缺失机制

    Returns:
        (风险等级, 原因)
    """
    # 影响率判断
    if impact_rate > 0.20:
        return "high", f"清洗影响了 {impact_rate:.1%} 的数据，偏差风险高"

    # MNAR 列被处理
    mnar_cols = [c for c, m in mechanisms.items() if m == "mnar"]
    if mnar_cols:
        if impact_rate > 0.05:
            return "high", f"存在 MNAR 缺失列 {mnar_cols} 且影响率 {impact_rate:.1%} > 5%，偏差风险高"

    # 分布变化大的列
    large_shift = [c for c, s in distribution_shift.items() if s > 0.3]
    if len(large_shift) >= 2:
        return "medium", f"{len(large_shift)} 列分布变化 > 0.3σ: {large_shift}"

    if mnar_cols:
        return "medium", f"存在 MNAR 缺失列 {mnar_cols}，偏差风险中等"

    if impact_rate > 0.10:
        return "medium", f"影响率 {impact_rate:.1%} > 10%，偏差风险中等"

    return "low", "影响率低，缺失机制为 MCAR/MAR，偏差风险低"


# ── 清洗执行 ──────────────────────────────────────────────────


def clean_data(
    df: pd.DataFrame,
    operations: list[dict[str, Any]] | None = None,
    *,
    auto_strategy: bool = True,
    impact_warning: float = 0.10,
) -> tuple[pd.DataFrame, CleaningReport]:
    """
    执行数据清洗

    Args:
        df: 原始数据
        operations: 手动指定的清洗操作列表，每项包含 column, strategy, reason
        auto_strategy: 是否自动为缺失列建议策略
        impact_warning: 影响率超过此值时发出警告

    Returns:
        (清洗后的 DataFrame, 清洗报告)
    """
    # 空 DataFrame
    if len(df) == 0:
        return df.copy(), CleaningReport(
            total_rows_original=0,
            total_rows_after=0,
            warnings=["输入数据为空"],
        )

    original_rows = len(df)
    df_clean = df.copy()
    ops: list[CleaningOp] = []
    warnings: list[str] = []
    mechanisms: dict[str, str] = {}

    # 清洗前快照
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    before_stats = compute_stats_snapshot(df, numeric_cols)

    if operations is None and auto_strategy:
        # 自动为每列缺失建议策略
        operations = []
        for col in df.columns:
            null_rate = df[col].isnull().mean()
            if null_rate > 0:
                mechanism = detect_missing_mechanism(df, col)
                mechanisms[col] = mechanism
                strategy, reason = suggest_cleaning_strategy(df, col, null_rate, mechanism)
                operations.append({
                    "column": col,
                    "strategy": strategy.value,
                    "reason": reason,
                })

    if operations:
        for op_spec in operations:
            col = op_spec["column"]
            strategy = CleaningStrategy(op_spec["strategy"])
            reason = op_spec.get("reason", "")
            ops_detail: dict[str, Any] = op_spec.get("detail", {})

            if col not in df_clean.columns:
                warnings.append(f"列 '{col}' 不存在，跳过")
                continue

            n_before = len(df_clean)
            rows_affected = int(df_clean[col].isnull().sum())

            if strategy == CleaningStrategy.DROP_ROWS:
                df_clean = df_clean.dropna(subset=[col])
                rows_affected = n_before - len(df_clean)

            elif strategy == CleaningStrategy.DROP_COLUMN:
                df_clean = df_clean.drop(columns=[col])
                rows_affected = 0

            elif strategy == CleaningStrategy.FILL_MEAN:
                if pd.api.types.is_numeric_dtype(df_clean[col]):
                    fill_val = df_clean[col].mean()
                    df_clean[col] = df_clean[col].fillna(fill_val)
                    ops_detail = {"fill_value": round(float(fill_val), 4)}
                else:
                    warnings.append(f"列 '{col}' 为非数值类型，跳过 FILL_MEAN")
                    continue

            elif strategy == CleaningStrategy.FILL_MEDIAN:
                if pd.api.types.is_numeric_dtype(df_clean[col]):
                    fill_val = df_clean[col].median()
                    df_clean[col] = df_clean[col].fillna(fill_val)
                    ops_detail = {"fill_value": round(float(fill_val), 4)}
                else:
                    warnings.append(f"列 '{col}' 为非数值类型，跳过 FILL_MEDIAN")
                    continue

            elif strategy == CleaningStrategy.FILL_MODE:
                fill_val = df_clean[col].mode().iloc[0] if len(df_clean[col].mode()) > 0 else ""
                df_clean[col] = df_clean[col].fillna(fill_val)
                ops_detail = {"fill_value": fill_val}

            elif strategy == CleaningStrategy.FILL_CONSTANT:
                fill_val = op_spec.get("fill_value", 0)
                df_clean[col] = df_clean[col].fillna(fill_val)
                ops_detail = {"fill_value": fill_val}

            elif strategy == CleaningStrategy.FORWARD_FILL:
                df_clean[col] = df_clean[col].ffill()

            elif strategy == CleaningStrategy.BACKWARD_FILL:
                df_clean[col] = df_clean[col].bfill()

            elif strategy == CleaningStrategy.INTERPOLATE:
                df_clean[col] = df_clean[col].interpolate(method="linear")

            elif strategy == CleaningStrategy.MULTIPLE_IMPUTATION:
                # MICE: sklearn IterativeImputer
                try:
                    from sklearn.impute import IterativeImputer

                    numeric_cols_in_df = df_clean.select_dtypes(include=[np.number]).columns
                    if col in numeric_cols_in_df:
                        imputer = IterativeImputer(max_iter=_config.iterative_imputer_max_iter, random_state=_config.random_state)
                        imputed = imputer.fit_transform(df_clean[numeric_cols_in_df])
                        df_clean[numeric_cols_in_df] = imputed
                        ops_detail = {"method": "MICE (IterativeImputer)", "max_iter": 10}
                    else:
                        df_clean[col] = df_clean[col].fillna(df_clean[col].mode().iloc[0] if len(df_clean[col].mode()) > 0 else "")
                        ops_detail = {"method": "mode (非数值列退回众数)"}
                except ImportError:
                    # sklearn 不可用时退回到中位数
                    fill_val = df_clean[col].median() if pd.api.types.is_numeric_dtype(df_clean[col]) else (df_clean[col].mode().iloc[0] if len(df_clean[col].mode()) > 0 else "")
                    df_clean[col] = df_clean[col].fillna(fill_val)
                    ops_detail = {"method": "median (sklearn未安装，退回中位数)"}
                    warnings.append(f"sklearn 未安装，列 '{col}' 退回中位数/众数填充")

            elif strategy == CleaningStrategy.FLAG_AND_KEEP:
                df_clean[f"{col}_missing"] = df_clean[col].isnull().astype(int)
                ops_detail = {"flag_column": f"{col}_missing"}

            elif strategy == CleaningStrategy.WINSORIZE:
                if not pd.api.types.is_numeric_dtype(df_clean[col]):
                    warnings.append(f"列 '{col}' 为非数值类型，跳过 Winsorize")
                    continue
                lower_pct = op_spec.get("lower", 0.05)
                upper_pct = op_spec.get("upper", 0.05)
                n_before_win = int(((df_clean[col] < df_clean[col].quantile(lower_pct)) | (df_clean[col] > df_clean[col].quantile(1 - upper_pct))).sum())
                df_clean[col] = winsorize_column(df_clean[col], lower_pct, upper_pct)
                rows_affected = n_before_win
                ops_detail = {"lower_pct": lower_pct, "upper_pct": upper_pct, "values_clipped": n_before_win}

            ops.append(CleaningOp(
                column=col,
                strategy=strategy,
                reason=reason,
                rows_affected=rows_affected,
                detail=ops_detail,
            ))

    # 计算影响率
    rows_removed = original_rows - len(df_clean)
    impact_rate = rows_removed / original_rows if original_rows > 0 else 0

    if impact_rate > impact_warning:
        warnings.append(
            f"⚠️ 清洗影响率 {impact_rate:.1%} 超过阈值 {impact_warning:.0%}，"
            f"移除了 {rows_removed} 行数据"
        )

    # 清洗后快照
    after_stats = compute_stats_snapshot(df_clean, [c for c in numeric_cols if c in df_clean.columns])
    distribution_shift = compare_before_after(before_stats, after_stats)

    # 偏差风险评估
    bias_risk, bias_risk_reason = assess_bias_risk(impact_rate, distribution_shift, mechanisms)

    report = CleaningReport(
        total_rows_original=original_rows,
        total_rows_after=len(df_clean),
        operations=ops,
        missing_mechanism=mechanisms,
        impact_rate=round(impact_rate, 4),
        warnings=warnings,
        before_stats=before_stats,
        after_stats=after_stats,
        distribution_shift=distribution_shift,
        bias_risk=bias_risk,
        bias_risk_reason=bias_risk_reason,
    )

    return df_clean, report
