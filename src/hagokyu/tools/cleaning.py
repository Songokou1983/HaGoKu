"""HaGoKu 数据清洗 — 清洗策略与执行"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

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

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_rows_original": self.total_rows_original,
            "total_rows_after": self.total_rows_after,
            "operations": [op.to_dict() for op in self.operations],
            "missing_mechanism": self.missing_mechanism,
            "impact_rate": self.impact_rate,
            "warnings": self.warnings,
        }


def detect_missing_mechanism(
    df: pd.DataFrame,
    column: str,
    alpha: float = 0.05,
) -> str:
    """
    检测缺失机制（简化版）

    MCAR 检验：比较缺失组和非缺失组在其他变量上的分布。
    如果无显著差异，判定为 MCAR。

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
        return CleaningStrategy.MULTIPLE_IMPUTATION, f"MAR 缺失，建议多重插补以减少偏差"

    # MNAR → 最谨慎
    return CleaningStrategy.FLAG_AND_KEEP, f"MNAR 缺失，建议标记缺失而非删除，避免引入偏差"


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
    original_rows = len(df)
    df_clean = df.copy()
    ops: list[CleaningOp] = []
    warnings: list[str] = []
    mechanisms: dict[str, str] = {}

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
                fill_val = df_clean[col].mean()
                df_clean[col] = df_clean[col].fillna(fill_val)
                ops_detail = {"fill_value": round(float(fill_val), 4)}

            elif strategy == CleaningStrategy.FILL_MEDIAN:
                fill_val = df_clean[col].median()
                df_clean[col] = df_clean[col].fillna(fill_val)
                ops_detail = {"fill_value": round(float(fill_val), 4)}

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
                # 简化版：使用中位数填充（完整的多重插补需要 sklearn IterativeImputer）
                try:
                    from sklearn.impute import IterativeImputer

                    numeric_cols = df_clean.select_dtypes(include=[np.number]).columns
                    if col in numeric_cols:
                        imputer = IterativeImputer(max_iter=10, random_state=42)
                        imputed = imputer.fit_transform(df_clean[numeric_cols])
                        df_clean[numeric_cols] = imputed
                    else:
                        df_clean[col] = df_clean[col].fillna(df_clean[col].mode().iloc[0] if len(df_clean[col].mode()) > 0 else "")
                except ImportError:
                    # sklearn 不可用时退回到中位数
                    fill_val = df_clean[col].median() if pd.api.types.is_numeric_dtype(df_clean[col]) else (df_clean[col].mode().iloc[0] if len(df_clean[col].mode()) > 0 else "")
                    df_clean[col] = df_clean[col].fillna(fill_val)
                    warnings.append(f"sklearn 未安装，列 '{col}' 退回中位数/众数填充")

            elif strategy == CleaningStrategy.FLAG_AND_KEEP:
                df_clean[f"{col}_missing"] = df_clean[col].isnull().astype(int)

            ops.append(CleaningOp(
                column=col,
                strategy=strategy,
                reason=reason,
                rows_affected=rows_affected,
                detail=op_spec.get("detail", {}),
            ))

    # 计算影响率
    rows_removed = original_rows - len(df_clean)
    impact_rate = rows_removed / original_rows if original_rows > 0 else 0

    if impact_rate > impact_warning:
        warnings.append(
            f"⚠️ 清洗影响率 {impact_rate:.1%} 超过阈值 {impact_warning:.0%}，"
            f"移除了 {rows_removed} 行数据"
        )

    report = CleaningReport(
        total_rows_original=original_rows,
        total_rows_after=len(df_clean),
        operations=ops,
        missing_mechanism=mechanisms,
        impact_rate=round(impact_rate, 4),
        warnings=warnings,
    )

    return df_clean, report


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

        z_scores = np.abs((df[col] - df[col].mean()) / df[col].std())
        outlier_mask = z_scores > threshold
        n_outliers = int(outlier_mask.sum())

        results[col] = {
            "count": n_outliers,
            "rate": round(n_outliers / len(df), 4) if len(df) > 0 else 0,
            "threshold": threshold,
            "max_zscore": round(float(z_scores.max()), 4) if len(z_scores) > 0 else 0,
        }

    return results
