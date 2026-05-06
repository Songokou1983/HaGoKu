"""HaGoKu Agent 共享类型"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


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
    data_path: str
    n_rows: int
    n_cols: int
    column_semantics: list = field(default_factory=list)
    quality_score: float = 0.0
    missing_summary: dict = field(default_factory=dict)
    correlation_highlights: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    target: str | None = None
    features: list = field(default_factory=list)
    confounders: list = field(default_factory=list)
    time_column: str | None = None
    group_columns: list = field(default_factory=list)
    column_descriptions: dict = field(default_factory=dict)
    units: dict = field(default_factory=dict)
    missing_patterns: dict = field(default_factory=dict)
    outlier_candidates: list = field(default_factory=list)
    variable_roles: dict = field(default_factory=dict)
    suggested_analyses: list = field(default_factory=list)
    user_constraints: list = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "data_path": self.data_path,
            "n_rows": self.n_rows,
            "n_cols": self.n_cols,
            "column_semantics": [s.to_dict() if hasattr(s, 'to_dict') else s for s in self.column_semantics],
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
    def from_dict(cls, data: dict[str, Any]) -> "DataContext":
        """从 to_dict() 的输出重建 DataContext"""
        data = data.copy()
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

    def get_uncertain_columns(self) -> list:
        return [s for s in self.column_semantics if s.needs_user_input]

    def get_target_candidates(self) -> list:
        return [s for s in self.column_semantics if s.suggested_role == "target"]

    def resolve_column_alias(self, name: str) -> str | None:
        """根据中文别名解析实际的列名"""
        if not name:
            return None

        COMMON_COLUMN_ALIASES = {
            "销售额": ["Inc1", "Inc2", "收入", "营收", "sales", "revenue"],
            "收入": ["Inc1", "Inc2", "revenue"],
            "利润": ["Bos1", "Bos2", "profit"],
            "成本": ["Bos1", "Bos2", "cost"],
        }

        # 精确匹配 column_descriptions
        if self.column_descriptions:
            for col, desc in self.column_descriptions.items():
                if desc == name:
                    return col

            import re
            clean_name = re.sub(r"（[^）]+）", "", name).strip()
            for col, desc in self.column_descriptions.items():
                desc_clean = re.sub(r"（[^）]+）", "", desc).strip()
                if desc_clean == clean_name:
                    return col

        # 兜底：常见业务术语映射
        for term, candidates in COMMON_COLUMN_ALIASES.items():
            if term in name:
                for sem in self.column_semantics:
                    if sem.column_name in candidates:
                        return sem.column_name

        return None

    def derive_from_column_semantics(self) -> None:
        """从 column_semantics 推导 target/features/confounders"""
        features = []
        confounders = []
        variable_roles = {}

        for sem in self.column_semantics:
            role = sem.suggested_role
            col = sem.column_name
            variable_roles[col] = role

            if role in ("ignore", "identifier"):
                continue
            if role == "target" and not self.target:
                self.target = col
                continue
            if role == "control":
                confounders.append(col)
                continue
            if role in ("time_index", "time") and not self.time_column:
                self.time_column = col
                continue
            if role == "group":
                if col not in self.group_columns:
                    self.group_columns.append(col)
                continue
            features.append(col)

        if not self.features:
            self.features = features
        if not self.confounders:
            self.confounders = confounders
        if not self.variable_roles:
            self.variable_roles = variable_roles


@dataclass
class InteractionResult:
    """
    Agent 交互结果。

    用于 begin()/respond() 双方法接口。
    Agent 每次 begin() 或 respond() 后返回此对象，
    Orchestrator 根据 final 判断是继续还是等用户响应。
    """

    phase: str  # 当前阶段: "infer" | "confirm_fields" | "confirm_strategy" | "next_step" | "done"
    message: str  # 显示给用户的消息
    data: dict[str, Any] = field(default_factory=dict)  # 阶段数据
    actions: list[str] = field(default_factory=list)  # 可选操作按钮
    final: bool = False  # True = 完成，False = 暂停等用户响应

    # 确认相关
    needs_confirmation: bool = False  # 是否需要用户确认
    confirmation_prompt: str = ""  # 确认提示语
    pending_items: list[dict[str, Any]] = field(default_factory=list)  # 待确认项

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "message": self.message,
            "data": self.data,
            "actions": self.actions,
            "final": self.final,
            "needs_confirmation": self.needs_confirmation,
            "confirmation_prompt": self.confirmation_prompt,
            "pending_items": self.pending_items,
        }
