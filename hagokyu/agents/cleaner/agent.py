"""
Cleaner Agent — 数据清洗员

从 prompt.md 读取角色定义，从 memory.md 读取/保存清洗偏好
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .._scribe.agent import ScribeAgent

import pandas as pd
import yaml

from ...config import LLMConfig
from ...observability.event_bus import EventBus
from ...observability.events import EventType
from ...tools.cleaning import (
    CleaningReport,
    clean_data,
    detect_missing_mechanism,
    detect_outliers_iqr,
    littles_mcar_test,
    suggest_cleaning_strategy,
)
from ...tools.data_io import load_data
from .._interactive import InteractionMixin
from ..types import InteractionResult
from . import knowledge as cleaner_knowledge


class CleanerAgent(InteractionMixin):
    """数据清洗员：保守清洗，影响可追溯"""

    def __init__(
        self,
        llm_config: LLMConfig,
        event_bus: EventBus,
        scribe: "ScribeAgent | None" = None,
        llm_client: Any | None = None,
    ) -> None:
        self.role = "cleaner"
        self.llm_config = llm_config
        self.event_bus = event_bus
        self.scribe = scribe
        self._llm_client = llm_client  # 外部传入的 LLM 客户端（双层策略用）

        self.prompt = self._load_prompt()
        self.memory = self._load_memory()

        # 交互状态
        self._phase = "begin"
        self._context: dict | None = None
        self._data_path: str | None = None
        self._df: pd.DataFrame | None = None
        self._operations: list[dict] = []
        self._report: CleaningReport | None = None

    def _load_prompt(self) -> str:
        path = Path(__file__).parent / "prompt.md"
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    def _load_memory(self) -> dict:
        path = Path(__file__).parent / "memory.md"
        if path.exists():
            content = path.read_text(encoding="utf-8")
            match = re.search(r"```yaml\n(cleaning_preferences:.*?)```", content, re.DOTALL)
            if match:
                try:
                    return yaml.safe_load(match.group(1)) or {}
                except yaml.YAMLError:
                    return {}
        return {"cleaning_preferences": {}}

    def _save_memory(self) -> None:
        path = Path(__file__).parent / "memory.md"
        content = path.read_text(encoding="utf-8")

        prefs_yaml = yaml.dump(
            self.memory.get("cleaning_preferences", {}),
            default_flow_style=False,
            allow_unicode=True
        )

        pattern = r"```yaml\ncleaning_preferences:.*?```"
        if re.search(pattern, content, re.DOTALL):
            content = re.sub(pattern, f"```yaml\ncleaning_preferences:\n{prefs_yaml}```", content, flags=re.DOTALL)
        else:
            content = re.sub(r"cleaning_preferences: \{\}", f"cleaning_preferences:\n{prefs_yaml}", content)

        path.write_text(content, encoding="utf-8")

    def _emit(self, event_type: EventType, data: dict | None = None) -> None:
        self.event_bus.emit(event_type=event_type, agent=self.role, data=data or {})

    # ── 核心逻辑 ────────────────────────────────────────────

    def run(
        self,
        data_path: str,
        context: dict,
        project_id: str | None = None,
        user_operations: list[dict[str, Any]] | None = None,
        impact_warning: float = 0.10,
        phase: str = "full",
    ) -> tuple[pd.DataFrame, CleaningReport, dict]:
        """
        执行数据清洗

        Args:
            data_path: 原始数据路径
            context: Scout 传来的 DataContext
            project_id: 项目 ID
            user_operations: 用户指定的清洗操作（覆盖自动策略）
            impact_warning: 影响率阈值
            phase: "full"=完整执行, "strategy_only"=只检测+计划

        Returns:
            (清洗后的 DataFrame, 清洗报告, 清洗摘要)
        """
        self._emit(EventType.AGENT_STARTED, {"goal": "清洗数据，去掉明显错误"})

        report: CleaningReport | None = None

        # 加载数据
        try:
            self._emit(EventType.AGENT_THINKING, {"thought": "加载原始数据..."})
            df = load_data(data_path)
        except Exception as e:
            self._emit(EventType.AGENT_FAILED, {"error": f"数据加载失败: {e}"})
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
            return pd.DataFrame(), report, {}

        try:
            # 1. 异常值检测
            self._emit(EventType.AGENT_THINKING, {"thought": "检测异常值（IQR）..."})
            outliers_iqr = detect_outliers_iqr(df)
            outlier_summary = {k: v["count"] for k, v in outliers_iqr.items() if v["count"] > 0}
            self._emit(EventType.TOOL_RESULT, {
                "summary": f"异常列: {outlier_summary}" if outlier_summary else "未检测到显著异常值"
            })

            # 2. 缺失机制检测
            null_cols = [col for col in df.columns if df[col].isnull().any()]
            mechanisms = {}
            if null_cols:
                try:
                    self._emit(EventType.AGENT_THINKING, {"thought": "执行 Little's MCAR 检验..."})
                    mcar_result = littles_mcar_test(df)
                    self._emit(EventType.TOOL_RESULT, {"summary": mcar_result["conclusion"]})
                except Exception:
                    pass

                self._emit(EventType.AGENT_THINKING, {"thought": "检测各列缺失机制..."})
                for col in null_cols:
                    try:
                        mechanism = detect_missing_mechanism(df, col)
                        mechanisms[col] = mechanism
                    except Exception:
                        mechanisms[col] = "unknown"

            # 3. 规划清洗操作
            # 检索相关清洗策略经验
            query = f"{context.get('target', '')} {','.join(context.get('features', [])[:5])} 缺失率{len(null_cols)/len(df):.0%}"
            recalled = cleaner_knowledge.recall(query, top_k=2)
            if recalled:
                hint = "参考经验：" + " | ".join(f"{r['metadata'].get('action','?')}({r['similarity']:.0%})" for r in recalled)
                self._emit(EventType.AGENT_THINKING, {"thought": hint})
            # 用户指定操作优先，否则用规划的操作
            if user_operations:
                operations = user_operations
                self._emit(EventType.AGENT_THINKING, {"thought": "使用用户指定的清洗操作"})
            else:
                operations = self._plan_operations(df, context, mechanisms, outliers_iqr)

            # phase="strategy_only"：只检测+计划，返回策略供用户确认
            if phase == "strategy_only":
                strategy_report = CleaningReport(
                    total_rows_original=len(df),
                    total_rows_after=len(df),
                    operations=[],
                    missing_mechanism=mechanisms,
                    impact_rate=0.0,
                    warnings=[],
                    distribution_shift={},
                    bias_risk="low",
                    bias_risk_reason="仅检测，未执行清洗",
                )
                self._emit(EventType.AGENT_COMPLETED, {
                    "result_summary": f"策略生成完成：{len(operations)} 个计划操作"
                })
                return df, strategy_report, {"operations": operations}

            # 4. 执行清洗
            self._emit(EventType.AGENT_THINKING, {"thought": f"执行 {len(operations)} 个清洗操作..."})
            df_clean, report = clean_data(
                df,
                operations=operations if operations else None,
                auto_strategy=not bool(operations),
                impact_warning=impact_warning,
            )

            self._emit(EventType.TOOL_RESULT, {
                "summary": f"清洗完成: {report.total_rows_original} → {report.total_rows_after} 行, 影响率 {report.impact_rate:.1%}"
            })

            # 5. 分布变化警告
            if report.distribution_shift:
                large_shifts = {k: v for k, v in report.distribution_shift.items() if v > 0.1}
                if large_shifts:
                    self._emit(EventType.AGENT_THINKING, {
                        "thought": f"分布变化 > 0.1σ 的列: {list(large_shifts.keys())}"
                    })

            # 6. 偏差风险
            self._emit(EventType.AGENT_THINKING, {
                "thought": f"偏差风险: {report.bias_risk} — {report.bias_risk_reason}"
            })

            # 7. 更新记忆
            self._update_own_memory(operations, project_id)

            # 8. 学习：将清洗策略写入知识库
            self._learn_from_results(df, operations, report, context, project_id)

            # 摘要
            summary = {
                "rows_original": report.total_rows_original,
                "rows_after": report.total_rows_after,
                "impact_rate": report.impact_rate,
                "operations": len(report.operations),
                "bias_risk": report.bias_risk,
            }

            self._emit(EventType.AGENT_COMPLETED, {"result_summary": f"影响率 {report.impact_rate:.1%}"})

            return df_clean, report, summary

        except Exception as e:
            self._emit(EventType.AGENT_FAILED, {"error": str(e)})
            report = CleaningReport(
                total_rows_original=len(df),
                total_rows_after=len(df),
                impact_rate=0.0,
                operations=[],
                warnings=[f"清洗异常: {e}"],
                distribution_shift={},
                bias_risk="high",
                bias_risk_reason=str(e),
                missing_mechanism=mechanisms,
            )
            return df, report, {}

    # ── 交互式接口 ────────────────────────────────────────

    def begin(
        self,
        data_path: str,
        context: dict,
        project_id: str | None = None,
    ) -> InteractionResult:
        """
        开始 Cleaner 交互。

        流程：加载数据 → 检测异常 → 规划策略 → 确认策略 → 执行清洗 → 询问下一步
        """
        self._data_path = data_path
        self._context = context

        self._emit(EventType.AGENT_STARTED, {"goal": "检测异常，规划清洗策略"})

        try:
            # 加载数据
            self._emit(EventType.AGENT_THINKING, {"thought": "加载原始数据..."})
            df = load_data(data_path)
            self._df = df
            self._emit(EventType.TOOL_RESULT, {"summary": f"加载成功: {len(df)} 行, {len(df.columns)} 列"})

            # 异常值检测
            self._emit(EventType.AGENT_THINKING, {"thought": "检测异常值（IQR）..."})
            outliers_iqr = detect_outliers_iqr(df)
            outlier_summary = {k: v for k, v in outliers_iqr.items() if v.get("count", 0) > 0}
            self._emit(EventType.TOOL_RESULT, {
                "summary": f"异常列: {outlier_summary}" if outlier_summary else "未检测到显著异常值"
            })

            # 缺失机制检测
            null_cols = [col for col in df.columns if df[col].isnull().any()]
            mechanisms = {}
            if null_cols:
                try:
                    self._emit(EventType.AGENT_THINKING, {"thought": "执行 Little's MCAR 检验..."})
                    mcar_result = littles_mcar_test(df)
                    self._emit(EventType.TOOL_RESULT, {"summary": mcar_result["conclusion"]})
                except Exception:
                    pass

                self._emit(EventType.AGENT_THINKING, {"thought": "检测各列缺失机制..."})
                for col in null_cols:
                    try:
                        mechanism = detect_missing_mechanism(df, col)
                        mechanisms[col] = mechanism
                    except Exception:
                        mechanisms[col] = "unknown"

            # 检索相关清洗策略经验
            query = f"{context.get('target', '')} {','.join(context.get('features', [])[:5])} 缺失率{len(null_cols)/len(df):.0%}"
            recalled = cleaner_knowledge.recall(query, top_k=2)
            if recalled:
                hint = "参考经验：" + " | ".join(f"{r['metadata'].get('action','?')}({r['similarity']:.0%})" for r in recalled)
                self._emit(EventType.AGENT_THINKING, {"thought": hint})

            # 规划清洗操作
            operations = self._plan_operations(df, context, mechanisms, outliers_iqr)
            self._operations = operations

            self._phase = "confirm_strategy"

            if operations:
                # block，等用户确认策略
                if self.scribe:
                    self.scribe.block_task("cleaner", "等用户确认清洗策略")
                return self._pause(
                    phase="confirm_strategy",
                    message=f"检测到 {len(operations)} 个潜在清洗操作，请确认：",
                    needs_confirmation=True,
                    confirmation_prompt="请逐个确认或修正清洗策略",
                    pending_items=[
                        {
                            "column": op["column"],
                            "strategy": op["strategy"],
                            "reason": op.get("reason", ""),
                        }
                        for op in operations
                    ],
                    data={
                        "operations": operations,
                        "outliers": outlier_summary,
                        "missing_mechanisms": mechanisms,
                        "data_quality": self._assess_quality(df, outlier_summary, null_cols),
                    },
                )
            else:
                # 无需清洗，直接进入下一步
                return self._write_memory_and_ask_next(df, context, [], project_id)

        except Exception as e:
            self._emit(EventType.AGENT_FAILED, {"error": str(e)})
            return self._done("done", f"Cleaner 失败: {e}", {"error": str(e)})

    def respond(
        self,
        user_input: dict,
        project_id: str | None = None,
    ) -> InteractionResult:
        """
        处理用户对清洗策略的确认响应。

        user_input 格式:
          {
            "confirmed": [{"column": "Inc1", "strategy": "fill_median"}, ...],
            "corrected": [{"column": "Inc1", "strategy": "drop_rows"}, ...],
          }
        """
        if self._phase != "confirm_strategy" or self._df is None:
            return self._done("done", "阶段错误，请重新开始", {})

        confirmed_ops = user_input.get("confirmed", [])
        corrected_ops = user_input.get("corrected", [])

        # 用用户确认的操作（合并 confirmed + corrected）
        final_ops = {}
        for op in confirmed_ops + corrected_ops:
            col = op.get("column")
            strategy = op.get("strategy")
            if col and strategy:
                final_ops[col] = strategy

        # 解除 block
        if self.scribe:
            self.scribe.unblock_task("cleaner")

        df = self._df
        context = self._context or {}

        # 执行清洗
        self._emit(EventType.AGENT_STARTED, {"goal": "执行清洗操作"})
        self._emit(EventType.AGENT_THINKING, {"thought": f"执行 {len(final_ops)} 个清洗操作..."})

        df_clean, report = clean_data(
            df,
            operations=[{"column": k, "strategy": v} for k, v in final_ops.items()] if final_ops else None,
            auto_strategy=not bool(final_ops),
            impact_warning=0.10,
        )

        self._df = df_clean
        self._report = report

        self._emit(EventType.TOOL_RESULT, {
            "summary": f"清洗完成: {report.total_rows_original} → {report.total_rows_after} 行, 影响率 {report.impact_rate:.1%}"
        })

        # 偏差风险提示
        if report.bias_risk == "high":
            self._emit(EventType.AGENT_THINKING, {
                "thought": f"⚠️ 偏差风险: {report.bias_risk_reason}"
            })

        # 更新记忆
        ops_for_memory = [{"column": k, "strategy": v} for k, v in final_ops.items()]
        self._update_own_memory(ops_for_memory, project_id)
        self._learn_from_results(df, ops_for_memory, report, context, project_id)

        return self._write_memory_and_ask_next(df_clean, context, ops_for_memory, project_id)

    def _write_memory_and_ask_next(
        self,
        df: pd.DataFrame,
        context: dict,
        operations: list[dict],
        project_id: str | None,
    ) -> InteractionResult:
        """写记忆后询问用户是否进入分析阶段"""
        self._phase = "next_step"

        summary = (
            f"已清洗 {len(operations)} 个字段，"
            f"影响率 {self._report.impact_rate:.1%}" if self._report else ""
        )

        # block，等用户确认进入下一步
        if self.scribe:
            self.scribe.block_task("cleaner", "等用户确认进入分析阶段")
        self._emit(EventType.AGENT_COMPLETED, {"result_summary": summary})

        return self._pause(
            phase="next_step",
            message=summary + "\n\n建议进入「分析阶段」，是否确认？",
            actions=["进入分析", "重新清洗", "结束分析"],
            pending_items=[],
            data={
                "rows_original": self._report.total_rows_original if self._report else len(df),
                "rows_after": self._report.total_rows_after if self._report else len(df),
                "impact_rate": self._report.impact_rate if self._report else 0.0,
                "operations_count": len(operations),
                "bias_risk": self._report.bias_risk if self._report else "unknown",
            },
        )

    def _assess_quality(self, df: pd.DataFrame, outliers: dict, null_cols: list) -> str:
        n_rows = len(df)
        outlier_count = sum(v.get("count", 0) for v in outliers.values())
        null_count = df.isnull().sum().sum()

        if outlier_count / max(n_rows, 1) > 0.1 or null_count / max(n_rows * len(df.columns), 1) > 0.2:
            return "poor"
        elif outlier_count / max(n_rows, 1) > 0.05 or null_count / max(n_rows * len(df.columns), 1) > 0.1:
            return "medium"
        return "good"

    def _plan_operations(
        self,
        df: pd.DataFrame,
        context: dict,
        mechanisms: dict,
        outliers: dict,
    ) -> list[dict]:
        """规划清洗操作"""
        operations = []
        variable_roles = context.get("variable_roles", {})
        target_col = context.get("target")

        # 从记忆加载该项目的清洗偏好
        project_prefs = self.memory.get("cleaning_preferences", {})

        for col in df.columns:
            role = variable_roles.get(col, "")

            if role in ("ignore", "identifier"):
                continue

            # 缺失值处理
            null_rate = df[col].isnull().mean()
            if null_rate > 0:
                # 优先用记忆中的偏好
                if project_prefs and col in project_prefs:
                    strategy = project_prefs[col]
                    reason = f"历史偏好: {strategy}"
                else:
                    strategy, reason = suggest_cleaning_strategy(
                        df, col, null_rate, mechanisms.get(col)
                    )

                # 目标变量用保守策略
                if col == target_col and strategy.value == "drop_rows":
                    from ...tools.cleaning import CleaningStrategy
                    strategy = CleaningStrategy.FILL_MEDIAN
                    reason = "目标变量不轻易删行，改用中位数填充"

                operations.append({
                    "column": col,
                    "strategy": strategy.value,
                    "reason": reason,
                })

        # 异常值处理
        for col, info in outliers.items():
            role = variable_roles.get(col, "")
            if role == "identifier":
                continue
            if info.get("count", 0) > 0 and info.get("rate", 0) < 0.1:
                rate_threshold = 0.05 if col == target_col else 0.1
                if info.get("rate", 0) < rate_threshold:
                    operations.append({
                        "column": col,
                        "strategy": "winsorize",
                        "reason": f"IQR 检测到 {info['count']} 个异常值({info['rate']:.1%})，Winsorize 截断优于删除",
                    })

        return operations

    def _update_own_memory(self, operations: list[dict], project_id: str | None) -> None:
        """更新清洗偏好记忆"""
        if not project_id:
            return

        if "cleaning_preferences" not in self.memory:
            self.memory["cleaning_preferences"] = {}

        for op in operations:
            col = op.get("column")
            strategy = op.get("strategy")
            if col and strategy:
                if project_id not in self.memory["cleaning_preferences"]:
                    self.memory["cleaning_preferences"][project_id] = {}
                self.memory["cleaning_preferences"][project_id][col] = strategy

        self._save_memory()

    def _learn_from_results(
        self,
        df: pd.DataFrame,
        operations: list[dict],
        report,
        context: dict,
        project_id: str | None,
    ) -> None:
        """将清洗策略选择写入知识库"""
        if not operations or not project_id:
            return

        for op in operations:
            col = op.get("column", "")
            strategy = op.get("strategy", "")
            if not col or not strategy:
                continue
            condition = f"列={col} {op.get('method', '')}"
            # 检查是否已有相似条目
            existing = cleaner_knowledge.recall(condition, top_k=1)
            if existing and existing[0]["similarity"] > 0.85:
                continue
            risk = "low" if op.get("impact", 0) < 0.05 else "medium"
            cleaner_knowledge.learn(
                condition=condition,
                action=strategy,
                risk=risk,
                tags=["清洗策略", col, strategy],
                metadata={"project": project_id, "column": col, "strategy": strategy},
            )

    def get_strategy_summary(self, data_path: str, context: dict) -> dict:
        """
        只检测+规划，不执行清洗。
        返回策略供用户确认。
        """
        df = load_data(data_path)

        outliers_iqr = detect_outliers_iqr(df)
        null_cols = [col for col in df.columns if df[col].isnull().any()]
        mechanisms = {}
        for col in null_cols:
            try:
                mechanisms[col] = detect_missing_mechanism(df, col)
            except Exception:
                mechanisms[col] = "unknown"

        operations = self._plan_operations(df, context, mechanisms, outliers_iqr)

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
