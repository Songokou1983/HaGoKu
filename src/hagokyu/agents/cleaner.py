"""HaGoKu Cleaner Agent — 数据清洗员，保守且可追溯"""

from __future__ import annotations

from typing import Any

import pandas as pd

from ..config import LLMConfig
from ..observability.event_bus import EventBus
from ..tools.cleaning import (
    CleaningReport,
    clean_data,
    detect_missing_mechanism,
    detect_outliers_iqr,
    suggest_cleaning_strategy,
)
from ..tools.data_io import get_data_info, load_data, save_data
from .base import DataAgentBase
from .scout import DataContext


class CleanerAgent(DataAgentBase):
    """数据清洗员：保守清洗，影响可追溯"""

    def __init__(self, llm_config: LLMConfig, event_bus: EventBus) -> None:
        super().__init__(
            role="Cleaner",
            goal="清洗数据，保守操作，影响可追溯",
            backstory=(
                "你是数据清洗员。你的原则是：宁可保留脏数据，也不要过度清洗导致偏差。"
                "每次操作都必须记录影响：影响了多少行、多少列、占总体比例。"
                "当清洗影响超过 10% 时，你会发出警告。"
                "你了解 MCAR/MAR/MNAR，会根据缺失机制选择合适的策略。"
            ),
            llm_config=llm_config,
            event_bus=event_bus,
        )

    def run(
        self,
        data_path: str,
        context: DataContext,
        *,
        user_operations: list[dict[str, Any]] | None = None,
        impact_warning: float = 0.10,
    ) -> tuple[pd.DataFrame, CleaningReport]:
        """
        执行数据清洗

        Args:
            data_path: 原始数据路径
            context: Scout 产出的数据上下文
            user_operations: 用户指定的清洗操作（覆盖自动策略）
            impact_warning: 影响率阈值

        Returns:
            (清洗后的 DataFrame, 清洗报告)
        """
        self.start()

        try:
            # 1. 加载数据
            self.emit_thinking("加载原始数据...")
            self.emit_tool_call("load_data", data_path)
            df = load_data(data_path)
            self.emit_tool_result(f"{len(df)} 行, {len(df.columns)} 列")

            # 2. 异常值检测
            self.emit_thinking("检测异常值...")
            self.emit_tool_call("detect_outliers_iqr")
            outliers = detect_outliers_iqr(df)
            outlier_summary = {k: v["count"] for k, v in outliers.items() if v["count"] > 0}
            self.emit_tool_result(
                f"异常列: {outlier_summary}" if outlier_summary else "未检测到显著异常值"
            )

            # 3. 缺失机制检测
            self.emit_thinking("检测缺失机制...")
            null_cols = [col for col in df.columns if df[col].isnull().any()]
            mechanisms = {}
            for col in null_cols:
                mechanism = detect_missing_mechanism(df, col)
                mechanisms[col] = mechanism
                self.emit_tool_result(f"  {col}: {mechanism}")

            # 4. 生成清洗操作
            if user_operations:
                operations = user_operations
                self.emit_thinking("使用用户指定的清洗操作")
            else:
                operations = self._plan_operations(df, context, mechanisms, outliers)
                self.emit_thinking(f"计划 {len(operations)} 个清洗操作")

            # 5. 执行清洗
            self.emit_thinking("执行数据清洗...")
            self.emit_tool_call("clean_data", f"{len(operations)} 个操作")
            df_clean, report = clean_data(
                df,
                operations=operations if operations else None,
                auto_strategy=not bool(operations),
                impact_warning=impact_warning,
            )
            self.emit_tool_result(
                f"清洗完成: {report.total_rows_original} → {report.total_rows_after} 行, "
                f"影响率 {report.impact_rate:.1%}"
            )

            # 6. 警告
            for warning in report.warnings:
                self.emit_thinking(f"⚠️ {warning}")

            # 7. 补充缺失机制信息
            report.missing_mechanism.update(mechanisms)

            self.complete({
                "rows_original": report.total_rows_original,
                "rows_after": report.total_rows_after,
                "impact_rate": report.impact_rate,
                "operations": len(report.operations),
            })

            return df_clean, report

        except Exception as e:
            self.fail(str(e))
            raise

    def _plan_operations(
        self,
        df: pd.DataFrame,
        context: DataContext,
        mechanisms: dict[str, str],
        outliers: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """基于上下文和检测结果规划清洗操作"""
        operations = []

        for col in df.columns:
            null_rate = df[col].isnull().mean()
            if null_rate > 0:
                strategy, reason = suggest_cleaning_strategy(
                    df, col, null_rate, mechanisms.get(col)
                )
                operations.append({
                    "column": col,
                    "strategy": strategy.value,
                    "reason": reason,
                })

        return operations
