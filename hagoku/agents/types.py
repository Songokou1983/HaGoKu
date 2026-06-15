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
    "ignore", "unknown",
]


class FieldInferenceItem(BaseModel):
    """单列语义推断结果 — Scout LLM 结构化输出中的一项"""
    name: str = Field(..., description="原始列名（照抄）")
    inferred_type: str = Field(..., description="数据类型", json_schema_extra={"enum": FIELD_INFERRED_TYPES})
    confidence: float = Field(..., ge=0, le=1, description="置信度 0~1")
    evidence: str = Field(..., description="推断依据：对每个字段说明为什么参与或不参与分析，根据分析目标判断")
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
    used_in_analysis: bool | None = Field(
        default=None,
        description=(
            "该字段是否参与本次分析。设为 true 的字段将出现在「参与分析」列中打勾。"
            "判断规则：结合用户分析目标，能服务于分析目标的字段 → true；"
            "纯标识列（ID/编码/序号）、常量列、与目标完全无关的列 → false。"
            "如果不确定，设为 null 交由用户确认。"
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

    新增字段只需修改 FieldInferenceItem 的 Pydantic 字段定义和 _build_fallback_schema() 中的
    手动 schema，无需改动 Agent 代码（P4 修复）。

    直接使用手动维护的 schema：Pydantic v2 model_json_schema() 会用 $ref/$defs
    引用方式输出，但 $defs 在 llama.cpp OpenAI-compatible API 上报残缺，导致 LLM
    收到空 properties 的工具定义 → 返回空响应。
    """
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
                        "evidence": {"type": "string", "description": "推断依据：对每个字段说明为什么参与或不参与分析，根据分析目标判断"},
                        "needs_user_input": {"type": "boolean", "description": "是否需要用户确认"},
                        "display_name": {"type": "string", "description": "简短中文业务名称（≤6 字，如「收入」「用户ID」）"},
                        "description": {"type": "string", "description": "业务含义理解（一句话自然语言，面向业务同事；引用样本值作为依据；不确定时写「可能表示…」并点出观察到的现象；禁止出现统计用词如「数值型」「分类型」；禁止只重复英文列名）"},
                        "used_in_analysis": {"type": "boolean", "description": "该字段是否参与本次分析。true=参与，false=不参与。"},
                    },
                    "required": ["name", "display_name", "used_in_analysis"],
                },
            },
            "target_columns": {"type": "array", "items": {"type": "string"}, "description": "从用户问题中识别到的目标变量候选列表（列名数组）"},
            "feature_columns": {"type": "array", "items": {"type": "string"}, "description": "特征变量列表（列名数组）"},
            "target_keywords_from_query": {"type": "array", "items": {"type": "string"}, "description": "从用户问题中提取的目标关键词（拆成中文词组，如 ['收入','销售额']）"},
        },
        "required": ["columns", "target_columns", "feature_columns", "target_keywords_from_query"],
    }


# ── 律 5 单权威：字段语义的唯一数据结构 ──
# column_semantics 是字段语义的 Single Source of Truth。
# column_descriptions / column_display_names / target / features / variable_roles
# 均从 column_semantics 派生，禁止平行存储。


def derive_display_names(column_semantics: list[dict[str, Any]]) -> dict[str, str]:
    """从 column_semantics 派生 display_name 映射。"""
    return {
        str(s.get("column_name", "")): str(s.get("display_name", "") or s.get("column_name", ""))
        for s in column_semantics
    }


def derive_descriptions(column_semantics: list[dict[str, Any]]) -> dict[str, str]:
    """从 column_semantics 派生 description 映射。"""
    return {
        str(s.get("column_name", "")): str(s.get("description", "") or "")
        for s in column_semantics
    }


def derive_target_features(
    column_semantics: list[dict[str, Any]],
) -> tuple[list[str], list[str]]:
    """从 column_semantics 派生 target / features 列表。

    优先使用 role 字段；无 role 时回退到 suggested_role。
    仅 used_in_analysis != False 的列参与推导。
    """
    targets: list[str] = []
    features: list[str] = []
    for s in column_semantics:
        col = str(s.get("column_name", ""))
        if s.get("used_in_analysis") is False:
            continue
        role = s.get("role") or s.get("suggested_role", "")
        if role in ("target",):
            targets.append(col)
        elif role in ("ignore", "identifier"):
            continue
        elif role in ("time_index", "time"):
            continue
        else:
            features.append(col)
    return targets, features


def derive_variable_roles(column_semantics: list[dict[str, Any]]) -> dict[str, str]:
    """从 column_semantics 派生 variable_roles 映射。"""
    return {
        str(s.get("column_name", "")): str(s.get("role") or s.get("suggested_role") or "")
        for s in column_semantics
    }


def derive_analysis_columns(column_semantics: list[dict[str, Any]]) -> list[str]:
    """从 column_semantics 派生本次参与分析的列名列表。"""
    return [
        str(s["column_name"])
        for s in column_semantics
        if s.get("used_in_analysis") is True
    ]


def column_semantics_lookup(
    column_semantics: list[dict[str, Any]], column_name: str
) -> dict[str, Any] | None:
    """按列名在 column_semantics 中查找（O(n)，n 通常 ≤ 50）。"""
    for s in column_semantics:
        if str(s.get("column_name", "")) == column_name:
            return s
    return None


# ── ColumnInfo 字段规范（文档型，不做运行时强制） ──
# 每个 column_semantics 元素必须包含以下字段：
#
#   column_name: str          — 原始列名
#   display_name: str         — 简短中文业务名称（≤6 字）
#   description: str          — 业务含义（一句话自然语言）
#   inferred_type: str        — 数据类型
#   confidence: float         — 置信度 0~1
#   evidence: str             — 推断依据
#   suggested_role: str       — LLM 建议角色
#   role: str                 — 当前有效角色（用户纠正后可覆盖 suggested_role）
#   used_in_analysis: bool    — 是否参与本次分析
#   needs_user_input: bool    — 是否需要用户确认
#   confirmed_by_user: bool   — 本轮是否被用户纠正过（律 10）
#   last_confirmed_at_run: str | None — 上次确认的 run_id（律 10）


@dataclass
class ColumnSemantic:
    """列语义推断结果（律 5 扩展版 — 字段语义的单一权威数据结构）。

    所有字段信息统一存储于此：display_name / description / role / used_in_analysis
    均在 column_semantics 中，不再有独立平行的 column_descriptions / column_display_names。
    """

    column_name: str
    inferred_type: SemanticType
    confidence: float  # 0-1
    evidence: str  # 推断依据
    needs_user_input: bool = False
    suggested_role: str = "feature"  # feature / target / identifier / time_index
    user_override: str | None = None  # 用户修正后的类型

    # 律 5 扩展字段
    display_name: str = ""  # 简短中文业务名（≤6 字，如「店铺收入」）
    description: str = ""  # 业务含义（一句话自然语言）
    used_in_analysis: bool = False  # 是否参与本次分析（opt-in：LLM 明确标记才参与）
    role: str = ""  # 当前有效角色（优先于 suggested_role）
    confirmed_by_user: bool = False  # 律 10：本轮是否被用户纠正
    last_confirmed_at_run: str | None = None  # 律 10：上次确认的 run_id

    @property
    def effective_role(self) -> str:
        """当前有效角色：role > suggested_role > fallback 'feature'。"""
        return self.role or self.suggested_role or "feature"

    @property
    def effective_display_name(self) -> str:
        """当前有效显示名：display_name > column_name。"""
        return self.display_name or self.column_name

    def to_dict(self) -> dict[str, Any]:
        return {
            "column_name": self.column_name,
            "inferred_type": self.inferred_type.value if isinstance(self.inferred_type, SemanticType) else str(self.inferred_type),
            "confidence": self.confidence,
            "evidence": self.evidence,
            "needs_user_input": self.needs_user_input,
            "suggested_role": self.suggested_role,
            "user_override": self.user_override,
            "display_name": self.display_name,
            "description": self.description,
            "used_in_analysis": self.used_in_analysis,
            "role": self.effective_role,
            "confirmed_by_user": self.confirmed_by_user,
            "last_confirmed_at_run": self.last_confirmed_at_run,
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
    targets: list = field(default_factory=list)  # P1.3: 支持多目标变量
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
            "targets": self.targets,
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
                inferred_type = s.get("inferred_type") or "unknown"
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
                    needs_user_input=s.get("needs_user_input"),
                    suggested_role=s.get("suggested_role"),
                    user_override=s.get("user_override"),
                ))
        return cls(column_semantics=column_semantics, **data)

    def get_uncertain_columns(self) -> list:
        return [s for s in self.column_semantics if s.needs_user_input]

    def get_target_candidates(self) -> list:
        return [s for s in self.column_semantics if s.suggested_role == "target"]

    def resolve_column_alias(self, name: str) -> str | None:
        """根据已有的列描述精确匹配列名（纯结构性查找，不做语义推断）。

        语义推断（如「销售额→Inc1」）由 LLM 通过 function calling 完成。
        """
        if not name:
            return None

        # 精确匹配 column_descriptions（代码只做已有数据的查找）
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

        return None

    def derive_from_column_semantics(self) -> None:
        """从 column_semantics 推导 target/features/confounders（支持多目标变量）"""
        features = []
        targets = []
        confounders = []
        variable_roles = {}

        for sem in self.column_semantics:
            role = sem.suggested_role
            col = sem.column_name
            variable_roles[col] = role

            if role in ("ignore", "identifier"):
                continue
            if role == "target":
                targets.append(col)
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

        # 兼容旧接口：target 保留第一个，targets 保留全部
        self.targets = targets
        if not self.target and targets:
            self.target = targets[0]
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
