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
from ...config import CleaningConfig
from ...tools.cleaning import (
    CleaningReport,
    clean_data,
    detect_missing_mechanism,
    detect_outliers_iqr,
    littles_mcar_test,
)

# 模块级配置
_cconfig = CleaningConfig()
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
        impact_warning: float | None = None,
        phase: str = "full",
        *,
        emit_completed: bool = True,
    ) -> tuple[pd.DataFrame, pd.DataFrame, CleaningReport, dict]:
        """
        执行数据清洗

        Args:
            data_path: 原始数据路径
            context: Scout 传来的 DataContext
            project_id: 项目 ID
            user_operations: 用户指定的清洗操作（覆盖自动策略）
            impact_warning: 影响率阈值
            phase: "full"=完整执行, "strategy_only"=只检测+计划
            emit_completed: 为 False 时不发 AGENT_COMPLETED（编排层在用户确认清洗方案后再发）。

        Returns:
            (原始 DataFrame, 清洗后 DataFrame, 清洗报告, 清洗摘要)
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
            return pd.DataFrame(), pd.DataFrame(), report, {}

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
                return df, df, strategy_report, {"operations": operations}

            # 4. 执行清洗
            self._emit(EventType.AGENT_THINKING, {"thought": f"执行 {len(operations)} 个清洗操作..."})
            df_clean, report = clean_data(
                df,
                operations=operations if operations else None,
                impact_warning=impact_warning if impact_warning is not None else _cconfig.impact_warning_threshold,
            )

            self._emit(EventType.TOOL_RESULT, {
                "summary": f"清洗完成: {report.total_rows_original} → {report.total_rows_after} 行, 影响率 {report.impact_rate:.1%}"
            })

            # 5. 分布变化警告
            if report.distribution_shift:
                sigma = _cconfig.large_shift_sigma
                large_shifts = {k: v for k, v in report.distribution_shift.items() if v > sigma}
                if large_shifts:
                    self._emit(EventType.AGENT_THINKING, {
                        "thought": f"分布变化 > {sigma}σ 的列: {list(large_shifts.keys())}"
                    })

            # 6. 偏差风险
            self._emit(EventType.AGENT_THINKING, {
                "thought": f"偏差风险: {report.bias_risk} — {report.bias_risk_reason}"
            })

            # 7. 更新记忆
            self._update_own_memory(operations, project_id)

            # 8. 学习：将清洗策略写入知识库
            self._learn_from_results(operations, context, project_id)

            # 摘要
            summary = {
                "rows_original": report.total_rows_original,
                "rows_after": report.total_rows_after,
                "impact_rate": report.impact_rate,
                "operations": len(report.operations),
                "bias_risk": report.bias_risk,
            }

            if emit_completed:
                self._emit(EventType.AGENT_COMPLETED, {"result_summary": f"影响率 {report.impact_rate:.1%}"})

            return df, df_clean, report, summary

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
            return df, df, report, {}

    # ── 交互式接口 ────────────────────────────────────────

    def begin(  # type: ignore[override]
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

    def respond(  # type: ignore[override]
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
            impact_warning=_cconfig.impact_warning_threshold,
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
        self._learn_from_results(ops_for_memory, context, project_id)

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

    def _assess_quality(self, df: pd.DataFrame, outliers: dict, null_cols: list) -> dict[str, Any]:
        """返回原始质量统计数据，评级由 LLM 在清洗规划时结合业务上下文给出。"""
        n_rows = len(df)
        outlier_count = sum(v.get("count", 0) for v in outliers.values())
        null_count = df.isnull().sum().sum()
        outlier_rate = outlier_count / max(n_rows, 1)
        null_rate = null_count / max(n_rows * len(df.columns), 1)

        return {
            "n_rows": n_rows,
            "n_columns": len(df.columns),
            "outlier_count": outlier_count,
            "outlier_rate": round(outlier_rate, 4),
            "null_count": int(null_count),
            "null_rate": round(null_rate, 4),
        }

    def _plan_operations(
        self,
        df: pd.DataFrame,
        context: dict,
        mechanisms: dict,
        outliers: dict,
    ) -> list[dict]:
        """规划清洗操作 — LLM 原生模式

        LLM 不可达或返回无效结果时，直接抛出异常。
        框架不做硬编码兜底：LLM 有问题就去解决 LLM 的问题。
        """
        llm_ops = self._plan_via_llm(df, context, mechanisms, outliers)
        if llm_ops:
            self._emit(EventType.AGENT_THINKING, {
                "thought": f"LLM 生成了 {len(llm_ops)} 个清洗操作"
            })
            return llm_ops
        raise RuntimeError(
            "Cleaner LLM 清洗规划失败：LLM 未返回任何有效的清洗操作。"
            "请检查 LLM 配置和 API 连通性，解决后再重试。"
        )

    # ==== CHANNEL ZONE: 禁止正则/if-else 语义分支 ====
    def _plan_via_llm(
        self,
        df: pd.DataFrame,
        context: dict,
        mechanisms: dict,
        outliers: dict,
    ) -> list[dict] | None:
        """LLM 原生清洗规划：让 LLM 直接看数据并决定清洗策略

        对标 Scout._infer_all_semantics() 的 LLM 原生模式：
        - 构建每列数据画像 + 字段语义 + 分析目标
        - 发送给 LLM
        - 解析 JSON 输出
        """
        from ...llm.client import create_raw_client

        # 构建每列的画像摘要
        column_list: list[dict] = []
        for col in df.columns:
            series = df[col]
            n_total = len(series)
            n_null = int(series.isna().sum())
            null_pct = n_null / n_total if n_total > 0 else 0

            col_info: dict = {
                "name": col,
                "dtype": str(series.dtype),
                "n_total": n_total,
                "n_null": n_null,
                "null_pct": round(null_pct, 4),
            }

            # 字段语义（来自 Scout）
            variable_roles = context.get("variable_roles", {})
            col_info["role"] = variable_roles.get(col, "unknown")
            col_info["description"] = context.get("column_descriptions", {}).get(col, "")

            # 数值列：分位数 + 分布
            if pd.api.types.is_numeric_dtype(series):
                non_null = series.dropna()
                if len(non_null) > 0:
                    col_info.update({
                        "min": float(non_null.min()) if hasattr(non_null, "min") else None,
                        "q25": float(non_null.quantile(0.25)),
                        "median": float(non_null.median()),
                        "q75": float(non_null.quantile(0.75)),
                        "max": float(non_null.max()) if hasattr(non_null, "max") else None,
                        "mean": round(float(non_null.mean()), 4),
                    })
            # 缺失机制
            mech = mechanisms.get(col)
            if mech:
                col_info["missing_mechanism"] = mech if isinstance(mech, str) else str(mech)

            # 样本值
            try:
                sample_vals = df[col].dropna().unique()[:3]
                col_info["sample_values"] = [str(v) for v in sample_vals]
            except Exception:
                pass

            column_list.append(col_info)

        # 提取分析目标
        analysis_goal = context.get("analysis_goal", "")
        query = context.get("query", "")
        target_col = context.get("target", "")

        payload = {
            "analysis_goal": analysis_goal or query or "未指定",
            "target_column": target_col,
            "n_rows": len(df),
            "n_cols": len(df.columns),
            "columns": column_list,
        }

        system_prompt = (
            "你是专业数据清洗员。你收到的每列数据画像仅包含原始统计量（count/min/q25/median/q75/max/mean/null_rate），"
            "没有任何预判信息。你需要自行决策：\n"
            "\n"
            "核心原则：\n"
            "1. 清洗策略必须匹配分析目标：\n"
            "   - 看分布/画像 → 不截断极端值，极端值就是用户想看的\n"
            "   - 算均值/比较 → 温和截断极端值，保护均值不被拉偏\n"
            "   - 预测建模 → 保守处理特征列，目标变量绝对不碰\n"
            "   - 找高价值/异常 → 极端值就是答案，不做截断\n"
            "2. 自行判断列的语义边界（不要依赖代码预判，数据里没有'known_range'字段）：\n"
            "   - 比较 min/max 与样本值判断是否为评分列（如 1-5 / 1-10 / 0-100 百分比）→ 是评分则 skip\n"
            "   - 比较 q75 与 max 的差距判断有无极端值（如 max > q75 * 3 可能有极端值，max > q75 * 10 几乎确定是异常）\n"
            "   - 比较 mean 与 median 的偏离判断分布偏态\n"
            "3. 标识列(identifier)、分组列 — 不处理\n"
            "4. 缺失率 > 50% → 建议标记缺失（fill_mcar），不要盲目删行\n"
            "5. 缺失率 < 1% 且非目标变量 → 可删行\n"
            "6. 目标变量绝对不删行、不截断 → skip\n"
            "\n"
            "输出一个 JSON 对象，字段 `operations` 为数组，仅包含需要处理的列。每项包含：\n"
            "  - column: 列名（照抄）\n"
            "  - strategy: 清洗策略（winsorize / drop_rows / fill_median / fill_mean / fill_mode / fill_mcar / skip）\n"
            "  - reason: 业务理由（面向用户的自然语言，禁止出现'IQR''p值'等统计术语，要说'最大值为中位数的15倍，存在极端偏离'这样）\n"
            "  - impact_estimate: 预估影响行数或比例（字符串，如'约5%'）\n"
            "\n"
            "不需要清洗的列不要出现在 operations 中。"
        )

        client = create_raw_client(self.llm_config)
        import json as _json
        try:
            response = client.chat.completions.create(
                model=self.llm_config.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"请分析以下数据集的清洗需求：\n```json\n{_json.dumps(payload, ensure_ascii=False, default=str)}\n```"},
                ],
                temperature=0.0,
                max_tokens=4096,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content or ""
        except Exception as e:
            raise RuntimeError(f"Cleaner LLM 清洗规划失败：LLM 不可达。原始错误: {e}") from e

        try:
            result = _json.loads(raw)
        except _json.JSONDecodeError:
            try:
                cleaned = raw.strip()
                cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
                cleaned = re.sub(r"\s*```\s*$", "", cleaned)
                cleaned = cleaned.strip()
                result = _json.loads(cleaned)
            except _json.JSONDecodeError:
                try:
                    match = re.search(r"\{.*\}", raw, re.DOTALL)
                    if match:
                        result = _json.loads(match.group())
                    else:
                        raise
                except Exception:
                    raise ValueError(
                        f"Cleaner LLM 返回的格式无法解析为 JSON。原始内容前 500 字: {raw[:500]}"
                    )

        operations = result.get("operations") or []
        if not operations:
            return None

        # 标准化并校验
        valid_strategies = {"winsorize", "drop_rows", "fill_median", "fill_mean", "fill_mode", "fill_mcar", "skip"}
        valid_columns = set(df.columns)
        normalized: list[dict] = []
        for op in operations:
            col = op.get("column", "")
            if not col or col not in valid_columns:
                continue
            strategy = op.get("strategy", "skip")
            if strategy not in valid_strategies:
                strategy = "skip"
            reason = op.get("reason", "")
            if not reason or not isinstance(reason, str):
                reason = f"对 {col} 列执行 {strategy}"
            normalized.append({
                "column": col,
                "strategy": strategy,
                "reason": reason,
                "impact_estimate": op.get("impact_estimate", ""),
            })

        return normalized if normalized else None

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
        operations: list[dict],
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
            cleaner_knowledge.learn(
                condition=condition,
                action=strategy,
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

        # 数据质量统计（由 LLM 解读，代码不做评级）
        n_rows = len(df)
        outlier_count = sum(v.get("count", 0) for v in outliers_iqr.values())
        null_count = df.isnull().sum().sum()

        return {
            "status": "cleaner_strategy",
            "n_rows": n_rows,
            "n_cols": len(df.columns),
            "outliers": {k: v for k, v in outliers_iqr.items() if v.get("count", 0) > 0},
            "missing_mechanisms": mechanisms,
            "operations": operations,
            "data_quality": {
                "outlier_rate": round(outlier_count / max(n_rows, 1), 4),
                "null_rate": round(null_count / max(n_rows * len(df.columns), 1), 4),
                "n_rows": n_rows,
                "n_columns": len(df.columns),
            },
        }
