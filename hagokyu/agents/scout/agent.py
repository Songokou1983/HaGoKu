"""
Scout Agent — 数据侦察员

从 prompt.md 读取角色定义，从 memory.md 读取/保存记忆
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import yaml

from . import knowledge as scout_knowledge

from ...config import LLMConfig
from ...observability.event_bus import EventBus
from ...observability.events import EventType
from ...tools.data_io import load_data
from ...tools.profiling import generate_profile
from ..types import InteractionResult
from .._interactive import InteractionMixin


class ScoutAgent(InteractionMixin):
    """数据侦察员：理解数据上下文，不猜，问"""

    def __init__(
        self,
        llm_config: LLMConfig,
        event_bus: EventBus,
        scribe: "ScribeAgent | None" = None,
    ) -> None:
        self.role = "scout"
        self.llm_config = llm_config
        self.event_bus = event_bus
        self.scribe = scribe  # 可选，用于看板 block/unblock

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

        # 更新 fields 部分
        fields_yaml = yaml.dump(self.memory.get("fields", {}), default_flow_style=False, allow_unicode=True)

        # 替换 memory.md 中的 fields 部分
        pattern = r"```yaml\nfields:.*?\n```"
        if re.search(pattern, content, re.DOTALL):
            content = re.sub(pattern, f"```yaml\nfields:\n{fields_yaml}```", content, flags=re.DOTALL)
        else:
            # 找到 fields: {} 行，替换
            content = re.sub(r"fields: \{\}", f"fields:\n{fields_yaml}", content)

        path.write_text(content, encoding="utf-8")

    def _emit(self, event_type: EventType, data: dict = None) -> None:
        self.event_bus.emit(event_type=event_type, agent=self.role, data=data or {})

    # ── 核心逻辑 ────────────────────────────────────────────

    def run(
        self,
        data_path: str,
        query: str = "",
        project_id: str | None = None,
        memory_project: dict | None = None,
    ) -> dict:
        """
        执行数据侦察

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

    def begin(
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

            self._context = context
            self._phase = "confirm_fields"

            # 需要用户确认的字段
            uncertain = [s for s in context["column_semantics"] if s.get("needs_user_input")]
            if uncertain:
                # block 看板，等用户确认
                if self.scribe:
                    self.scribe.block_task("scout", "等用户确认字段含义")
                self._emit(EventType.AGENT_THINKING, {"thought": f"识别 {len(uncertain)} 个字段需确认"})
                return self._pause(
                    phase="confirm_fields",
                    message="以下字段需要你确认理解是否正确：",
                    needs_confirmation=True,
                    confirmation_prompt="请逐个确认或修正字段含义",
                    pending_items=[
                        {
                            "column": s["column_name"],
                            "inferred_type": s["inferred_type"],
                            "confidence": s["confidence"],
                            "description": context["column_descriptions"].get(s["column_name"], ""),
                            "evidence": s.get("evidence", ""),
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

    def respond(
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

        uncertain = [s for s in self._context["column_semantics"] if s.get("needs_user_input")]
        summary = (
            f"已理解 {len(self._context['column_semantics'])} 个字段，"
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
                "n_cols": self._context["n_cols"],
                "n_rows": self._context["n_rows"],
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
        null_rate = series.isnull().mean()

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
            col = sem["column_name"]
            role = sem["suggested_role"]
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

            sample_val = ""
            try:
                vals = df[col].dropna().unique()
                if len(vals) > 0:
                    sample_val = str(list(vals[:5])).strip("[]")
            except Exception:
                pass

            field_specs.append(
                f"[{col}] 类型={sem['inferred_type']} 置信={sem['confidence']:.0%} "
                f"依据={sem['evidence']} 示例={sample_val if sample_val else '无'}"
            )

        if not field_specs:
            return

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

        client = self._create_llm_client()
        try:
            system_prompt = "你是专业数据分析师，对每个字段用20字以内描述。格式：字段名：描述"
            if knowledge_hint:
                system_prompt += f"\n\n{knowledge_hint}"
            response = client.chat.completions.create(
                model=self.llm_config.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"为以下字段生成描述：\n{field_block}"},
                ],
                temperature=0.3,
                max_tokens=500,
            )
            result = response.choices[0].message.content or ""
        except Exception:
            result = ""

        # 解析 LLM 输出
        for line in result.split("\n"):
            line = line.strip()
            if not line or "：" not in line:
                continue
            col_name, desc_text = line.split("：", 1)
            col_name = col_name.strip()
            desc_text = desc_text.strip()

            # 检查列名是否在上下文中
            if col_name in context["column_descriptions"]:
                continue

            # 找到对应的 sem
            for sem in context["column_semantics"]:
                if sem["column_name"] == col_name and sem["inferred_type"] != "unknown":
                    context["column_descriptions"][col_name] = desc_text
                    break

        # 兜底：未生成描述的字段
        type_map = {
            "numeric": "数值型",
            "categorical": "分类型",
            "datetime": "时间型",
            "id": "标识符",
            "text": "文本型",
            "boolean": "布尔型",
            "unknown": "未知类型",
        }
        for sem in context["column_semantics"]:
            col = sem["column_name"]
            if col not in context["column_descriptions"]:
                type_ch = type_map.get(sem["inferred_type"], sem["inferred_type"])
                context["column_descriptions"][col] = f"{col}（{type_ch}）"

    def _learn_from_results(self, context: dict, project_id: str | None) -> None:
        """将高置信度字段推断结果写入知识库"""
        if not project_id:
            return

        for sem in context["column_semantics"]:
            # 只学习高置信度且不需要用户确认的推断
            if sem.get("confidence", 0) < 0.85 or sem.get("needs_user_input"):
                continue
            if sem["column_name"] in context.get("column_descriptions", {}):
                desc = context["column_descriptions"][sem["column_name"]]
                # 检查是否已存在相似条目（通过 recall 确认）
                existing = scout_knowledge.recall(f"{sem['column_name']} {desc}", top_k=1)
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

        # 更新 fields
        if "fields" not in self.memory:
            self.memory["fields"] = {}

        # 合并新理解的字段
        for col, desc in context.get("column_descriptions", {}).items():
            if col not in self.memory["fields"]:
                self.memory["fields"][col] = desc

        # 保存
        self._save_memory()

    def _create_llm_client(self):
        """创建 LLM 客户端"""
        from ...llm.client import create_structured_llm_client
        return create_structured_llm_client(self.llm_config)

    # ── 对话接口（供 UI 调用） ──────────────────────────────

    def confirm_field(self, column: str, description: str) -> None:
        """用户确认字段含义后，更新记忆"""
        if "fields" not in self.memory:
            self.memory["fields"] = {}
        self.memory["fields"][column] = description
        self._save_memory()
