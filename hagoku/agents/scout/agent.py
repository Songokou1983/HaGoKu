"""
Scout Agent — 数据侦察员

从 prompt.md 读取角色定义，从 memory.md 读取/保存记忆
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .._scribe.agent import ScribeAgent

import numpy as np
import pandas as pd
import yaml

from ...config import LLMConfig
from ...observability.event_bus import EventBus
from ...observability.events import EventType
from ...tools.data_io import load_data
from ...tools.profiling import generate_profile
from .._interactive import InteractionMixin
from ..types import InteractionResult
from . import knowledge as scout_knowledge

# 与编排层展示过滤一致：不把「列名（统计类型）」当业务含义
_TYPE_ECHO_SUFFIXES: tuple[str, ...] = (
    "分类型",
    "数值型",
    "时间型",
    "文本型",
    "布尔型",
    "标识符",
    "未知类型",
)


def _description_is_user_facing_meaningful(col: str, desc: str) -> bool:
    d = (desc or "").strip()
    c = (col or "").strip()
    if not d or d == c:
        return False
    for suf in _TYPE_ECHO_SUFFIXES:
        for o, cl in (("（", "）"), ("(", ")")):
            if d == f"{c}{o}{suf}{cl}":
                return False
    return True


def _parse_llm_field_desc_line(raw: str) -> tuple[str, str] | None:
    """解析「列名：描述」行；兼容半角冒号、列表前缀、反引号。"""
    s = (raw or "").strip()
    if not s:
        return None
    s = re.sub(r"^[\-\*\•]\s*", "", s)
    s = re.sub(r"^\d+[\.)]\s*", "", s)
    if "：" in s:
        left, right = s.split("：", 1)
    elif ":" in s:
        idx = s.find(":")
        left, right = s[:idx], s[idx + 1 :]
        if len(left.strip()) > 64:
            return None
    else:
        return None
    col = left.strip().strip("`").strip()
    desc = right.strip()
    if not col or not desc:
        return None
    return col, desc


def _format_sample_preview(df: pd.DataFrame, col: str, *, limit: int = 5) -> str:
    """把样本值格式化成人类可读短串（去掉 np.float64 等噪音）。"""
    try:
        vals = df[col].dropna().unique()
    except Exception:
        return ""
    if len(vals) == 0:
        return ""
    parts: list[str] = []
    for v in vals[:limit]:
        try:
            if hasattr(v, "item") and callable(getattr(v, "item", None)):
                v = v.item()  # numpy scalar → Python
        except Exception:
            pass
        if isinstance(v, float):
            av = abs(v)
            if av != 0 and (av >= 1e6 or av < 1e-5):
                parts.append(f"{v:.3e}")
            else:
                s = f"{v:.6g}".rstrip("0").rstrip(".")
                parts.append(s or "0")
        elif isinstance(v, (int, np.integer)):
            parts.append(str(int(v)))
        else:
            s = str(v).strip()
            if len(s) > 20:
                s = s[:17] + "…"
            parts.append(s)
    return ", ".join(parts)


def _heuristic_column_business_hint(column_name: str, sample_preview: str) -> str:
    """LLM 未给出可用描述时的短保底：不出现统计类型词。"""
    c = (column_name or "").strip()
    low = c.lower()
    sp = (sample_preview or "").strip().replace("\n", " ")
    if len(sp) > 56:
        sp = sp[:53] + "…"

    parts: list[str] = []
    if low == "bu" or re.search(r"\bbu\b", low):
        parts.append("多为事业部/业务线")
    if "code" in low:
        parts.append("多为业务或主数据编码")
    if "period" in low:
        parts.append("多为账期/统计周期")
    if re.search(r"\binc\d*\b", low) or low.startswith("inc"):
        parts.append("多为收入侧指标")
    if re.search(r"\bbos\d*\b", low) or low.startswith("bos"):
        parts.append("多为支出/成本侧指标")
    if "date" in low or "time" in low:
        parts.append("多为日期/时间")
    if "id" in low and len(low) <= 32:
        parts.append("多为标识字段")

    core = "；".join(parts) if parts else "含义待你确认"

    if sp:
        return f"{core}（例：{sp}）"
    return core


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
            column_semantics = self._infer_all_semantics(df, query)

            # 4. 构建上下文
            context = {
                "data_path": data_path,
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
            column_semantics = self._infer_all_semantics(df, query)

            # 构建上下文
            context = {
                "data_path": data_path,
                "n_rows": len(df),
                "n_cols": len(df.columns),
                "column_semantics": column_semantics,
                "quality_score": profile["quality_score"],
                "missing_summary": profile.get("missing_summary", {}),
                "warnings": [],
                "column_descriptions": {},
            }

            # 应用项目记忆
            if memory_project and project_id:
                self._apply_project_memory(context, memory_project)

            # 派生字段角色
            self._derive_roles(context)

            # 生成字段描述
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

        # 更新 column_descriptions
        for col, desc in confirmed.items():
            self._context["column_descriptions"][col] = desc
        for col, desc in corrected.items():
            self._context["column_descriptions"][col] = desc

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

    def _infer_all_semantics(self, df: pd.DataFrame, query: str) -> list[dict]:
        """推断所有列的语义"""
        semantics = []
        target_keywords = self._extract_target_keywords(query)

        for col in df.columns:
            sem = self._infer_column(df[col], col, target_keywords)
            semantics.append(sem)

        return semantics

    def _infer_column(self, series: pd.Series, name: str, target_keywords: list) -> dict:
        """单列语义推断"""
        n_unique = series.nunique()
        n_total = len(series)

        # 100% 唯一 → ID
        if n_unique == n_total and n_total > 10:
            return {
                "column_name": name,
                "inferred_type": "id",
                "confidence": 0.95,
                "evidence": "100%唯一值",
                "needs_user_input": False,
                "suggested_role": "identifier",
            }

        # 日期
        if pd.api.types.is_datetime64_any_dtype(series):
            return {
                "column_name": name,
                "inferred_type": "datetime",
                "confidence": 0.95,
                "evidence": "日期类型",
                "needs_user_input": False,
                "suggested_role": "time_index",
            }

        # 布尔
        if n_unique == 2 and pd.api.types.is_numeric_dtype(series):
            vals = set(series.dropna().unique())
            if vals <= {0, 1} or vals <= {0.0, 1.0}:
                return {
                    "column_name": name,
                    "inferred_type": "boolean",
                    "confidence": 0.90,
                    "evidence": "二元数值(0/1)",
                    "needs_user_input": False,
                    "suggested_role": "binary_feature",
                }

        # 数值
        if pd.api.types.is_numeric_dtype(series):
            name_lower = name.lower()
            if any(kw in name_lower for kw in target_keywords):
                return {
                    "column_name": name,
                    "inferred_type": "target",
                    "confidence": 0.50,
                    "evidence": "列名含目标关键词",
                    "needs_user_input": True,
                    "suggested_role": "target",
                }

            # 高唯一值
            if n_unique > n_total * 0.8 and not pd.api.types.is_float_dtype(series):
                vals = series.dropna().sort_values()
                val_range = vals.max() - vals.min() + 1
                if val_range <= n_unique * 1.1:
                    return {
                        "column_name": name,
                        "inferred_type": "id",
                        "confidence": 0.60,
                        "evidence": f"高唯一值整数列 {n_unique}/{n_total}",
                        "needs_user_input": True,
                        "suggested_role": "identifier",
                    }

            return {
                "column_name": name,
                "inferred_type": "numeric",
                "confidence": 0.90,
                "evidence": "数值类型",
                "needs_user_input": False,
                "suggested_role": "numeric_feature",
            }

        # 类别
        if n_unique < 20:
            return {
                "column_name": name,
                "inferred_type": "categorical",
                "confidence": 0.70,
                "evidence": f"{n_unique}个唯一值",
                "needs_user_input": n_unique > 5,
                "suggested_role": "categorical_feature",
            }

        # 文本
        if n_unique > n_total * 0.5:
            avg_len = series.dropna().str.len().mean() if series.dtype == object else 0
            if avg_len > 50:
                return {
                    "column_name": name,
                    "inferred_type": "text",
                    "confidence": 0.60,
                    "evidence": "高唯一值比+长文本",
                    "needs_user_input": True,
                    "suggested_role": "text_feature",
                }

        return {
            "column_name": name,
            "inferred_type": "unknown",
            "confidence": 0.0,
            "evidence": "无法推断",
            "needs_user_input": True,
        }

    def _extract_target_keywords(self, query: str) -> list[str]:
        """从查询中提取目标变量关键词"""
        keywords = [
            "target", "y", "label", "revenue", "sales", "income",
            "profit", "cost", "price", "value", "amount",
            "收入", "销售额", "利润", "成本", "价格",
        ]
        if query:
            query_lower = query.lower()
            for kw in ["revenue", "sales", "income", "profit", "收入", "销售额", "利润"]:
                if kw in query_lower and kw not in keywords:
                    keywords.append(kw)
        return keywords

    def _apply_project_memory(self, context: dict, memory_project: dict) -> None:
        """应用项目记忆中的字段定义"""
        fields = memory_project.get("fields", {})
        if not fields:
            return

        # 从全局记忆加载字段描述
        for sem in context["column_semantics"]:
            col = sem["column_name"]
            if col in fields:
                context["column_descriptions"][col] = fields[col]
                sem["confidence"] = 1.0  # 记忆中的定义是高置信度

    def _derive_roles(self, context: dict) -> None:
        """从 column_semantics 推导 target/features"""
        features = []
        target = None
        variable_roles = {}

        for sem in context["column_semantics"]:
            col = sem.get("column_name", sem.get("column"))
            role = sem.get("suggested_role", "feature")
            variable_roles[col] = role

            if role in ("ignore", "identifier"):
                continue
            if role == "target" and not target:
                target = col
                continue
            features.append(col)

        context["target"] = target
        context["features"] = features
        context["variable_roles"] = variable_roles

    def _generate_field_descriptions(self, context: dict, df: pd.DataFrame) -> None:
        """用 LLM 批量生成字段描述（融入知识库经验）"""
        field_specs = []
        for sem in context["column_semantics"]:
            col = sem["column_name"]
            if col in context["column_descriptions"]:
                continue  # 已有描述不覆盖

            sample_val = _format_sample_preview(df, col)

            field_specs.append(
                f"[{col}] 类型={sem['inferred_type']} 置信={sem['confidence']:.0%} "
                f"依据={sem['evidence']} 示例={sample_val if sample_val else '无'}"
            )

        if not field_specs:
            return

        self._emit(EventType.AGENT_THINKING, {
            "thought": "正在调用模型生成字段业务含义（列数较多时可能需数十秒）…",
        })

        field_block = "\n".join(field_specs)

        # 检索相关字段知识（用于增强 LLM 上下文）
        type_tags = list({s["inferred_type"] for s in context["column_semantics"]})
        query = f"{' '.join(type_tags)} {' '.join([s['column_name'] for s in context['column_semantics'][:5]])}"
        recalled = scout_knowledge.recall(query, top_k=3)
        if recalled:
            knowledge_hint = "参考经验：\n" + "\n".join(
                f"- {r['content']}（置信{r['metadata'].get('confidence', 'N/A')}）"
                for r in recalled
            )
        else:
            knowledge_hint = ""

        system_prompt = (
            "你是专业数据分析师，为每个字段写一句**业务向**的中文（建议 12–28 字）。\n"
            "要求：结合列名、示例猜测「这列在业务里可能表示什么」；面向业务同事。\n"
            "禁止：写「数值型/分类型/未知类型」等统计用词；禁止只输出「字段名（类型）」或只重复英文列名。\n"
            "若不确定，也要写「可能表示…」并点出你从样本里看到的现象（如金额大小、是否像编码）。\n"
            + (f"\n{knowledge_hint}" if knowledge_hint else "")
            + "\n\n每行**严格**使用格式：`字段名：理解名称｜含义理解`（全角冒号、全角竖线「｜」）。\n"
            "「理解名称」≤12 字，为后续表格第二列的简短业务称呼；「含义理解」为第三列的一句话（可含（例：…）样本片段）。\n"
            "不要 Markdown 表格，不要编号；每行只写一列字段。"
        )
        max_out = min(max(self.llm_config.max_tokens, 512), 1600)
        model_name = self.llm_config.model_quick or self.llm_config.model

        client = self._create_llm_client()
        result = ""
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"为以下字段生成描述：\n{field_block}"},
                ],
                temperature=0.3,
                max_tokens=max_out,
            )
            result = response.choices[0].message.content or ""
        except Exception:
            result = ""

        known_cols = {sem["column_name"] for sem in context["column_semantics"]}
        # 解析 LLM 输出
        for line in result.split("\n"):
            parsed = _parse_llm_field_desc_line(line)
            if not parsed:
                continue
            col_name, desc_text = parsed
            if col_name not in known_cols:
                continue
            if col_name in context["column_descriptions"]:
                continue
            if _description_is_user_facing_meaningful(col_name, desc_text):
                if "｜" in desc_text:
                    left, sep, right = desc_text.partition("｜")
                    short_guess = left.strip()
                    long_guess = right.strip()
                    if sep and short_guess and long_guess:
                        context.setdefault("column_display_names", {})[col_name] = short_guess
                        desc_text = long_guess
                context["column_descriptions"][col_name] = desc_text

        # 仍为空的列：用语义缩写 + 样本做短保底
        context.setdefault("_field_desc_auto_columns", [])
        for sem in context["column_semantics"]:
            col = sem["column_name"]
            raw = str(context["column_descriptions"].get(col, "") or "").strip()
            if _description_is_user_facing_meaningful(col, raw):
                continue
            sample_val = _format_sample_preview(df, col)
            context["column_descriptions"][col] = _heuristic_column_business_hint(col, sample_val)
            context["_field_desc_auto_columns"].append(col)

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

        system_prompt = """你是一个数据分析助手，正在帮助用户理解数据字段的含义。

你的任务是：
1. 为每个字段生成三列信息：**字段名**（原始列名）、**理解名称**（后续展示用的简短业务称呼）、**含义理解**（业务含义一句话）
2. 确认完成后，告知用户如何继续：
   - 如果所有字段理解正确 → 用户可以输入"确认"继续下一步
   - 如果某个字段理解有误 → 用户会告诉你正确含义
   - 如果某字段完全不认识 → 用户会补充说明

重要规则：
- **字段名照抄原始列名**，不要翻译
- **理解名称要简短**（建议 ≤12 字），后续分析表格第二列会用到
- **含义理解**说明这个字段在业务中的具体含义"""

        user_prompt = f"""请为以下字段生成理解：

{fields_text}

数据概况：{context.get('n_rows', 0)} 行，{context.get('n_cols', 0)} 列

只输出一个 Markdown 表格，不要任何说明文字。表格格式：
| 字段名 | 理解名称 | 含义理解 |
| --- | --- | --- |"""

        client = self._create_llm_client()
        try:
            response = client.chat.completions.create(
                model=self.llm_config.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.5,
                max_tokens=1200,
            )
            result = response.choices[0].message.content or ""

            # 提取思考标签外的内容（MiniMax 模型输出 <think>...</think>）
            import re
            result = re.sub(r'<think>.*?</think>\s*', '', result, flags=re.DOTALL).strip()

            return result.strip() if result.strip() else "（字段理解生成失败）"
        except Exception:
            # LLM 失败时回退到简单消息
            return f"""数据包含 {len(column_semantics)} 个字段，请确认以下理解是否正确：

{fields_text}

确认流程：
- 如果所有字段理解正确 → 输入"确认"继续
- 如果某个字段理解有误 → 直接告诉我正确的含义，如"Inc1=销售额"或「理解名称｜含义理解」
- 如果某字段完全不理解 → 告诉我这个字段是什么意思"""

    def _learn_from_results(self, context: dict, project_id: str | None) -> None:
        """将高置信度字段推断结果写入知识库"""
        if not project_id:
            return

        for sem in context["column_semantics"]:
            # 只学习高置信度且不需要用户确认的推断
            if sem.get("confidence", 0) < 0.85 or sem.get("needs_user_input"):
                continue
            col_name = sem["column_name"]
            if col_name in context.get("_field_desc_auto_columns", []):
                continue
            if col_name not in context.get("column_descriptions", {}):
                continue
            desc = context["column_descriptions"][col_name]
            # 检查是否已存在相似条目（通过 recall 确认）
            existing = scout_knowledge.recall(f"{col_name} {desc}", top_k=1)
            if existing and existing[0]["similarity"] > 0.9:
                continue  # 已有相似条目，跳过
            scout_knowledge.learn(
                field=desc,
                meaning=desc,
                data_pattern=f"{sem['inferred_type']} {sem['evidence']}",
                inferred_role=sem.get("suggested_role", "feature"),
                confidence=sem.get("confidence", 0.85),
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
        """创建 LLM 客户端（原始 OpenAI，不走 instructor）"""
        if self._llm_client is not None:
            return self._llm_client
        from openai import OpenAI
        return OpenAI(
            base_url=self.llm_config.base_url,
            api_key=self.llm_config.api_key,
            timeout=120.0,
        )

    # ── 对话接口（供 UI 调用） ──────────────────────────────

    def confirm_field(self, column: str, description: str) -> None:
        """用户确认字段含义后，更新记忆"""
        if "fields" not in self.memory:
            self.memory["fields"] = {}
        self.memory["fields"][column] = description
        self._save_memory()
