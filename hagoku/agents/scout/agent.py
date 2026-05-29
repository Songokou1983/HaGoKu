"""
Scout Agent — 数据侦察员

从 prompt.md 读取角色定义，从 memory.md 读取/保存记忆
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .._scribe.agent import ScribeAgent

import numpy as np
import pandas as pd
import yaml

from ...config import KnowledgeConfig, LLMConfig
from ...observability.event_bus import EventBus
from ...observability.events import EventType
from ...tools.data_io import load_data
from ...tools.profiling import generate_profile
from .._interactive import InteractionMixin
from ..types import InteractionResult, build_submit_field_inference_schema
from . import knowledge as scout_knowledge

# 模块级知识库配置（可通过 YAML 覆盖）
_kconfig = KnowledgeConfig()

from ..constants import (
    SCOUT_CONFIRM_MAX_TOKENS,
    SCOUT_CONFIRM_TEMPERATURE,
    SCOUT_DEDUP_SIMILARITY,
    SCOUT_INFER_MAX_TOKENS,
    SCOUT_INFER_TEMPERATURE,
    SCOUT_LABEL_PREVIEW_LEN,
    SCOUT_LABEL_TRUNCATE_LEN,
    SCOUT_LEARN_CONFIDENCE_MIN,
    SCOUT_TOP_VALUES_MAX_UNIQUE,
)


# 结构性检查：描述是否为「列名（任意内容）」格式。
# 这是纯字符串形状匹配——任何 col_name（...）形式都被视为结构回显。
# 代码不判断括号内内容的语义——那是 LLM 的职责。
_TYPE_ECHO_PATTERN_RE = re.compile(r"^.+\（.+?\）$")


def _description_is_user_facing_meaningful(col_name: str, desc: str) -> bool:
    """检查描述是否提供了超出列名本身的结构性信息。

    纯字符串形状匹配，不涉及语义判断：
    - 空描述 → False
    - 描述 == 列名 → False
    - 描述匹配「列名（...）」模式 → False（结构回显）
    - 其他 → True

    代码不判断括号内内容的业务含义——那是 LLM 的职责。
    """
    d = (desc or "").strip()
    if not d:
        return False
    if d == col_name:
        return False
    # 检测「列名（...）」结构回显模式：任何 col_name（内容）形式
    prefix = col_name + "（"
    if d.startswith(prefix) and d.endswith("）"):
        return False
    return True


def _load_prompt_md_text(agent_name: str) -> str:
    """加载 agent 的 prompt.md 作为 LLM system prompt 的后半部分（行为约束 + 判断规则）。"""
    try:
        path = Path(__file__).parent.parent / agent_name / "prompt.md"
        if path.exists():
            return "\n\n" + path.read_text(encoding="utf-8")
    except Exception as e:
        logging.getLogger("hagoku").warning(f"加载 {agent_name}/prompt.md 失败: {e}")
    return ""


def _format_sample_preview(df: pd.DataFrame, col: str, *, limit: int = 5) -> str:
    """提取样本值直白串，不做格式判断——让 LLM 自行理解。"""
    try:
        vals = df[col].dropna().unique()
    except Exception as e:
        logging.getLogger("hagoku").warning(f"提取列 {col} 样本值失败: {e}")
        return ""
    if len(vals) == 0:
        return ""
    parts: list[str] = []
    for v in vals[:limit]:
        parts.append(str(v).strip())
    return ", ".join(parts)




class ScoutAgent(InteractionMixin):
    """数据侦察员：理解数据上下文，不猜，问"""

    def __init__(
        self,
        llm_config: LLMConfig,
        event_bus: EventBus,
        scribe: "ScribeAgent | None" = None,
        llm_client: Any | None = None,
    ) -> None:
        self.role = "scout"
        self.llm_config = llm_config
        self.event_bus = event_bus
        self.scribe = scribe  # 可选，用于看板 block/unblock
        self._llm_client = llm_client  # 外部传入的 LLM 客户端（双层策略用）

        # 加载 prompt.md
        self.prompt = self._load_prompt()
        self.memory = self._load_memory()

        # 交互状态
        self._phase = "begin"
        self._context: dict | None = None
        self._data_path: str | None = None
        self._query: str = ""

    def _load_prompt(self) -> str:
        """从 prompt.md 加载角色定义"""
        path = Path(__file__).parent / "prompt.md"
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    def _load_memory(self) -> dict:
        """从 memory.md 加载记忆"""
        path = Path(__file__).parent / "memory.md"
        if path.exists():
            content = path.read_text(encoding="utf-8")
            # 提取 YAML 部分
            match = re.search(r"```yaml\n(.*?)\n```", content, re.DOTALL)
            if match:
                try:
                    return yaml.safe_load(match.group(1)) or {}
                except yaml.YAMLError:
                    return {}
        return {"fields": {}, "analyses": [], "interactions": []}

    def _save_memory(self) -> None:
        """保存记忆到 memory.md"""
        path = Path(__file__).parent / "memory.md"
        content = path.read_text(encoding="utf-8")

        # 将 fields 嵌套到 yaml 顶层 key，保证缩进正确
        fields_yaml = yaml.dump(
            {"fields": self.memory.get("fields") or {}},
            default_flow_style=False,
            allow_unicode=True,
        ).rstrip()

        pattern = r"```yaml\nfields:.*?\n```"
        if re.search(pattern, content, re.DOTALL):
            content = re.sub(pattern, f"```yaml\n{fields_yaml}\n```", content, flags=re.DOTALL)
        else:
            content = re.sub(r"fields:.*", fields_yaml, content)

        path.write_text(content, encoding="utf-8")

    def _emit(self, event_type: EventType, data: dict | None = None) -> None:
        self.event_bus.emit(event_type=event_type, agent=self.role, data=data or {})

    # ── 核心逻辑 ────────────────────────────────────────────

    def run(
        self,
        data_path: str,
        query: str = "",
        project_id: str | None = None,
        memory_project: dict | None = None,
        *,
        emit_completed: bool = True,
    ) -> dict:
        """
        执行数据侦察

        Args:
            emit_completed: 为 False 时不发 AGENT_COMPLETED（编排层在用户确认字段理解后再发）。

        Returns:
            DataContext dict
        """
        self._emit(EventType.AGENT_STARTED, {"goal": "理解数据字段和质量问题"})

        try:
            # 1. 加载数据
            self._emit(EventType.AGENT_THINKING, {"thought": f"正在加载数据: {data_path}"})
            df = load_data(data_path)
            self._emit(EventType.TOOL_CALLED, {"tool": "load_data", "args_summary": data_path})
            self._emit(EventType.TOOL_RESULT, {"summary": f"加载成功: {len(df)} 行, {len(df.columns)} 列"})

            # 2. 数据画像
            self._emit(EventType.AGENT_THINKING, {"thought": "生成数据画像..."})
            profile = generate_profile(df)
            self._emit(EventType.TOOL_RESULT, {"summary": f"质量={profile['quality_score']:.0%}"})

            # 3. 推断字段语义
            column_semantics = self._infer_all_semantics(df, query, memory_project)

            # 4. 构建上下文
            context = {
                "data_path": data_path,
                "query": query,
                "n_rows": len(df),
                "n_cols": len(df.columns),
                "column_semantics": column_semantics,
                "quality_score": profile["quality_score"],
                "missing_summary": profile.get("missing_summary", {}),
                "warnings": [],
                "column_descriptions": {},
            }

            # 5. 应用项目记忆（从 memory_project 传入）
            if memory_project and project_id:
                self._apply_project_memory(context, memory_project)

            # 6. 派生字段角色
            self._derive_roles(context)

            # 7. 质量警告
            if profile.get("duplicate_rate", 0) > 0.05:
                context["warnings"].append(f"重复行率 {profile['duplicate_rate']:.1%} 较高")
            if profile.get("missing_summary", {}).get("null_rate", 0) > 0.1:
                context["warnings"].append(f"缺失率 {profile['missing_summary']['null_rate']:.1%} 较高")

            # 8. 生成字段描述（LLM批量）
            self._generate_field_descriptions(context, df)

            # 9. 学习：将高置信度推断写入知识库
            self._learn_from_results(context, project_id)

            # 10. 更新自身记忆
            self._update_own_memory(context, project_id)

            if emit_completed:
                self._emit(EventType.AGENT_COMPLETED, {
                    "result_summary": f"理解 {len(context['column_semantics'])} 个字段"
                })

            return context

        except FileNotFoundError:
            self._emit(EventType.AGENT_FAILED, {"error": "数据文件未找到"})
            return {"error": "数据文件未找到"}
        except Exception as e:
            self._emit(EventType.AGENT_FAILED, {"error": str(e)})
            return {"error": str(e)}

    # ── 交互式接口 ────────────────────────────────────────

    def begin(  # type: ignore[override]
        self,
        data_path: str,
        query: str = "",
        project_id: str | None = None,
        memory_project: dict | None = None,
    ) -> InteractionResult:
        """
        开始 Scout 交互。

        流程：加载数据 → 推断语义 → 确认字段 → 写记忆 → 询问下一步
        每次暂停都会 block_task() 等用户确认。
        """
        self._data_path = data_path
        self._query = query

        # emit STARTED，让 Scribe claim 看板任务
        self._emit(EventType.AGENT_STARTED, {"goal": "理解数据字段和质量问题"})

        try:
            # 加载数据
            self._emit(EventType.AGENT_THINKING, {"thought": f"正在加载数据: {data_path}"})
            df = load_data(data_path)
            self._emit(EventType.TOOL_RESULT, {"summary": f"加载成功: {len(df)} 行, {len(df.columns)} 列"})

            # 数据画像
            profile = generate_profile(df)

            # 推断字段语义
            column_semantics = self._infer_all_semantics(df, query, memory_project)

            # per-column 数据画像（用于 LLM 生成描述 + 前端展示）
            column_profiles: dict[str, Any] = {}
            for col in df.columns:
                column_profiles[col] = self._profile_column(df[col], col, df)

            # 构建上下文
            context = {
                "data_path": data_path,
                "query": query,
                "n_rows": len(df),
                "n_cols": len(df.columns),
                "column_semantics": column_semantics,
                "quality_score": profile["quality_score"],
                "missing_summary": profile.get("missing_summary", {}),
                "warnings": [],
                "column_descriptions": {},
                "_column_profiles": column_profiles,
            }

            # 应用项目记忆
            if memory_project and project_id:
                self._apply_project_memory(context, memory_project)

            # 派生字段角色
            self._derive_roles(context)

            # 生成字段描述（增强版：融入分布数据）
            self._generate_field_descriptions(context, df)

            # 提取样本值（用于 LLM 理解字段含义）
            sample_values = {}
            for col in df.columns:
                prev = _format_sample_preview(df, col, limit=3)
                if prev:
                    sample_values[col] = prev
            context["_sample_values"] = sample_values

            self._context = context
            self._phase = "confirm_fields"

            # 需要用户确认的字段
            uncertain = [s for s in context["column_semantics"] if s.get("needs_user_input")]
            if uncertain:
                # block 看板，等用户确认
                if self.scribe:
                    self.scribe.block_task("scout", "等用户确认字段含义")
                self._emit(EventType.AGENT_THINKING, {"thought": f"识别 {len(uncertain)} 个字段需确认，正在生成确认消息..."})

                # 用 LLM 生成完整确认消息（传入所有字段，不只是 uncertain）
                llm_message = self._generate_confirmation_message(context["column_semantics"], context)

                return self._pause(
                    phase="confirm_fields",
                    message=llm_message,
                    needs_confirmation=True,
                    confirmation_prompt="请逐个确认或修正字段含义",
                    pending_items=[
                        {
                            "column": s["column_name"],
                            "description": context["column_descriptions"].get(s["column_name"], ""),
                        }
                        for s in uncertain
                    ],
                    data={
                        "column_semantics": column_semantics,
                        "column_descriptions": context["column_descriptions"],
                        "quality_score": profile["quality_score"],
                        "warnings": context["warnings"],
                    },
                )

            # 无需确认，直接进入写记忆
            return self._write_memory_and_ask_next()

        except FileNotFoundError:
            self._emit(EventType.AGENT_FAILED, {"error": "数据文件未找到"})
            return self._done("done", "数据文件未找到", {"error": "数据文件未找到"})
        except Exception as e:
            self._emit(EventType.AGENT_FAILED, {"error": str(e)})
            return self._done("done", f"Scout 失败: {e}", {"error": str(e)})

    def respond(  # type: ignore[override]
        self,
        user_input: dict,
        project_id: str | None = None,
    ) -> InteractionResult:
        """
        处理用户对字段确认的响应。

        user_input 格式:
          {
            "confirmed": {"Inc1": "销售额", "渠道": "触达用户的途径"},
            "corrected": {"Period": "分析周期维度"},
            "comments": {"Inc1": "注意单位是万元"}
          }
        """
        if self._phase != "confirm_fields" or self._context is None:
            return self._done("done", "阶段错误，请重新开始", {})

        confirmed = user_input.get("confirmed", {})
        corrected = user_input.get("corrected", {})
        comments = user_input.get("comments", {})

        # 更新 column_descriptions（旧接口）+ column_semantics（律 5 单权威）
        all_updates = {**confirmed, **corrected}
        for col, desc in all_updates.items():
            self._context["column_descriptions"][col] = desc
            # 律 5：同步写入 column_semantics
            for sem in self._context.get("column_semantics", []):
                if sem["column_name"] == col:
                    sem["description"] = desc
                    sem["confirmed_by_user"] = True  # 律 10
                    break

        # 记录用户注释到 context
        if comments:
            self._context["user_comments"] = comments

        # 解除 block，继续看板任务
        if self.scribe:
            self.scribe.unblock_task("scout")

        # 写记忆
        self._update_own_memory(self._context, project_id)
        self._learn_from_results(self._context, project_id)

        self._emit(EventType.AGENT_THINKING, {
            "thought": f"已确认 {len(confirmed) + len(corrected)} 个字段"
        })

        return self._write_memory_and_ask_next(project_id)

    def _write_memory_and_ask_next(self, project_id: str | None = None) -> InteractionResult:
        """写记忆后询问用户是否进入下一步"""
        self._phase = "next_step"

        uncertain = [s for s in self._context["column_semantics"] if s.get("needs_user_input")]  # type: ignore[index]
        summary = (
            f"已理解 {len(self._context['column_semantics'])} 个字段，"  # type: ignore[index]
            f"{len(uncertain)} 个需后续关注"
        )

        # block，等用户确认进入下一步
        if self.scribe:
            self.scribe.block_task("scout", "等用户确认进入清洗阶段")
        self._emit(EventType.AGENT_COMPLETED, {"result_summary": summary})

        return self._pause(
            phase="next_step",
            message=summary + "\n\n建议进入「清洗阶段」，是否确认？",
            actions=["进入清洗", "重新理解字段", "结束分析"],
            pending_items=[],
            data={
                "context": self._context,
                "n_cols": self._context["n_cols"],  # type: ignore[index]
                "n_rows": self._context["n_rows"],  # type: ignore[index]
            },
        )

    # ==== CHANNEL ZONE: 禁止正则/if-else 语义分支 ====
    def _infer_all_semantics(self, df: pd.DataFrame, query: str, memory_project: dict[str, Any] | None = None) -> list[dict]:
        """推断所有列的语义 — 全部通过 LLM 结构化输出完成，零硬编码

        memory_project: 来自 MemoryManager.build_memory_project() 的项目记忆，
                       包含 {"fields": {...}, "display_names": {...}}。
                       已确认的字段描述和中文名称会直接注入 prompt，LLM 可沿用而非重新推断。
        """
        from ...llm.client import create_quick_client, create_raw_client

        # 构建每列的 profile 摘要
        column_list: list[dict] = []
        for col in df.columns:
            p = self._profile_column(df[col], col, df)
            sample_vals = _format_sample_preview(df, col, limit=5)
            column_list.append({
                "name": col,
                "dtype": p.get("dtype", "object"),
                "n_unique": p.get("n_unique", 0),
                "n_total": p.get("n_total", 0),
                "null_pct": p.get("null_pct", 0),
                "sample_values": sample_vals if sample_vals else "",
                "top_values": p.get("top_values", {}),
                "min": p.get("min"),
                "max": p.get("max"),
                "mean": p.get("mean"),
                "median": p.get("median"),
                "q25": p.get("q25"),
                "q75": p.get("q75"),
                "distribution_summary": p.get("distribution_summary", ""),
                "time_min": p.get("time_min"),
                "time_max": p.get("time_max"),
            })

        payload = {
            "user_query": query,
            "n_rows": len(df),
            "n_cols": len(df.columns),
            "columns": column_list,
        }

        # ── 跨项目知识检索（增强版：向量检索 + 项目记忆聚合 + 可观测性）──
        knowledge_notes_parts: list[str] = []
        seen_field_refs: set[str] = set()  # 去重：不同列可能匹配到同一条知识
        total_recalled = 0
        total_accepted = 0

        for col_info in column_list:
            col_name = col_info["name"]
            # 1) 向量检索：列名 + 样本值
            search_query = f"{col_name} {col_info.get('sample_values', '')}"
            matches = scout_knowledge.recall(search_query, top_k=3)
            total_recalled += len(matches)

            for match in matches:
                sim = match.get("similarity", 0)
                if sim < _kconfig.similarity_threshold:
                    continue
                meta = match.get("metadata") or {}
                ref_key = meta.get("field", match.get("id", ""))
                if ref_key in seen_field_refs:
                    continue
                seen_field_refs.add(ref_key)
                total_accepted += 1
                parts: list[str] = []
                parts.append(f"    历史字段「{meta.get('field', '?')}」")
                parts.append(f"含义: {meta.get('meaning', '?')}")
                parts.append(f"数据特征: {meta.get('data_pattern', '?')}")
                parts.append(f"推断角色: {meta.get('inferred_role', '?')}")
                if meta.get("project"):
                    parts.append(f"来源项目: {meta['project']}")
                if meta.get("confidence") is not None:
                    parts.append(f"历史置信度: {meta['confidence']:.0%}")
                knowledge_notes_parts.append("\n".join(parts))

        # 2) 项目记忆聚合：将 memory_project 中的字段也注入知识区
        if memory_project:
            fields = memory_project.get("fields", {})
            display_names = memory_project.get("display_names", {})
            if fields:
                # 检查当前数据集中哪些列在项目记忆中有记录
                matched_cols = [c for c in df.columns if c in fields]
                if matched_cols:
                    proj_parts: list[str] = []
                    proj_parts.append("【本项目记忆 — 以下字段已在过往分析中确认，请直接沿用：】")
                    for col in matched_cols:
                        desc = fields[col]
                        dn = display_names.get(col, "")
                        line = f"  - {col}"
                        if dn:
                            line += f"（中文名称：{dn}）"
                        line += f"：{desc}"
                        proj_parts.append(line)
                    knowledge_notes_parts.append("\n".join(proj_parts))

                    self._emit(EventType.AGENT_THINKING, {
                        "thought": f"复用项目记忆：{len(matched_cols)} 个字段来自过往分析"
                    })

        # 3) 可观测性：记录跨项目知识检索效果
        if total_recalled > 0:
            self._emit(EventType.AGENT_THINKING, {
                "thought": (
                    f"跨项目知识检索：从 {total_recalled} 条候选中采纳 {total_accepted} 条"
                    f"（复用率 {total_accepted / total_recalled:.0%}）"
                )
            })

        knowledge_section = ""
        if knowledge_notes_parts:
            knowledge_section = (
                "\n\n"
                "【跨项目知识库参考 — 以下是历史分析中类似字段的经验，供参考而非决定：】\n"
                "这些字段在数据特征和列名上与当前数据集的某些列相似。"
                "你可以参考这些历史经验来辅助推断，但最终判断需要基于当前数据集的实际情况。\n\n"
                + "\n\n".join(knowledge_notes_parts)
            )

        # 拼接记忆上下文到 system_prompt
        memory_notes = ""
        if memory_project:
            fields = memory_project.get("fields", {})
            display_names = memory_project.get("display_names", {})
            if fields or display_names:
                lines = [
                    "\n\n【项目记忆 — 以下是历史分析中的字段记录，请沿用其中文名称和业务含义；但字段角色（target/feature/ignore）需根据当前分析目标重新判断：】"
                ]
                for col, desc in fields.items():
                    dn = display_names.get(col, "")
                    if dn:
                        lines.append(f"  - {col}: 中文名称「{dn}」，含义：{desc}")
                    else:
                        lines.append(f"  - {col}: 含义：{desc}")
                memory_notes = "\n".join(lines)

        # P4 修复：由 FieldInferenceResult 数据模型驱动 schema，新增字段无需改 Agent 代码
        _schema = build_submit_field_inference_schema()
        submit_tool = {
            "type": "function",
            "function": {
                "name": "submit_field_inference",
                "description": "提交字段语义推断结果。调用此工具来报告你对数据集中每个字段的分析结论，包括数据类型、置信度、业务名称和含义理解。",
                "parameters": _schema,
            }
        }

        # ── 注入 Agent 行为约束（prompt.md）和用户命令上下文 ──
        prompt_md_text = _load_prompt_md_text("scout")
        command_context = ""
        try:
            ctx = getattr(self, "_context", {}) or {}
            pt = (ctx.get("_pending_command_text") or "").strip()
            if pt:
                command_context = f"\n\n【用户最近提出的指令/纠正（必须采纳并执行，优先级高于其他所有信息）：】\n{pt}"
        except Exception as e:
            logging.getLogger("hagoku").warning(f"获取命令上下文失败: {e}")

        # ── 将用户分析目标前置为最高优先级指令 ──
        analysis_goal_line = ""
        if query and query.strip():
            analysis_goal_line = (
                f"\n\n【最高优先级 — 用户分析目标】\n"
                f"「{query.strip()}」\n"
                f"你必须逐一检查每个字段是否能服务于上述分析目标。\n"
                f"将最相关的字段设为 target（目标变量），辅助字段设为 feature（特征变量），\n"
                f"无关字段设为 ignore 或 identifier。\n"
                f"⚠️ 趋势/变化类分析：时间列（Period/Date）必须判为 feature，不是 time_index。\n"
                f"不要仅根据数据类型（数值/文本/日期）推断角色——必须结合分析目标做语义判断。\n"
                f"\n"
                f"⚡ 关键：对于与本次分析目标「{query.strip()}」无关的字段，\n"
                f"必须将 used_in_analysis 设为 false。\n"
                f"只有确实能服务于用户分析目标的字段才设为 true。\n"
                f"举例：用户问「各渠道收入对比」——渠道字段、收入字段 = true；\n"
                f"设备型号、注册日期等无关字段 = false。\n"
                f"\n"
                f"used_in_analysis 判断规则（严格按 suggested_role 执行）：\n"
                f"  • suggested_role 为 target 或 feature → used_in_analysis = true\n"
                f"  • suggested_role 为 identifier、ignore、time_index、unknown → used_in_analysis = false\n"
                f"这是硬性规则，不允许例外。role 是你自己判的，uia 必须与 role 一致。\n"
            )

        system_prompt = (
            "你是专业数据分析侦察员。基于每列的数据画像，推断每个字段的语义角色。\n"
            "你必须调用 submit_field_inference 工具来提交你的分析结果。\n"
            "同名 display_name 可以相同但不要编号——让后续流程处理重复。"
            f"{analysis_goal_line}"
            f"{knowledge_section}"
            f"{memory_notes}"
            f"{prompt_md_text}"
            f"{command_context}"
        )

        client = create_raw_client(self.llm_config)
        try:
            response = client.chat.completions.create(
                model=self.llm_config.model_quick or self.llm_config.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"请分析以下数据集的字段语义：\n```json\n{__import__('json').dumps(payload, ensure_ascii=False, default=str)}\n```"},
                ],
                temperature=SCOUT_INFER_TEMPERATURE,
                max_tokens=SCOUT_INFER_MAX_TOKENS,
                tools=[submit_tool],
                tool_choice={"type": "function", "function": {"name": "submit_field_inference"}},
            )
        except Exception as e:
            raise RuntimeError(f"Scout 字段推断失败：LLM 不可达，请检查 API 配置。原始错误: {e}") from e

        import json as _json
        raw_text = response.choices[0].message.content or ""
        tool_calls = response.choices[0].message.tool_calls

        if tool_calls:
            # 优先：LLM 支持 tool calling，从结构化参数中解析
            result = _json.loads(tool_calls[0].function.arguments)
        elif raw_text:
            # 兜底：LLM 不支持 tool calling，从文本中提取 JSON
            cleaned = raw_text.strip()
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```\s*$", "", cleaned)
            cleaned = cleaned.strip()
            try:
                result = _json.loads(cleaned)
            except _json.JSONDecodeError:
                match = re.search(r"\{.*\}", cleaned, re.DOTALL)
                if match:
                    result = _json.loads(match.group())
                else:
                    raise ValueError(
                        f"Scout LLM 未调用工具且返回文本无法解析为 JSON。"
                        f"原始文本前 500 字: {raw_text[:500]}"
                    ) from None
        else:
            raise ValueError("Scout LLM 既未调用工具，也未返回文本内容")

        columns_out = result.get("columns") or result.get("column_semantics") or []
        if not columns_out:
            raise ValueError("Scout LLM 未返回任何列推断结果（`columns` 字段为空）")

        # 标准化输出到 Scout 代码库期望的格式（律 5：display_name/description/role 入 column_semantics）
        semantics: list[dict] = []
        for item in columns_out:
            col_name = item.get("name", "")
            if not col_name or col_name not in set(df.columns):
                continue
            semantics.append({
                "column_name": col_name,
                "inferred_type": item.get("inferred_type", "unknown"),
                "confidence": float(item.get("confidence", 0.5)),
                "evidence": item.get("evidence", ""),
                "needs_user_input": bool(item.get("needs_user_input", True)),
                "suggested_role": item.get("suggested_role", "unknown"),
                "used_in_analysis": item.get("used_in_analysis"),
                # 律 5 扩展：display_name / description / role 直接入 column_semantics
                "display_name": str(item.get("display_name", "") or "").strip(),
                "description": str(item.get("description", "") or "").strip(),
                "role": "",  # 初始为空，用户纠正后由 orchestrator 填入
                "confirmed_by_user": False,
                "last_confirmed_at_run": None,
            })

        # 如果 LLM 遗漏某些列，用 unknown 补上
        known = {s["column_name"] for s in semantics}
        for col in df.columns:
            if col not in known:
                semantics.append({
                    "column_name": col,
                    "inferred_type": "unknown",
                    "confidence": 0.0,
                    "evidence": "LLM 未覆盖",
                    "needs_user_input": True,
                    "suggested_role": "unknown",
                    "used_in_analysis": None,
                    "display_name": col,
                    "description": "",
                    "role": "",
                    "confirmed_by_user": False,
                    "last_confirmed_at_run": None,
                })

        # 从 columns 数组中提取 description / display_name 到映射
        llm_column_descriptions: dict[str, str] = {}
        llm_display_names: dict[str, str] = {}
        for item in columns_out:
            col_name = item.get("name", "")
            if not col_name:
                continue
            desc = item.get("description", "")
            if desc and isinstance(desc, str) and desc.strip():
                llm_column_descriptions[col_name] = desc.strip()
            dn = item.get("display_name", "")
            if dn and isinstance(dn, str) and dn.strip():
                llm_display_names[col_name] = dn.strip()

        # 也兼容根级别旧格式
        root_descs = result.get("column_descriptions")
        if isinstance(root_descs, dict):
            for k, v in root_descs.items():
                if k not in llm_column_descriptions and v and isinstance(v, str):
                    llm_column_descriptions[k] = v
        root_names = result.get("column_display_names")
        if isinstance(root_names, dict):
            for k, v in root_names.items():
                if k not in llm_display_names and v and isinstance(v, str):
                    llm_display_names[k] = v

        self._llm_column_descriptions = llm_column_descriptions
        self._llm_display_names = llm_display_names
        self._llm_target_keywords = result.get("target_keywords_from_query") or []
        self._llm_target_columns = result.get("target_columns") or []
        self._llm_feature_columns = result.get("feature_columns") or []

        return semantics

    def _profile_column(self, series: pd.Series, name: str, df: pd.DataFrame) -> dict:
        """对单列做数据画像：分布特征、值范围、缺失率、唯一值数"""
        n_total = len(series)
        n_null = int(series.isna().sum())
        n_unique = series.nunique()
        null_pct = n_null / n_total if n_total > 0 else 0

        profile: dict[str, Any] = {
            "column_name": name,
            "dtype": str(series.dtype),
            "n_total": n_total,
            "n_null": n_null,
            "null_pct": round(null_pct, 4),
            "n_unique": n_unique,
        }

        # 数值列：分位数 + 分布形状
        if pd.api.types.is_numeric_dtype(series):
            non_null = series.dropna()
            if len(non_null) > 0:
                profile.update({
                    "min": float(non_null.min()) if hasattr(non_null, "min") else None,
                    "q25": float(non_null.quantile(0.25)),
                    "median": float(non_null.median()),
                    "q75": float(non_null.quantile(0.75)),
                    "max": float(non_null.max()) if hasattr(non_null, "max") else None,
                    "mean": round(float(non_null.mean()), 4),
                    "std": round(float(non_null.std()), 4),
                })
                # 分布特征仅传原始分位数，让 LLM 自行判断分布形态
                # 不再由代码做硬编码的形状标签
                parts: list[str] = []
                for key in ["min", "q25", "median", "q75", "max"]:
                    v = profile.get(key)
                    if v is not None:
                        if isinstance(v, float):
                            if abs(v) >= 1e6 or (v != 0 and abs(v) < 1e-5):
                                parts.append(f"{v:.3e}")
                            else:
                                parts.append(f"{v:.6g}")
                        else:
                            parts.append(str(v))
                    else:
                        parts.append("-")
                profile["distribution_summary"] = " ~ ".join(parts)

        # 类别/对象列：高频值 top-5
        if n_unique < SCOUT_TOP_VALUES_MAX_UNIQUE and n_unique > 0:
            vc = series.value_counts().head(5)
            top_vals = {}
            for v, c in vc.items():
                label = str(v)
                if len(label) > SCOUT_LABEL_TRUNCATE_LEN:
                    label = label[:SCOUT_LABEL_PREVIEW_LEN] + "…"
                top_vals[label] = int(c)
            profile["top_values"] = top_vals

        # 日期列：时间范围
        if pd.api.types.is_datetime64_any_dtype(series):
            non_null = series.dropna()
            if len(non_null) > 0:
                profile["time_min"] = str(non_null.min())
                profile["time_max"] = str(non_null.max())

        return profile


    def _apply_project_memory(self, context: dict, memory_project: dict) -> None:
        """应用项目记忆中的字段定义"""
        fields = memory_project.get("fields", {})
        display_names = memory_project.get("display_names", {})
        if not fields and not display_names:
            return

        # 从全局记忆加载字段描述和显示名
        for sem in context["column_semantics"]:
            col = sem["column_name"]
            if col in fields:
                context["column_descriptions"][col] = fields[col]
                sem["confidence"] = 1.0  # 记忆中的定义是高置信度
            if col in display_names:
                context.setdefault("column_display_names", {})
                context["column_display_names"][col] = display_names[col]
                sem["needs_user_input"] = False  # 记忆中的名称减少确认需求

    def _derive_roles(self, context: dict) -> None:
        """从 column_semantics 推导 target/features（支持多目标变量）"""
        features = []
        targets = []
        variable_roles = {}

        for sem in context["column_semantics"]:
            col = sem.get("column_name", sem.get("column"))
            role = sem.get("suggested_role", "feature")
            variable_roles[col] = role

            if role in ("ignore", "identifier"):
                continue
            if role == "target":
                targets.append(col)
                continue
            features.append(col)

        # 兼容旧接口：target 保留第一个目标变量，同时提供 targets 列表
        context["target"] = targets[0] if targets else None
        context["targets"] = targets
        context["features"] = features
        context["variable_roles"] = variable_roles

    def _generate_field_descriptions(self, context: dict, df: pd.DataFrame) -> None:
        """将 _infer_all_semantics LLM 产出回填到 context：column_descriptions / display_names / target / features。

        _infer_all_semantics 已经通过一次 LLM 调用产出了所有字段的 type/role/desc/display_name。
        此方法仅做回填，不做独立 LLM 调用——零硬编码。

        律 5 过渡：同时写入 column_descriptions/column_display_names（旧接口兼容）
        和 column_semantics[i].description / .display_name（新单一权威源）。
        """
        # 1. 回填 LLM 产出的 column_descriptions（_infer_all_semantics 暂存在 self 上）
        llm_descs = getattr(self, "_llm_column_descriptions", {}) or {}
        for col, desc in llm_descs.items():
            if col not in context["column_descriptions"]:
                context["column_descriptions"][col] = desc
            # 律 5：同步写入 column_semantics
            for sem in context["column_semantics"]:
                if sem["column_name"] == col:
                    if not sem.get("description"):
                        sem["description"] = desc
                    break

        # 2. 回填 display_names
        llm_names = getattr(self, "_llm_display_names", {}) or {}
        if llm_names:
            context.setdefault("column_display_names", {})
            for col, name in llm_names.items():
                if col not in context["column_display_names"]:
                    context["column_display_names"][col] = name
                # 律 5：同步写入 column_semantics
                for sem in context["column_semantics"]:
                    if sem["column_name"] == col:
                        if not sem.get("display_name"):
                            sem["display_name"] = name
                        break

        # 3. 无 LLM 描述的列：标记 needs_user_input=True
        for sem in context["column_semantics"]:
            col = sem["column_name"]
            raw = str(context["column_descriptions"].get(col, "") or "").strip()
            if not raw or raw == col:
                context.setdefault("column_display_names", {})[col] = col
                sem["needs_user_input"] = True
                # 律 5：兜底 display_name 写入 column_semantics
                if not sem.get("display_name"):
                    sem["display_name"] = col

        # 4. 回填 LLM 产出的 target / features
        if getattr(self, "_llm_target_columns", None):
            context["target"] = getattr(self, "_llm_target_columns")[0] if getattr(self, "_llm_target_columns") else None
        if getattr(self, "_llm_feature_columns", None):
            context["features"] = list(getattr(self, "_llm_feature_columns"))

        # 4b. 同步 column_semantics 和 variable_roles，确保 UI 复选框与实际分析列一致
        analysis_cols: set[str] = set()
        if context.get("target"):
            analysis_cols.add(context["target"])
        if context.get("features"):
            analysis_cols.update(context["features"])
        for sem in context.get("column_semantics", []):
            col = sem.get("column_name", "")
            if not col:
                continue
            if col in analysis_cols:
                role = "target" if col == context.get("target") else "feature"
                sem["suggested_role"] = role
                context.setdefault("variable_roles", {})[col] = role
                # used_in_analysis 由 LLM 直接决策，代码不做推导
            else:
                context.setdefault("variable_roles", {})[col] = sem.get("suggested_role", "unknown")
                # used_in_analysis 由 LLM 直接决策，代码不做推导

    def _generate_confirmation_message(self, column_semantics: list, context: dict) -> str:
        """用 LLM 生成字段确认的 Markdown 表（字段名｜理解名称｜含义理解）。"""
        # 构建字段列表给 LLM
        field_info = []
        for s in column_semantics:
            col = s["column_name"]
            desc = context["column_descriptions"].get(col, "")
            sample_val = context.get("_sample_values", {}).get(col, "")
            field_info.append(f"- {col}: {desc} | 示例: {sample_val}" if sample_val else f"- {col}: {desc}")

        fields_text = "\n".join(field_info)

        # 提取分析角色信息（如果有的话）
        roles_text = ""
        target = context.get("target")
        features = context.get("features") or []
        if target:
            roles_text += f"- 目标变量（因变量）：{target}\n"
        if features:
            roles_text += f"- 特征变量（自变量）：{', '.join(features)}\n"

        # ── 注入 Agent 行为约束（prompt.md） ──
        prompt_md_text = _load_prompt_md_text("scout")

        system_prompt = (
            "你是一个数据分析助手，正在帮助用户理解数据字段的含义。\n\n"
            "你的任务是：\n"
            "1. 为每个字段生成四列信息：**字段名**（原始列名）、**理解名称**（后续展示用的简短业务称呼）、**含义理解**（业务含义一句话）、**分析角色**（目标变量/特征变量/其他/不参与分析）\n"
            "2. 确认完成后，告知用户如何继续：\n"
            "   - 如果所有字段理解正确 → 用户可以输入\"确认\"继续下一步\n"
            "   - 如果某个字段理解有误 → 用户会告诉你正确含义\n"
            "   - 如果某字段完全不认识 → 用户会补充说明\n\n"
            "重要规则：\n"
            "- **字段名照抄原始列名**，不要翻译\n"
            "- **理解名称要简短**（建议 ≤12 字），后续分析表格第二列会用到\n"
            "- **含义理解**说明这个字段在业务中的具体含义\n"
            "- **分析角色**根据系统推断的目标变量和特征变量来标注，未指定的字段标注\"其他\"或\"不参与分析\"（如 ID、时间戳等）"
            f"{prompt_md_text}"
        )

        roles_hint = (
            f"\n\n系统已推断的分析角色：\n{roles_text}\n"
            "请在上表的「分析角色」一列中按此标注。目标变量的角色为「目标变量（因变量）」，"
            "特征变量的角色为「特征变量（自变量）」，其余字段标注「其他」或「不参与分析」。"
        ) if roles_text else ""

        user_prompt = f"""请为以下字段生成理解：

{fields_text}

数据概况：{context.get('n_rows', 0)} 行，{context.get('n_cols', 0)} 列{roles_hint}

只输出一个 Markdown 表格，不要任何说明文字。表格格式：
| 字段名 | 理解名称 | 含义理解 | 分析角色 |
| --- | --- | --- | --- |"""

        client = self._create_llm_client()
        response = client.chat.completions.create(
            model=self.llm_config.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=SCOUT_CONFIRM_TEMPERATURE,
            max_tokens=SCOUT_CONFIRM_MAX_TOKENS,
        )
        result = response.choices[0].message.content or ""

        # 提取思考标签外的内容（MiniMax 模型输出 <think>...</think>）
        result = re.sub(r'<think>.*?</think>\s*', '', result, flags=re.DOTALL).strip()

        return result.strip() if result.strip() else ""

    def _learn_from_results(self, context: dict, project_id: str | None) -> None:
        """将高置信度字段推断结果写入知识库"""
        if not project_id:
            return

        for sem in context["column_semantics"]:
            # 只学习高置信度且不需要用户确认的推断
            if sem.get("confidence", 0) < SCOUT_LEARN_CONFIDENCE_MIN or sem.get("needs_user_input"):
                continue
            col_name = sem["column_name"]
            if col_name not in context.get("column_descriptions", {}):
                continue
            desc = context["column_descriptions"][col_name]
            if not desc or not isinstance(desc, str) or not desc.strip():
                continue
            desc = desc.strip()
            # 检查是否已存在相似条目（通过 recall 确认）
            existing = scout_knowledge.recall(f"{col_name} {desc}", top_k=1)
            if existing and existing[0]["similarity"] > SCOUT_DEDUP_SIMILARITY:
                continue  # 已有相似条目，跳过
            scout_knowledge.learn(
                field=desc,
                meaning=desc,
                data_pattern=f"{sem['inferred_type']} {sem['evidence']}",
                inferred_role=sem.get("suggested_role", "feature"),
                confidence=sem.get("confidence", SCOUT_LEARN_CONFIDENCE_MIN),
                tags=[sem["inferred_type"], sem.get("suggested_role", "feature")],
                metadata={"project": project_id},
            )

    def _update_own_memory(self, context: dict, project_id: str | None) -> None:
        """更新自身记忆中的字段定义"""
        if not project_id:
            return

        # 确保 fields 是 dict（YAML 中 `fields:` 无值时读出 None）
        if not isinstance(self.memory.get("fields"), dict):
            self.memory["fields"] = {}

        # 合并新理解的字段
        for col, desc in context.get("column_descriptions", {}).items():
            if col not in self.memory["fields"]:
                self.memory["fields"][col] = desc

        # 保存
        self._save_memory()

    def _create_llm_client(self):
        """创建 LLM 客户端（通过工厂函数，确保 instructor 包装和代理清理）"""
        if self._llm_client is not None:
            return self._llm_client
        from ...llm.client import create_raw_client
        return create_raw_client(self.llm_config)


    # ── 对话接口（供 UI 调用） ──────────────────────────────

    def confirm_field(self, column: str, description: str) -> None:
        """用户确认字段含义后，更新记忆"""
        if "fields" not in self.memory:
            self.memory["fields"] = {}
        self.memory["fields"][column] = description
        self._save_memory()
