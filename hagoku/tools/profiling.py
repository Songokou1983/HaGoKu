"""HaGoKu Studio 数据画像 — 快速了解数据全貌"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def generate_profile(df: pd.DataFrame, *, minimal: bool = True) -> dict[str, Any]:
    """
    生成数据画像，返回结构化结果

    轻量级画像，不依赖 ydata-profiling（重），纯 pandas + numpy 实现。
    如果需要完整画像，可用 generate_full_profile()。

    Args:
        df: 数据
        minimal: 是否只返回关键统计量

    Returns:
        结构化画像字典
    """
    # 空 DataFrame 安全处理
    if len(df) == 0:
        return {
            "n_rows": 0,
            "n_cols": len(df.columns),
            "columns": {},
            "missing_summary": {"total_nulls": 0, "null_rate": 0, "columns_with_nulls": 0, "column_details": {}},
            "duplicate_rate": 0,
            "duplicate_rows": 0,
            "memory_mb": 0,
            "correlations": {},
            "quality_score": 0,
        }

    profile: dict[str, Any] = {
        "n_rows": len(df),
        "n_cols": len(df.columns),
        "columns": {},
        "missing_summary": _missing_summary(df),
        "duplicate_rate": round(df.duplicated().mean(), 4),
        "duplicate_rows": int(df.duplicated().sum()),
        "memory_mb": round(df.memory_usage(deep=True).sum() / 1024 / 1024, 2),
    }

    # 各列统计
    for col in df.columns:
        profile["columns"][col] = _column_profile(df[col], minimal=minimal)

    # 相关性矩阵（数值列）
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    if len(numeric_cols) >= 2:
        profile["correlations"] = _compute_correlations(df[numeric_cols])
    else:
        profile["correlations"] = {}

    # 数据质量评分
    profile["quality_score"] = _compute_quality_score(profile)

    return profile


def generate_full_profile(df: pd.DataFrame) -> dict[str, Any]:
    """
    生成完整数据画像（使用 ydata-profiling）

    需要安装 ydata-profiling: pip install ydata-profiling

    Args:
        df: 数据

    Returns:
        ydata-profiling 的结构化结果
    """
    import importlib.util

    if importlib.util.find_spec("ydata_profiling") is None:
        raise ImportError(
            "ydata-profiling 未安装。请运行: pip install ydata-profiling\n"
            "或使用轻量级画像: generate_profile(df)"
        )

    # 提取关键信息
    return {
        "n_rows": len(df),
        "n_cols": len(df.columns),
        "columns": {col: _column_profile(df[col], minimal=False) for col in df.columns},
        "missing_summary": _missing_summary(df),
        "duplicate_rate": round(df.duplicated().mean(), 4),
        "correlations": _compute_correlations(df.select_dtypes(include=[np.number])),
        "quality_score": _compute_quality_score({
            "missing_summary": _missing_summary(df),
            "duplicate_rate": round(df.duplicated().mean(), 4),
        }),
    }


def _column_profile(series: pd.Series, *, minimal: bool = True) -> dict[str, Any]:
    """单列画像"""
    col_type = _infer_type(series)
    n_null = int(series.isnull().sum())
    n_unique = int(series.nunique())

    profile: dict[str, Any] = {
        "dtype": str(series.dtype),
        "inferred_type": col_type,
        "null_count": n_null,
        "null_rate": round(n_null / len(series), 4) if len(series) > 0 else 0,
        "unique_count": n_unique,
        "unique_rate": round(n_unique / len(series), 4) if len(series) > 0 else 0,
    }

    if col_type == "numeric":
        desc = series.describe()
        profile.update({
            "mean": round(float(desc["mean"]), 4) if not np.isnan(desc["mean"]) else None,
            "std": round(float(desc["std"]), 4) if not np.isnan(desc["std"]) else None,
            "min": float(desc["min"]) if not np.isnan(desc["min"]) else None,
            "q25": float(desc["25%"]) if not np.isnan(desc["25%"]) else None,
            "median": float(desc["50%"]) if not np.isnan(desc["50%"]) else None,
            "q75": float(desc["75%"]) if not np.isnan(desc["75%"]) else None,
            "max": float(desc["max"]) if not np.isnan(desc["max"]) else None,
            "skewness": round(float(series.skew()), 4) if not np.isnan(series.skew()) else None,
            "kurtosis": round(float(series.kurtosis()), 4) if not np.isnan(series.kurtosis()) else None,
            "has_zeros": bool((series == 0).any()),
            "zero_rate": round(float((series == 0).mean()), 4),
        })

        # 异常值检测 (IQR 法)
        if not minimal:
            q1, q3 = desc["25%"], desc["75%"]
            iqr = q3 - q1
            if iqr > 0:
                lower = q1 - 1.5 * iqr
                upper = q3 + 1.5 * iqr
                outliers = series[(series < lower) | (series > upper)]
                profile["outliers_iqr"] = {
                    "count": len(outliers),
                    "rate": round(len(outliers) / len(series), 4),
                    "lower_bound": round(float(lower), 4),
                    "upper_bound": round(float(upper), 4),
                }

    elif col_type == "categorical":
        value_counts = series.value_counts()
        profile.update({
            "top_values": value_counts.head(10).to_dict(),
            "top_value": str(value_counts.index[0]) if len(value_counts) > 0 else None,
            "top_freq": int(value_counts.iloc[0]) if len(value_counts) > 0 else 0,
        })

        # 唯一值过多可能是 ID 列
        if n_unique > len(series) * 0.8:
            profile["likely_id"] = True

    elif col_type == "datetime":
        profile.update({
            "min_date": str(series.min()),
            "max_date": str(series.max()),
            "date_range_days": (series.max() - series.min()).days if pd.notna(series.max()) and pd.notna(series.min()) else None,
        })

    elif col_type == "boolean":
        profile.update({
            "true_count": int(series.sum()),
            "true_rate": round(float(series.mean()), 4),
        })

    return profile


def _infer_type(series: pd.Series) -> str:
    """推断列的语义类型"""
    # 全 NaN 列
    if series.isna().all():
        return "unknown"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"
    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    if pd.api.types.is_numeric_dtype(series):
        n_unique = series.nunique()
        # 高唯一率的数值列可能是 ID，但需额外验证：
        # 浮点列高唯一率是正常的（连续值），只有整数列且接近连续序列才判为 ID
        if n_unique > len(series) * 0.8:
            if not pd.api.types.is_float_dtype(series):
                # 整数列：检查是否接近连续序列（如 0,1,2,...,N）
                vals = series.dropna().sort_values()
                val_range = vals.max() - vals.min() + 1
                # 如果值域接近唯一值数，说明是连续序列 → ID
                if val_range <= n_unique * 1.1:
                    return "id"
            # 浮点列或非连续整数列，高唯一率也保持 numeric
        # 低唯一值数的整数列可能是分类（如 flag/枚举），浮点列保持 numeric
        if (not pd.api.types.is_float_dtype(series)
                and n_unique <= 10 and n_unique < len(series) * 0.05):
            return "categorical"
        return "numeric"
    # 字符串列
    if pd.api.types.is_string_dtype(series) or series.dtype == object:
        n_unique = series.nunique()
        # 唯一值比例很高，可能是 ID
        if n_unique > len(series) * 0.8:
            return "id"
        return "categorical"
    return "unknown"


def _missing_summary(df: pd.DataFrame) -> dict[str, Any]:
    """缺失值摘要"""
    null_counts = df.isnull().sum()
    null_cols = null_counts[null_counts > 0]

    return {
        "total_nulls": int(null_counts.sum()),
        "null_rate": round(float(null_counts.sum() / (len(df) * len(df.columns))), 4),
        "columns_with_nulls": len(null_cols),
        "column_details": {
            col: {
                "count": int(cnt),
                "rate": round(float(cnt / len(df)), 4),
            }
            for col, cnt in null_cols.items()
        },
    }


def _compute_correlations(df: pd.DataFrame) -> dict[str, Any]:
    """计算相关性矩阵"""
    if len(df.columns) < 2:
        return {}

    corr = df.corr()

    # 提取高相关对
    high_corr = []
    for i in range(len(corr.columns)):
        for j in range(i + 1, len(corr.columns)):
            val = corr.iloc[i, j]
            if abs(val) >= 0.7 and not np.isnan(val):
                high_corr.append({
                    "var1": corr.columns[i],
                    "var2": corr.columns[j],
                    "correlation": round(float(val), 4),
                })

    return {
        "matrix": corr.round(4).to_dict(),
        "high_correlations": high_corr,
    }


def _compute_quality_score(profile: dict[str, Any]) -> float:
    """
    计算数据质量评分 (0-1)

    评分维度：
    - 完整性：无缺失值 = 1
    - 唯一性：无重复行 = 1
    """
    missing = profile.get("missing_summary", {})
    null_rate = missing.get("null_rate", 0)
    dup_rate = profile.get("duplicate_rate", 0)

    # 完整性得分
    completeness = 1.0 - null_rate
    # 唯一性得分
    uniqueness = 1.0 - dup_rate

    # 综合得分 (权重: 完整性 60%, 唯一性 40%)
    score = completeness * 0.6 + uniqueness * 0.4
    return float(round(score, 4))


def suggest_column_roles(df: pd.DataFrame, profile: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """
    基于画像推断列的潜在角色

    Args:
        df: 数据
        profile: 已有的画像（可选，避免重复计算）

    Returns:
        列名 → 角色建议的映射
    """
    if profile is None:
        profile = generate_profile(df)

    suggestions: dict[str, dict[str, Any]] = {}

    for col, col_profile in profile.get("columns", {}).items():
        inferred = col_profile.get("inferred_type", "unknown")
        role = "feature"  # 默认
        confidence = 0.5

        if inferred == "id":
            role = "identifier"
            confidence = 0.9
        elif inferred == "datetime":
            role = "time_index"
            confidence = 0.8
        elif inferred == "boolean":
            role = "binary_feature"
            confidence = 0.7
        elif inferred == "categorical":
            n_unique = col_profile.get("unique_count", 0)
            if n_unique == 2:
                role = "binary_feature"
                confidence = 0.8
            else:
                role = "categorical_feature"
                confidence = 0.6
        elif inferred == "numeric":
            skew = col_profile.get("skewness", 0)
            if col_profile.get("likely_id"):
                role = "identifier"
                confidence = 0.7
            elif abs(skew) > 2:
                role = "skewed_numeric"
                confidence = 0.6
            else:
                role = "numeric_feature"
                confidence = 0.6

        suggestions[col] = {
            "role": role,
            "type": inferred,
            "confidence": confidence,
            "reason": f"基于类型推断({inferred})和统计特征",
        }

    return suggestions
