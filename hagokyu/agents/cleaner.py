"""HaGoKu Cleaner Agent — 数据清洗员，保守且可追溯"""

from __future__ import annotations

from typing import Any

import pandas as pd

from ..config import LLMConfig
from ..observability.events import EventType
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
                "【你的职责】数据清洗：去掉明显的错误数据，同时追踪每一步改动的影响。\n\n"
                "【你的边界】\n"
                "- 只做清洗，不理解数据含义，不下统计结论\n"
                "- 不确定的数据宁可保留，不要擅改\n"
                "- 大量数据被改动时，必须在报告中说明影响\n\n"
                "【第一步：查记忆】\n"
                "如果 memory 有这个项目的历史清洗偏好（某列用什么策略填充/删除），\n"
                "先查看并复用之前的清洗决策，不要每次重复摸索。\n\n"
                "【第二步：执行清洗】\n"
                "1. 检测异常值：用 IQR 和 Isolation Forest 双保险\n"
                "2. 分析缺失机制：用 Little's 检验判断缺失是否随机\n"
                "3. 每次清洗记录：影响了多少行、占总数据比例多少\n"
                "4. 清洗后对比分布：某列均值偏移超过 10% 要警告\n"
                "5. 偏差风险评估：大量数据被删除时，说明结论可能不可靠\n\n"
                "【影响率阈值】\n"
                "- < 5%：正常清洗，结果可信\n"
                "- 5-10%：注意，结果参考即可\n"
                "- > 10%：严重警告，结果可信度受限\n"
                "- > 30%：引入偏差风险高，需用户在报告中手动确认\n\n"
                "【第三步：写记忆】\n"
                "执行完成后，把本次有效的清洗策略（某列用什么方法）保存到 memory，\n"
                "供下次同项目分析时直接复用相同的清洗决策。\n\n"
                "【输出要求】\n"
                "- 每步操作必须有原因（为什么要删这行、为什么要填这个值）\n"
                "- 任何 >5% 的清洗操作都要在报告中明确标出\n"
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
        phase: str = "full",
    ) -> tuple[pd.DataFrame, CleaningReport] | dict[str, Any]:
        """
        执行数据清洗

        Args:
            data_path: 原始数据路径
            context: Scout 产出的数据上下文
            user_operations: 用户指定的清洗操作（覆盖自动策略）
            impact_warning: 影响率阈值
            phase: "full"=完整执行, "strategy_only"=只检测+计划，返回策略供用户确认

        Returns:
            phase="full": (清洗后的 DataFrame, 清洗报告)
            phase="strategy_only": {
                "status": "cleaner_strategy",
                "n_rows": int,
                "n_cols": int,
                "outliers": dict,         # 异常值检测结果
                "missing_mechanisms": dict, # 缺失机制检测结果
                "operations": list[dict],   # 计划的清洗操作
                "data_quality": str,       # "good"/"medium"/"poor"
            }
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

            # ── phase="strategy_only"：只检测+计划，不执行清洗，返回策略供确认 ──
            if phase == "strategy_only":
                self.emit_thinking("清洗策略已生成，等待用户确认...")
                self.emit_event(EventType.AGENT_COMPLETED, "Cleaner", {
                    "result_summary": f"检测完成：{len(outliers_iqr)} 个异常列，{len(mechanisms)} 个缺失列，{len(operations)} 个计划操作",
                })
                # 数据质量评估
                n_rows = len(df)
                outlier_count = sum(v.get("count", 0) for v in outliers_iqr.values())
                null_count = df.isnull().sum().sum()
                if outlier_count / max(n_rows, 1) > 0.1 or null_count / max(n_rows * len(df.columns), 1) > 0.2:
                    data_quality = "poor"
                elif outlier_count / max(n_rows, 1) > 0.05 or null_count / max(n_rows * len(df.columns), 1) > 0.1:
                    data_quality = "medium"
                else:
                    data_quality = "good"
                return {
                    "status": "cleaner_strategy",
                    "n_rows": n_rows,
                    "n_cols": len(df.columns),
                    "outliers": {k: v for k, v in outliers_iqr.items() if v.get("count", 0) > 0},
                    "missing_mechanisms": mechanisms,
                    "operations": operations,
                    "data_quality": data_quality,
                }

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

        # 🎯 情绪价值：清洗完成，鼓励用户
        if report.bias_risk == "low":
            self.emit_thinking("清洗完成，数据干净，可以放心分析")
        elif report.bias_risk == "medium":
            self.emit_thinking("清洗完成，报告里会标注数据限制，请留意")
        else:
            self.emit_thinking("数据修改较多，分析结论会注明数据限制，供你参考")

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
        variable_roles = context.variable_roles or {}
        target_col = context.target

        for col in df.columns:
            role = variable_roles.get(col, "")

            # Scout 标记为忽略或标识的列，跳过处理
            if role in ("ignore", "identifier"):
                continue

            null_rate = df[col].isnull().mean()
            if null_rate > 0:
                strategy, reason = suggest_cleaning_strategy(
                    df, col, null_rate, mechanisms.get(col)
                )
                # 目标变量列用保守策略，不用 DROP_ROWS
                if col == target_col and strategy.value == "drop_rows":
                    from ..tools.cleaning import CleaningStrategy
                    strategy = CleaningStrategy.FILL_MEDIAN
                    reason = "目标变量不轻易删行，改用中位数填充"
                operations.append({
                    "column": col,
                    "strategy": strategy.value,
                    "reason": reason,
                })

        # 异常值处理：对 IQR 检测到异常的列，使用 Winsorize 而非删除
        for col, info in outliers.items():
            role = variable_roles.get(col, "")
            # 标识列不做异常值处理
            if role == "identifier":
                continue
            if info.get("count", 0) > 0 and info.get("rate", 0) < 0.1:
                # 目标变量用宽松阈值（<5%）而非通用阈值（<10%）
                rate_threshold = 0.05 if col == target_col else 0.1
                if info.get("rate", 0) < rate_threshold:
                    operations.append({
                        "column": col,
                        "strategy": "winsorize",
                        "reason": f"IQR 检测到 {info['count']} 个异常值({info['rate']:.1%})，Winsorize 截断优于删除",
                    })

        return operations
