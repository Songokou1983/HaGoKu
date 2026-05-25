"""HaGoKu Studio Agent 共享类型"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


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


# ── Scout 语义推断的数据模型（P4 修复：由数据模型驱动 JSON Schema）
# 新增字段角色只需修改此模型，无需改动 Agent 代码。

FIELD_INFERRED_TYPES = [
    "id", "datetime", "boolean", "numeric",
    "categorical", "text", "unknown",
]

FIELD_SUGGESTED_ROLES = [
    "identifier", "time_index", "binary_feature", "target",
    "numeric_feature", "categorical_feature", "text_feature",
    "unknown",
]


class FieldInferenceItem(BaseModel):
    """单列语义推断结果 — Scout LLM 结构化输出中的一项"""
    name: str = Field(..., description="原始列名（照抄）")
    inferred_type: str = Field(..., description="数据类型", json_schema_extra={"enum": FIELD_INFERRED_TYPES})
    confidence: float = Field(..., ge=0, le=1, description="置信度 0~1")
    evidence: str = Field(..., description="推断依据（自然语言简述）")
    needs_user_input: bool = Field(..., description="是否需要用户确认")
    suggested_role: str = Field(..., description="建议角色", json_schema_extra={"enum": FIELD_SUGGESTED_ROLES})
    display_name: str = Field(..., description="简短中文业务名称（≤6 字，如「收入」「用户ID」）")
    description: str = Field(
        ...,
        description=(
            "业务含义理解（一句话自然语言，面向业务同事；引用样本值作为依据；"
            "不确定时写「可能表示…」并点出观察到的现象；"
            "禁止出现统计用词如「数值型」「分类型」；禁止只重复英文列名）"
        ),
    )


class FieldInferenceResult(BaseModel):
    """Scout 语义推断完整输出 — 由 LLM function calling 生成"""
    columns: list[FieldInferenceItem] = Field(..., description="每个字段的推断结果")
    target_columns: list[str] = Field(default_factory=list, description="从用户问题中识别到的目标变量候选列表（列名数组）")
    feature_columns: list[str] = Field(default_factory=list, description="特征变量列表（列名数组）")
    target_keywords_from_query: list[str] = Field(default_factory=list, description="从用户问题中提取的目标关键词（拆成中文词组，如 ['收入','销售额']）")


def build_submit_field_inference_schema() -> dict[str, Any]:
    """根据 FieldInferenceResult 模型生成 Scout submit_field_inference 工具的 function schema。
    
    新增字段只需修改 FieldInferenceItem，无需改动 Agent 代码（P4 修复）。
    """
    try:
        return FieldInferenceResult.model_json_schema()
    except Exception:
        # Pydantic v1 / v2 兼容：降级为手动生成
        warnings.warn("FieldInferenceResult.model_json_schema() 不可用，使用降级 schema")
        return _build_fallback_schema()


def _build_fallback_schema() -> dict[str, Any]:
    """降级 schema 生成（Pydantic v1 兼容）"""
    return {
        "type": "object",
        "properties": {
            "columns": {
                "type": "array",
                "description": "每个字段的推断结果",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "原始列名（照抄）"},
                        "inferred_type": {"type": "string", "enum": FIELD_INFERRED_TYPES, "description": "数据类型"},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1, "description": "置信度 0~1"},
                        "evidence": {"type": "string", "description": "推断依据（自然语言简述）"},
                        "needs_user_input": {"type": "boolean", "description": "是否需要用户确认"},
                        "suggested_role": {"type": "string", "enum": FIELD_SUGGESTED_ROLES, "description": "建议角色"},
                        "display_name": {"type": "string", "description": "简短中文业务名称（≤6 字，如「收入」「用户ID」）"},
                        "description": {"type": "string", "description": "业务含义理解（一句话自然语言，面向业务同事；引用样本值作为依据；不确定时写「可能表示…」并点出观察到的现象；禁止出现统计用词如「数值型」「分类型」；禁止只重复英文列名）"},
                    },
                    "required": ["name", "inferred_type", "confidence", "evidence", "needs_user_input", "suggested_role", "display_name", "description"],
                },
            },
            "target_columns": {"type": "array", "items": {"type": "string"}, "description": "从用户问题中识别到的目标变量候选列表（列名数组）"},
            "feature_columns": {"type": "array", "items": {"type": "string"}, "description": "特征变量列表（列名数组）"},
            "target_keywords_from_query": {"type": "array", "items": {"type": "string"}, "description": "从用户问题中提取的目标关键词（拆成中文词组，如 ['收入','销售额']）"},
        },
        "required": ["columns", "target_columns", "feature_columns", "target_keywords_from_query"],
    }


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

        COMMON_COLUMN_ALIASES: dict[str, list[str]] = {
            "销售额": ["Inc1", "Inc2", "收入", "营收", "sales", "revenue"],
            "收入": ["Inc1", "Inc2", "revenue"],
            "利润": ["Bos1", "Bos2", "profit"],
            "成本": ["Bos1", "Bos2", "cost"],
        }

        # 精确匹配 column_descriptions
        if self.column_descriptions:
            for col, desc in self.column_descriptions.items():
                if desc == name:
                    return str(col)

            import re
            clean_name = re.sub(r"（[^）]+）", "", name).strip()
            for col, desc in self.column_descriptions.items():
                desc_clean = re.sub(r"（[^）]+）", "", desc).strip()
                if desc_clean == clean_name:
                    return str(col)

        # 兜底：常见业务术语映射
        for term, candidates in COMMON_COLUMN_ALIASES.items():
            if term in name:
                for sem in self.column_semantics:
                    if sem.column_name in candidates:
                        return str(sem.column_name)

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


# ── Refinement Schema（P0 修复：Refinement 由 LLM function calling 驱动，零正则）


def build_submit_refinement_schema() -> dict[str, Any]:
    """构建 submit_refinement 工具的 JSON Schema。

    RefinementParser 不再使用硬编码正则，全部由 LLM 通过此工具的 function calling
    完成语义理解，仅保留退出口令的快速路径。
    """
    return {
        "type": "object",
        "properties": {
            "refine_type": {
                "type": "string",
                "enum": [
                    "filter", "switch_target", "simplify", "more_detail", "explain",
                    "new_direction", "regenerate", "speculate", "explore", "exit", "unknown",
                ],
                "description": (
                    "用户调整意图的类型：\n"
                    "- filter: 筛选/缩小数据范围\n"
                    "- switch_target: 切换分析指标\n"
                    "- simplify: 简化报告\n"
                    "- more_detail: 详细展开\n"
                    "- explain: 解释已有结论\n"
                    "- new_direction: 提出新的分析方向（超出当前调整范围）\n"
                    "- regenerate: 要求重新生成\n"
                    "- speculate: 要求推测原因\n"
                    "- explore: 要求开放性探索\n"
                    "- exit: 退出当前分析\n"
                    "- unknown: 无法分类"
                ),
            },
            "filter_column": {"type": "string", "description": "要筛选的维度名称"},
            "filter_value": {"type": "string", "description": "筛选值"},
            "filter_exclude": {"type": "boolean", "description": "是否排除（true=排除，false=只看）"},
            "new_target": {"type": "string", "description": "要切换的目标指标名称"},
            "verbosity": {"type": "string", "enum": ["simpler", "more_detailed"]},
            "explain_target": {"type": "string", "description": "要解释的结论主题"},
            "can_explain_from_data": {"type": "boolean", "description": "是否能从已有数据结论中解释"},
            "guidance": {"type": "string", "description": "当 refine_type 为 blocked/unknown 时，给用户的引导建议"},
            "thinking": {"type": "string", "description": "LLM 对用户意图的判断依据"},
        },
        "required": ["refine_type"],
    }


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
