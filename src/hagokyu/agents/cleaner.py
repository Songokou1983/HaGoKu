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
    detect_outliers_isolation_forest,
    littles_mcar_test,
    suggest_cleaning_strategy,
)
from ..tools.data_io import load_data
from .base import DataAgentBase
from .scout import DataContext


class CleanerAgent(DataAgentBase):
    """数据清洗员：统计感知，保守清洗，影响可追溯"""

    def __init__(self, llm_config: LLMConfig, event_bus: EventBus) -> None:
        super().__init__(
            role="Cleaner",
            goal="帮你清洗数据，去掉明显错误，同时告诉你哪些数据可能被改动了",
            backstory=(
                "【你的任务】数据清洗要保守：宁可留一点脏数据，也不要删太多导致结论跑偏。\n\n"
                "【内部指令】\n"
                "1. 检测异常值：用 IQR 和 Isolation Forest 双保险\n"
                "2. 分析缺失机制：用 Little's 检验判断缺失是否随机\n"
                "3. 每次清洗都要记录：影响了多少行、占总数据比例多少\n"
                "4. 清洗后对比分布变化：如果某列均值偏移超过 10%，要警告\n"
                "5. 偏差风险评估：大量数据被删除时，说明这个结论可能不可靠\n\n"
                "【内部指令：影响率阈值】\n"
                "- < 5%：正常清洗，结果可信\n"
                "- 5-10%：注意，清洗后结果参考即可\n"
                "- > 10%：严重警告，结果可信度受限\n"
                "- > 30%：非常可能引入偏差，需要用户在报告中手动确认\n\n"
                "【输出要求】\n"
                "- 报告每一步操作的原因（为什么要删这行、为什么要填这个值）\n"
                "- 任何 >5% 的清洗都要在报告中明确标出\n"
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

        # 尝试加载数据（失败则返回原始数据 + 空报告）
        try:
            self.emit_thinking("加载原始数据...")
            self.emit_tool_call("load_data", data_path)
            df = load_data(data_path)
            self.emit_tool_result(f"{len(df)} 行, {len(df.columns)} 列")
        except Exception as e:
            self.fail("数据加载失败")
            self.emit_event(EventType.AGENT_THINKING, {
                "thought": "⚠️ Cleaner 跳过，使用原始数据继续",
            })
            # 返回原始数据的最小报告
            report = CleaningReport(
                total_rows_original=0,
                total_rows_after=0,
                impact_rate=0.0,
                operations=[],
                warnings=[f"数据加载失败: {e}"],
                distribution_shift={},
                bias_risk="unknown",
                bias_risk_reason="无法加载数据",
                missing_mechanism={},
            )
            return None, report

        try:
            # 2. 异常值检测（IQR + Isolation Forest）
            self.emit_thinking("检测异常值（IQR）...")
            self.emit_tool_call("detect_outliers_iqr")
            outliers_iqr = detect_outliers_iqr(df)
            outlier_summary = {k: v["count"] for k, v in outliers_iqr.items() if v["count"] > 0}
            self.emit_tool_result(
                f"异常列: {outlier_summary}" if outlier_summary else "未检测到显著异常值"
            )

            # Isolation Forest（如果数据足够）— 失败则跳过
            try:
                if len(df) >= 20:
                    self.emit_thinking("检测异常值（Isolation Forest）...")
                    self.emit_tool_call("detect_outliers_isolation_forest")
                    outliers_iso = detect_outliers_isolation_forest(df)
                    if "__global" in outliers_iso:
                        self.emit_tool_result(
                            f"Isolation Forest: {outliers_iso['__global']['count']} 个全局异常行 "
                            f"({outliers_iso['__global']['rate']:.1%})"
                        )
            except Exception as e:
                self.emit_thinking(f"Isolation Forest 跳过: {e}")

            # 3. 缺失机制检测（Little's MCAR 检验 + 逐列 t 检验）
            null_cols = [col for col in df.columns if df[col].isnull().any()]
            mechanisms = {}

            if null_cols:
                # Little's MCAR 整体检验
                try:
                    self.emit_thinking("执行 Little's MCAR 检验...")
                    self.emit_tool_call("littles_mcar_test")
                    mcar_result = littles_mcar_test(df)
                    self.emit_tool_result(mcar_result["conclusion"])
                except Exception as e:
                    self.emit_thinking(f"Little's MCAR 跳过: {e}")

                # 逐列检测
                self.emit_thinking("检测各列缺失机制...")
                for col in null_cols:
                    try:
                        mechanism = detect_missing_mechanism(df, col)
                        mechanisms[col] = mechanism
                        self.emit_tool_result(f"  {col}: {mechanism}")
                    except Exception:
                        mechanisms[col] = "unknown"

            # 4. 生成清洗操作
            if user_operations:
                operations = user_operations
                self.emit_thinking("使用用户指定的清洗操作")
            else:
                operations = self._plan_operations(df, context, mechanisms, outliers_iqr)
                self.emit_thinking(f"计划 {len(operations)} 个清洗操作")

            # 5. 执行清洗（失败则跳过，返回原始数据）
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

        except Exception as e:
            # 清洗失败 → 返回原始数据 + 警告
            self.fail("数据清洗遇到问题")
            self.emit_event(EventType.AGENT_THINKING, {
                "thought": "⚠️ Cleaner 数据清洗遇到问题，继续使用原始数据",
            })
            df_clean = df
            report = CleaningReport(
                total_rows_original=len(df),
                total_rows_after=len(df),
                impact_rate=0.0,
                operations=[],
                warnings=[f"清洗步骤失败: {e}"],
                distribution_shift={},
                bias_risk="high",
                bias_risk_reason=f"清洗异常: {e}",
                missing_mechanism=mechanisms,
            )

        # 6. 报告分布变化
        if report.distribution_shift:
            large_shifts = {k: v for k, v in report.distribution_shift.items() if v > 0.1}
            if large_shifts:
                self.emit_thinking(
                    f"分布变化 > 0.1σ 的列: {list(large_shifts.keys())}"
                )

        # 7. 偏差风险评估
        self.emit_thinking(f"偏差风险: {report.bias_risk} — {report.bias_risk_reason}")

        # 8. 警告
        for warning in report.warnings:
            self.emit_thinking(f"⚠️ {warning}")

        # 9. 补充缺失机制信息
        report.missing_mechanism.update(mechanisms)

        self.complete({
            "rows_original": report.total_rows_original,
            "rows_after": report.total_rows_after,
            "impact_rate": report.impact_rate,
            "operations": len(report.operations),
            "bias_risk": report.bias_risk,
        })

        return df_clean, report

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

        # 异常值处理：对 IQR 检测到异常的列，使用 Winsorize 而非删除
        for col, info in outliers.items():
            if info.get("count", 0) > 0 and info.get("rate", 0) < 0.1:
                # 只对异常率 < 10% 的列做 Winsorize
                operations.append({
                    "column": col,
                    "strategy": "winsorize",
                    "reason": f"IQR 检测到 {info['count']} 个异常值({info['rate']:.1%})，Winsorize 截断优于删除",
                })

        return operations
