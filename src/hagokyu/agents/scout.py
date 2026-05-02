"""HaGoKu Scout Agent — 数据侦察员，理解数据上下文，不猜，问"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd

from ..config import LLMConfig
from ..observability.event_bus import EventBus
from ..observability.events import EventType
from ..tools.data_io import get_data_info, load_data
from ..tools.profiling import generate_profile, suggest_column_roles
from .base import DataAgentBase


class SemanticType(Enum):
    """列语义类型"""

    ID = "id"
    NUMERIC = "numeric"
    CATEGORICAL = "categorical"
    ORDINAL = "ordinal"
    BOOLEAN = "boolean"
    DATETIME = "datetime"
    TARGET = "target"
    TEXT = "text"
    UNKNOWN = "unknown"


@dataclass
class ColumnSemantic:
    """列语义推断结果"""

    column_name: str
    inferred_type: SemanticType
    confidence: float  # 0-1
    evidence: str  # 推断依据
    needs_user_input: bool = False
    suggested_role: str = "feature"  # feature / target / identifier / time_index
    user_override: str | None = None  # 用户修正后的类型

    def to_dict(self) -> dict[str, Any]:
        return {
            "column_name": self.column_name,
            "inferred_type": self.inferred_type.value,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "needs_user_input": self.needs_user_input,
            "suggested_role": self.suggested_role,
        }


@dataclass
class DataContext:
    """Scout 产出的数据上下文"""

    # 基础信息
    data_path: str
    n_rows: int
    n_cols: int
    column_semantics: list[ColumnSemantic] = field(default_factory=list)
    quality_score: float = 0.0
    missing_summary: dict[str, Any] = field(default_factory=dict)
    correlation_highlights: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # 分析上下文（Scout 的真正价值，来自 PROJECT.md 设计）
    target: str | None = None
    features: list[str] = field(default_factory=list)
    confounders: list[str] = field(default_factory=list)
    time_column: str | None = None
    group_columns: list[str] = field(default_factory=list)
    column_descriptions: dict[str, str] = field(default_factory=dict)
    units: dict[str, str] = field(default_factory=dict)
    missing_patterns: dict[str, str] = field(default_factory=dict)
    outlier_candidates: list[str] = field(default_factory=list)
    variable_roles: dict[str, str] = field(default_factory=dict)
    suggested_analyses: list[str] = field(default_factory=list)
    user_constraints: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "data_path": self.data_path,
            "n_rows": self.n_rows,
            "n_cols": self.n_cols,
            "column_semantics": [s.to_dict() for s in self.column_semantics],
            "quality_score": self.quality_score,
            "missing_summary": self.missing_summary,
            "correlation_highlights": self.correlation_highlights,
            "warnings": self.warnings,
            "target": self.target,
            "features": self.features,
            "confounders": self.confounders,
            "time_column": self.time_column,
            "group_columns": self.group_columns,
            "column_descriptions": self.column_descriptions,
            "units": self.units,
            "missing_patterns": self.missing_patterns,
            "outlier_candidates": self.outlier_candidates,
            "variable_roles": self.variable_roles,
            "suggested_analyses": self.suggested_analyses,
            "user_constraints": self.user_constraints,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DataContext:
        """从 to_dict() 的输出重建 DataContext，正确处理 column_semantics 反序列化"""
        data = data.copy()
        # 反序列化 column_semantics：dict → ColumnSemantic
        raw_sems = data.pop("column_semantics", [])
        column_semantics = []
        for s in raw_sems:
            if isinstance(s, ColumnSemantic):
                column_semantics.append(s)
            elif isinstance(s, dict):
                inferred_type = s.get("inferred_type", "unknown")
                if isinstance(inferred_type, str):
                    try:
                        inferred_type = SemanticType(inferred_type)
                    except ValueError:
                        inferred_type = SemanticType.UNKNOWN
                column_semantics.append(ColumnSemantic(
                    column_name=s.get("column_name", ""),
                    inferred_type=inferred_type,
                    confidence=s.get("confidence", 0.0),
                    evidence=s.get("evidence", ""),
                    needs_user_input=s.get("needs_user_input", False),
                    suggested_role=s.get("suggested_role", "feature"),
                    user_override=s.get("user_override"),
                ))
        return cls(column_semantics=column_semantics, **data)

    def get_uncertain_columns(self) -> list[ColumnSemantic]:
        """获取需要用户确认的列"""
        return [s for s in self.column_semantics if s.needs_user_input]

    def get_target_candidates(self) -> list[ColumnSemantic]:
        """获取可能的目标变量"""
        return [s for s in self.column_semantics if s.suggested_role == "target"]

    def derive_from_column_semantics(self) -> None:
        """从 column_semantics 推导 target/features/confounders/variable_roles 等"""
        features = []
        confounders = []
        variable_roles = {}

        for sem in self.column_semantics:
            role = sem.suggested_role
            col = sem.column_name
            variable_roles[col] = role

            # 跳过忽略列和标识列
            if role in ("ignore", "identifier"):
                continue

            # 目标变量
            if role == "target" and not self.target:
                self.target = col
                continue

            # 混淆变量
            if role == "control":
                confounders.append(col)
                continue

            # 时间列
            if role in ("time_index", "time") and not self.time_column:
                self.time_column = col
                continue

            # 分组列
            if role == "group":
                if col not in self.group_columns:
                    self.group_columns.append(col)
                continue

            # 其他作为特征
            features.append(col)

        # 只在没设置过时才覆盖
        if not self.features:
            self.features = features
        if not self.confounders:
            self.confounders = confounders
        if not self.variable_roles:
            self.variable_roles = variable_roles


class ScoutAgent(DataAgentBase):
    """数据侦察员：理解数据上下文，不猜，问"""

    def __init__(self, llm_config: LLMConfig, event_bus: EventBus) -> None:
        super().__init__(
            role="Scout",
            goal="让你快速搞懂这份数据：有哪些列、各列什么意思、数据质量怎样",
            backstory=(
                "【你的任务】拿到数据后，快速弄清楚这份数据长什么样。\n\n"
                "【内部指令】\n"
                "1. 推断每列的语义类型：数值/分类/日期/ID/文本\n"
                "2. 识别质量信号：缺失率、重复率、异常值\n"
                "3. 找出最有分析价值的列（目标变量候选）\n"
                "4. 不确定的字段，标注置信度（高/中/低），不要瞎猜\n"
                "5. 如果用户的 query 提到了某个指标，优先把它标记为目标变量\n\n"
                "【内部指令：置信度标准】\n"
                "- 高置信度：数据类型清晰、样本量大（>80%）\n"
                "- 中置信度：数据类型有一定歧义或样本量中等\n"
                "- 低置信度：类型模糊、样本量小（<30%）、缺失率高（>50%）\n\n"
                "【输出要求】\n"
                "- 所有推断必须有依据（evidence 字段说明判断理由）\n"
                "- 有歧义的地方要明确标注，不要模糊处理\n"
            ),
            llm_config=llm_config,
            event_bus=event_bus,
        )

    def run(
        self,
        data_path: str,
        query: str = "",
        project_id: str | None = None,
        memory: Any | None = None,
    ) -> DataContext:
        """
        执行数据侦察

        Args:
            data_path: 数据文件路径
            query: 用户的分析问题（帮助推断目标变量）
            project_id: 项目 ID
            memory: MemoryManager 实例（用于应用记忆）

        Returns:
            DataContext 数据上下文
        """
        self.start()

        try:
            # 1. 加载数据（尝试多种方式）
            self.emit_thinking(f"正在加载数据: {data_path}")
            self.emit_tool_call("load_data", data_path)
            df = load_data(data_path)
            self.emit_tool_result(f"加载成功: {len(df)} 行, {len(df.columns)} 列")

        except FileNotFoundError:
            # 文件不存在 → 尝试常见扩展名
            from pathlib import Path
            p = Path(data_path)
            suffixes = ["", ".csv", ".parquet", ".xlsx", ".json"]
            found = None
            for suf in suffixes:
                candidate = p.parent / (p.stem + suf)
                if candidate.exists():
                    found = str(candidate)
                    break
            if found:
                self.emit_thinking(f"文件不存在，尝试 {found}")
                self.emit_tool_call("load_data", found)
                df = load_data(found)
                self.emit_tool_result(f"加载成功: {len(df)} 行, {len(df.columns)} 列")
                data_path = found
            else:
                self.fail("数据文件未找到")
                # 返回空 context，不阻断 pipeline
                return DataContext(
                    data_path=data_path,
                    n_rows=0,
                    n_cols=0,
                    column_semantics=[],
                    quality_score=0.0,
                )

        except ValueError:
            # 格式不支持 → 返回空 context
            self.fail("不支持的数据文件格式")
            return DataContext(
                data_path=data_path,
                n_rows=0,
                n_cols=0,
                column_semantics=[],
                quality_score=0.0,
            )

        try:
            # 2. 数据画像（失败则用最小 profile）
            self.emit_thinking("生成数据画像...")
            self.emit_tool_call("generate_profile")
            profile = generate_profile(df)
            n_cols_with_nulls = profile['missing_summary'].get('columns_with_nulls', 0)
            if not isinstance(n_cols_with_nulls, int):
                n_cols_with_nulls = len(n_cols_with_nulls)
            self.emit_tool_result(
                f"质量={profile['quality_score']}, "
                f"缺失列={n_cols_with_nulls}"
            )

        except Exception as e:
            # 画像失败 → 用最小化指标
            self.emit_thinking(f"数据画像失败（{e}），使用最小推断")
            profile = {
                "quality_score": 0.5,
                "missing_summary": {
                    "columns_with_nulls": 0,
                    "column_details": {},
                    "null_rate": 0.0,
                },
                "duplicate_rate": 0.0,
                "correlations": {},
            }

        try:
            # 3. 字段语义推断
            self.emit_thinking("推断字段语义...")
            column_semantics = self._infer_all_semantics(df, query)

            # 4. 构建数据上下文
            context = DataContext(
                data_path=data_path,
                n_rows=len(df),
                n_cols=len(df.columns),
                column_semantics=column_semantics,
                quality_score=profile["quality_score"],
                missing_summary=profile["missing_summary"],
                correlation_highlights=profile.get("correlations", {}).get("high_correlations", []),
            )

            # 5. 应用记忆：自动修正已知字段语义
            if memory and project_id:
                n_before = len(context.get_uncertain_columns())
                memory.apply_to_context(project_id, context)
                n_after = len(context.get_uncertain_columns())
                if n_before > n_after:
                    self.emit_thinking(f"从记忆中应用了 {n_before - n_after} 个字段修正")

            # 6. 推导派生字段
            context.derive_from_column_semantics()

            # 7. 警告
            if profile["duplicate_rate"] > 0.05:
                context.warnings.append(f"重复行率 {profile['duplicate_rate']:.1%} 较高")
            if profile["missing_summary"].get("null_rate", 0) > 0.1:
                context.warnings.append(f"缺失率 {profile['missing_summary']['null_rate']:.1%} 较高")

            # 8. 如果有用户输入请求
            uncertain = context.get_uncertain_columns()
            if uncertain:
                for col_sem in uncertain:
                    self.emit_event(
                        EventType.USER_INPUT_REQUESTED,
                        {
                            "question": f"列 '{col_sem.column_name}' 推断为 {col_sem.inferred_type.value}（置信度 {col_sem.confidence:.0%}），"
                                        f"依据: {col_sem.evidence}。是否正确？",
                            "column": col_sem.column_name,
                        },
                    )

            self.complete({"n_columns": len(df.columns), "uncertain": len(uncertain)})
            return context

        except Exception as e:
            # 推断/构建失败 → 返回最基本 context
            self.fail("数据侦察遇到问题")
            self.emit_event(EventType.AGENT_THINKING, {
                "thought": "⚠️ Scout 数据侦察遇到问题，继续使用最小上下文",
            })
            return DataContext(
                data_path=data_path,
                n_rows=len(df) if 'df' in dir() else 0,
                n_cols=len(df.columns) if 'df' in dir() else 0,
                column_semantics=[],
                quality_score=profile.get("quality_score", 0.5) if 'profile' in dir() else 0.5,
            )

    def _infer_all_semantics(self, df: pd.DataFrame, query: str = "") -> list[ColumnSemantic]:
        """推断所有列的语义"""
        semantics = []

        # 目标关键词（来自查询）
        target_keywords = self._extract_target_keywords(query)

        for col in df.columns:
            sem = self._infer_column(df[col], col, target_keywords)
            semantics.append(sem)

        return semantics

    def _infer_column(
        self,
        series: pd.Series,
        name: str,
        target_keywords: list[str] | None = None,
    ) -> ColumnSemantic:
        """单列语义推断"""
        target_keywords = target_keywords or []
        n_unique = series.nunique()
        n_total = len(series)
        null_rate = series.isnull().mean()

        # 100% 唯一 → ID
        if n_unique == n_total and n_total > 10:
            return ColumnSemantic(
                column_name=name,
                inferred_type=SemanticType.ID,
                confidence=0.95,
                evidence="100%唯一值",
                needs_user_input=False,
                suggested_role="identifier",
            )

        # 日期推断
        if pd.api.types.is_datetime64_any_dtype(series):
            return ColumnSemantic(
                column_name=name,
                inferred_type=SemanticType.DATETIME,
                confidence=0.95,
                evidence="日期类型",
                needs_user_input=False,
                suggested_role="time_index",
            )

        # 布尔
        if n_unique == 2 and pd.api.types.is_numeric_dtype(series):
            vals = set(series.dropna().unique())
            if vals <= {0, 1} or vals <= {0.0, 1.0} or vals <= {True, False}:
                return ColumnSemantic(
                    column_name=name,
                    inferred_type=SemanticType.BOOLEAN,
                    confidence=0.90,
                    evidence="二元数值(0/1)",
                    needs_user_input=False,
                    suggested_role="binary_feature",
                )

        if n_unique == 2 and not pd.api.types.is_numeric_dtype(series):
            return ColumnSemantic(
                column_name=name,
                inferred_type=SemanticType.BOOLEAN,
                confidence=0.85,
                evidence="2个唯一值",
                needs_user_input=False,
                suggested_role="binary_feature",
            )

        # 数值
        if pd.api.types.is_numeric_dtype(series):
            # 列名暗示目标变量
            name_lower = name.lower()
            if any(kw in name_lower for kw in target_keywords):
                return ColumnSemantic(
                    column_name=name,
                    inferred_type=SemanticType.TARGET,
                    confidence=0.50,
                    evidence=f"列名含目标关键词",
                    needs_user_input=True,
                    suggested_role="target",
                )

            # 高唯一值比可能是 ID — 但只有整数列且接近连续序列才判为 ID
            # 浮点列高唯一率是正常的（连续值），不应误判
            if n_unique > n_total * 0.8:
                if not pd.api.types.is_float_dtype(series):
                    # 整数列：检查是否接近连续序列（如 0,1,2,...,N）
                    vals = series.dropna().sort_values()
                    val_range = vals.max() - vals.min() + 1
                    if val_range <= n_unique * 1.1:
                        return ColumnSemantic(
                            column_name=name,
                            inferred_type=SemanticType.ID,
                            confidence=0.60,
                            evidence=f"高唯一值整数列 {n_unique}/{n_total}，接近连续序列",
                            needs_user_input=True,
                            suggested_role="identifier",
                        )
                # 浮点列或非连续整数列，高唯一率保持 NUMERIC

            return ColumnSemantic(
                column_name=name,
                inferred_type=SemanticType.NUMERIC,
                confidence=0.90,
                evidence="数值类型",
                needs_user_input=False,
                suggested_role="numeric_feature",
            )

        # 字符串/对象列
        # 尝试检测日期
        if series.dtype == object:
            try:
                sample = series.dropna().head(100)
                if len(sample) > 0:
                    parsed = pd.to_datetime(sample, errors="coerce")
                    if parsed.notna().mean() > 0.8:
                        return ColumnSemantic(
                            column_name=name,
                            inferred_type=SemanticType.DATETIME,
                            confidence=0.80,
                            evidence="字符串可解析为日期",
                            needs_user_input=False,
                            suggested_role="time_index",
                        )
            except Exception:
                pass

        # 类别/有序
        if n_unique < 20:
            name_lower = name.lower()
            if any(kw in name_lower for kw in ["score", "rating", "level", "grade", "rank", "等级", "评分"]):
                return ColumnSemantic(
                    column_name=name,
                    inferred_type=SemanticType.ORDINAL,
                    confidence=0.50,
                    evidence="列名暗示有序",
                    needs_user_input=True,
                    suggested_role="ordinal_feature",
                )

            # 列名暗示目标变量
            if any(kw in name_lower for kw in target_keywords):
                return ColumnSemantic(
                    column_name=name,
                    inferred_type=SemanticType.TARGET,
                    confidence=0.50,
                    evidence=f"列名含目标关键词",
                    needs_user_input=True,
                    suggested_role="target",
                )

            return ColumnSemantic(
                column_name=name,
                inferred_type=SemanticType.CATEGORICAL,
                confidence=0.70,
                evidence=f"{n_unique}个唯一值",
                needs_user_input=n_unique > 5,  # 唯一值多时需要确认
                suggested_role="categorical_feature",
            )

        # 文本
        if n_unique > n_total * 0.5:
            avg_len = series.dropna().str.len().mean() if series.dtype == object else 0
            if avg_len > 50:
                return ColumnSemantic(
                    column_name=name,
                    inferred_type=SemanticType.TEXT,
                    confidence=0.60,
                    evidence="高唯一值比+长文本",
                    needs_user_input=True,
                    suggested_role="text_feature",
                )

        # 完全看不懂
        return ColumnSemantic(
            column_name=name,
            inferred_type=SemanticType.UNKNOWN,
            confidence=0.0,
            evidence="无法推断",
            needs_user_input=True,
        )

    def _extract_target_keywords(self, query: str) -> list[str]:
        """从查询中提取目标变量关键词"""
        # 通用目标关键词
        target_keywords = [
            "target", "y", "label", "revenue", "sales", "income",
            "profit", "cost", "price", "value", "amount",
            "convert", "churn", "retention",
            "收入", "销售额", "利润", "成本", "价格", "转化", "流失",
        ]

        # 从查询中提取
        if query:
            query_lower = query.lower()
            for kw in ["revenue", "sales", "income", "profit", "收入", "销售额", "利润"]:
                if kw in query_lower and kw not in target_keywords:
                    target_keywords.append(kw)

        return target_keywords

    def apply_user_feedback(
        self,
        context: DataContext,
        column: str,
        correct_type: SemanticType,
        correct_role: str = "feature",
    ) -> DataContext:
        """
        应用用户对字段语义的反馈

        Args:
            context: 原始数据上下文
            column: 列名
            correct_type: 用户确认的语义类型
            correct_role: 用户确认的角色

        Returns:
            更新后的数据上下文
        """
        for sem in context.column_semantics:
            if sem.column_name == column:
                sem.user_override = correct_type.value
                sem.inferred_type = correct_type
                sem.suggested_role = correct_role
                sem.needs_user_input = False
                sem.confidence = 1.0
                sem.evidence = "用户确认"
                break

        return context

