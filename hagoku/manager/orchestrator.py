"""HaGoKu Studio Manager — 编排器：LLM 决策驱动，代码构建通道"""

from __future__ import annotations

import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from ..agents.analyst import AnalystAgent
from ..agents.cleaner import CleanerAgent
from ..agents.reporter import ReporterAgent
from ..agents.scout import ScoutAgent
from ..config import HaGoKuConfig
from ..guardrails.statistical import StatisticalGuardrails
from ..llm.client import create_deep_client, create_quick_client, create_raw_client, create_structured_llm_client
from ..observability.display import TerminalDisplay
from ..observability.event_bus import EventBus
from ..observability.events import EventType
from ..storage.database import HaGoKuDB
from ..storage.kanban import KanbanDB
from ..storage.memory import MemoryManager
from ..storage.output import OutputManager
from ..storage.project_manager import ProjectManager
from ..tools.data_io import save_data

from .command_parser import parse as parse_command, ParsedCommand

# ── 规则引擎 ──────────────────────────────────────────────────

# WebSocket「重置 / 取消」暂停时使用的哨兵（用户正常回复不会使用此串）
# 律 3：多轮对话历史窗口 — 注入轮数 vs 持久化轮数（1 轮 = user + assistant 两条消息）
_CONV_HISTORY_INJECT_TURNS = 3   # 注入到 LLM prompt 的最近轮数
_CONV_HISTORY_KEEP_TURNS = 10    # context 中保留的最近轮数

# ── CH-5 拆分：从子模块重导出，保持外部 import 路径不变 ─────────

from .payloads.scout_payload import (  # noqa: F401 — 供类内方法使用 + 外部测试导入
    _expand_column_range,
    _known_scout_columns,
    _md_table_cell,
    _resolve_scout_column_token,
    _resolve_scout_column_token_with_context,
    _scout_ai_meaning_cell,
    _scout_chinese_display_cell,
    _scout_description_is_meaningful_for_user,
    _scout_display_name_cell,
    _scout_second_column_cell,
    _scout_semantic_fallback_label,
    _try_parse_json,
    scout_field_review_pause_payload,
    scout_user_input_received_payload,
)

from .payloads.cleaner_payload import (  # noqa: F401
    _cleaning_quality_display,
    _normalize_cleaning_operation,
    cleaning_review_pause_payload,
)

from .llm_dispatch.scout_reply import (  # noqa: F401
    _SCOUT_FIELD_UPDATE_TOOLS,
    _apply_role_update,
    _apply_restrict_analysis_to,
    _apply_scout_reply_with_llm,
    _get_scout_tools,
    _resolve_to_column_names,
    apply_scout_user_field_reply_to_context,
)


from .llm_dispatch.plan_generation import (  # noqa: F401
    _build_analysis_purpose,
    _describe_intent,
    _get_upstream_summary,
    _parse_user_query,
)

from .llm_dispatch.confirmation import (  # noqa: F401
    _apply_field_corrections,
    _build_intent_context,
    _llm_classify_confirmation,
    _request_field_confirmation,
)

from .llm_dispatch.reply_handlers import (  # noqa: F401
    _ensure_memory_for_respond,
    _handle_analyst_reply,
    _handle_cleaner_reply,
    _handle_reporter_reply,
    _handle_scout_reply,
    respond,
)

from .payloads.pipeline_helpers import (  # noqa: F401
    _attach_pause_dialogue_message,
    _check_mandatory_guardrails,
    _finish_run_cancelled,
    _handle_command_if_present,
    _handle_mandatory_violations,
    _init_pipeline_tasks,
)

class Orchestrator:
    _STAGE_HANDLERS: dict[str, str] = {
        "scout": "_handle_scout_reply",
        "cleaner": "_handle_cleaner_reply",
        "analyst": "_handle_analyst_reply",
        "reporter": "_handle_reporter_reply",
    }

    """HaGoKu Studio 编排器：规则+AI 双驱动，协调四个 Agent"""

    def __init__(self, config: HaGoKuConfig | None = None) -> None:
        self.config = config or HaGoKuConfig.load()
        self.config.ensure_work_dir()

        # 核心组件
        self.event_bus = EventBus()
        self.db = HaGoKuDB.get_instance(self.config.work_dir / "hagoku.db")
        self.display = TerminalDisplay(verbosity="normal")
        self.output_mgr: OutputManager | None = None  # 按项目初始化
        self.memory: MemoryManager | None = None  # 按项目初始化
        self.project_mgr = ProjectManager(self.config.output.project_dir)  # 全局项目管理器

        # 订阅显示
        self.event_bus.subscribe(self.display)

        # 护栏
        self.guardrails = StatisticalGuardrails()

        # LLM 客户端（懒初始化，pure_rule 模式永远不会触发）
        self._llm_client: Any | None = None
        self._llm_deep: Any | None = None  # 深度推理客户端（懒初始化）
        self._llm_quick: Any | None = None  # 快速客户端（懒初始化，instructor 包装）
        self._llm_quick_raw: Any | None = None  # 快速原始客户端（非 instructor 包装）

        # 设置模块级配置
        from ..tools.analysis import set_analysis_config
        from ..tools.cleaning import set_cleaning_config
        set_analysis_config(self.config.analysis)
        set_cleaning_config(self.config.cleaning)

        # 交互式暂停机制（分析线程用 Event 等待用户回复）
        # 用户请求中止本轮分析（WebSocket cancel_analysis）
        self._cancel_lock = threading.Lock()
        self._cancel_requested_flag = False
        # 事件驱动状态机字段
        self._stage: str = ""
        self._df_clean: pd.DataFrame | None = None
        self._df_raw: pd.DataFrame | None = None
        self._analyst_messages: list[dict] = []
        self._analyst_agent: Any = None
        self._analyst_first_pass_done: bool = False
        self._cleaner_agent: Any = None
        self._cleaner_messages: list[dict] = []
        self._cleaner_dialog_open: bool = False
        self._error: Exception | None = None


    @property
    def llm_deep(self) -> Any:
        """深度推理客户端（懒初始化）"""
        if self._llm_deep is None:
            self._llm_deep = create_deep_client(self.config)
        return self._llm_deep

    @property
    def llm_quick(self) -> Any:
        """快速客户端（懒初始化，instructor 包装，用于结构化输出）"""
        if self._llm_quick is None:
            self._llm_quick = create_quick_client(self.config)
        return self._llm_quick

    @property
    def llm_quick_raw(self) -> Any:
        """快速原始客户端（懒初始化，非 instructor 包装，用于 _apply_scout_reply_with_llm 等 JSON-only 调用）"""
        if self._llm_quick_raw is None:
            self._llm_quick_raw = create_raw_client(self.config)
        return self._llm_quick_raw

    def _reset_run_state(self) -> None:
        """新一轮分析前清理上次残留。"""
        self._stage = ""
        self._df_clean = None
        self._df_raw = None
        self._analyst_messages = []
        self._analyst_agent = None
        self._analyst_first_pass_done = False
        self._cleaner_agent = None
        self._cleaner_messages = []
        self._cleaner_dialog_open = False
        self._error = None

    def request_cancel(self) -> None:
        """前端「重置分析」：设置取消标志。"""
        with self._cancel_lock:
            self._cancel_requested_flag = True

    def _is_cancel_requested(self) -> bool:
        with self._cancel_lock:
            return self._cancel_requested_flag

    def run(
        self,
        data_path: str,
        query: str = "",
        *,
        project_name: str | None = None,
        output_dir: str | None = None,
        formats: list[str] | None = None,
        template: str | None = None,
        resume: bool = False,
        progress_path: str | None = None,
    ) -> dict[str, Any]:
        """
        主入口：Scout 字段理解。后续阶段通过 respond() 事件驱动。

        Args:
            data_path: 数据文件路径
            query: 用户的分析问题
            project_name: 项目名（默认从文件名推断）
            output_dir: 自定义输出目录
            formats: 报告输出格式
            template: 报告模板 (default/academic/brief/business_analysis/ab_test/executive_brief/data_audit)
            resume: 是否从上次断点继续
            progress_path: 外部 progress.yaml 路径

        Returns:
            运行结果摘要。
            `scout_confirm` / `cleaner_strategy` / `analyst_preliminary` 等阶段返回值。
        """
        run_start = datetime.now()

        # 1. 创建项目
        if project_name is None:
            project_name = Path(data_path).stem.replace(" ", "_")

        self.event_bus.emit(EventType.RUN_STARTED, "manager", {
            "query": query,
            "project": project_name,
        })

        self.output_mgr = OutputManager(self.config.output, project_name)
        schema_file = self.output_mgr.project_dir / "progress.yaml"
        self.memory = MemoryManager(self.db, progress_path=schema_file)

        # ── 持久 context 引用（必修 3）：Scribe 初始化前声明 ──
        context: dict[str, Any] = {}

        # 初始化 kanban 状态机（Step 4：从 Scribe 迁移到 Orchestrator 内部）
        self.kanban = KanbanDB.get_instance(self.output_mgr.project_dir)
        self.event_bus.subscribe(self._on_event)
        self._init_pipeline_tasks()

        # 处理 --progress 参数
        if progress_path:
            n = self.memory.import_progress_yaml(project_name, Path(progress_path))
            if n > 0:
                self.event_bus.emit(EventType.AGENT_THINKING, "manager", {
                    "thought": f"📄 导入了 {n} 条进度定义",
                })

        run_dir = self.output_mgr.create_run_dir()
        run_id = run_dir.name

        # ── LLM dump：设置当前 run 的 dump 目录（CH-4：观察通道四合一）──
        from ..observability.llm_dump import set_run_dir
        set_run_dir(run_dir)

        # ── ProjectContext：统一上下文记忆系统（阶段1：并行旧路径）──
        from ..context.project_context import ProjectContext
        self._project_context = ProjectContext(
            run_id=run_id,
            analysis_goal=query,
        )
        self._project_context.subscribe(self.event_bus, context_ref=context)

        # ── 持久化路径（阶段 3：crash 恢复）──
        self._project_context._save_path = str(run_dir / "project_context.jsonl")

        # ── 通道日志：初始化 ChannelLogger ──
        from ..observability.channel_logger import ChannelLogger
        self._channel_logger = ChannelLogger(run_dir)
        self._channel_logger.log("orchestrator", "run_start", query=query, project=project_name, run_id=run_id)

        with self._cancel_lock:
            self._cancel_requested_flag = False
        # 事件驱动状态机字段
        self._project_name = project_name
        self._stage: str = ""
        self._df_clean: pd.DataFrame | None = None
        self._df_raw: pd.DataFrame | None = None
        self._analyst_messages: list[dict] = []
        self._analyst_agent: Any = None
        self._error: Exception | None = None


        # 创建数据库记录
        self.db.create_project(project_name, data_path=data_path)

        # 1.5 解析用户查询 — 理解用户真正想问什么
        parsed_intent = self._parse_user_query(query)
        self.event_bus.emit(EventType.AGENT_THINKING, "manager", {
            "thought": f"🔍 收到，启动分析，让我来{self._describe_intent(parsed_intent)}",
        })

        # 2. 创建分析计划
        plan = self._create_plan(query, parsed_intent=parsed_intent)
        # 与 HaGoKuDB.create_run 默认一致；仅为 runs 表元数据，非面向用户的模式档位
        self.db.create_run(run_id, project_name, query=query, plan=plan, manager_mode="balanced")

        # 初始化 Agent（Step 4：Scribe 类已删，agent 不再接收 scribe= 参数）
        # 双层 LLM 策略：Scout/Cleaner/Reporter 用 quick，Analyst 用 deep
        scout = ScoutAgent(self.config.llm, self.event_bus, orchestrator=self,
                           llm_client=self.llm_quick, channel_logger=self._channel_logger)
        cleaner = CleanerAgent(self.config.llm, self.event_bus, orchestrator=self,
                               llm_client=self.llm_quick)
        analyst = AnalystAgent(self.config.llm, self.event_bus, orchestrator=self,
                               llm_client=self.llm_deep)
        reporter = ReporterAgent(self.config.llm, self.event_bus, orchestrator=self,
                                 llm_client=self.llm_quick_raw)

        # Resume 支持
        df_clean = None
        cleaning_report = None
        cleaned_path_str = ""

        if resume:
            state = self.memory.get_resume_state(project_name)
            if state and state["stage"] in ("cleaned", "analyzed", "reported"):
                self.event_bus.emit(EventType.AGENT_THINKING, "manager", {
                    "thought": f"⏩ 从 {state['stage']} 阶段恢复，跳过 Scout 和 Cleaner",
                })
                # 恢复上下文
                if state.get("context") and isinstance(state["context"], dict):
                    context.update(state["context"])
                # 加载清洗后数据
                if state.get("cleaned_path"):
                    import pandas as pd
                    cleaned_path_str = state["cleaned_path"]
                    if Path(cleaned_path_str).exists():
                        df_clean = pd.read_parquet(cleaned_path_str)


        try:
            # Scout + Cleaner（如果不是 resume）
            if not context:
                # 3. Scout: 数据侦察
                # 加载项目历史记忆，避免用户重复回答字段含义
                memory_project = self.memory.build_memory_project(project_name) if self.memory else None
                scout.memory_project = memory_project
                result = scout.run(
                    data_path, query, project_id=project_name, emit_completed=False,
                    memory_project=memory_project,
                )
                context.update(result)
                # ── 补录初始 Scout 快照（AGENT_COMPLETED 在 scout.run() 内部已触发，
                #     此时 _context_ref 为空，snapshot 丢失；context.update 后显式补录）──
                if hasattr(self, '_project_context') and self._project_context is not None:
                    self._project_context.add_agent_response(
                        stage="scout",
                        revision=0,
                        content=f"字段推断完成：理解 {len(context.get('column_semantics', []))} 个字段",
                        snapshot=self._project_context._derive_snapshot(context),
                    )
                if context.get("error"):
                    raise RuntimeError(str(context["error"]))

                if self._is_cancel_requested():
                    return self._finish_run_cancelled(run_id, project_name, run_start, run_dir)

                # ── 多轮对齐：Scout 字段理解子状态机 ───────────────────────────────
                # 结构：外层循环（Scout 循环 + gate）；内层 Scout 循环负责字段对齐
                # 对齐条件：用户纯确认  OR  所有字段 needs_user_input=False
                # 对齐后发 gate_to_cleaning 暂停；用户「还有补充」→ 回 Scout 内层循环；纯确认 → 进 Cleaner
                interaction_revision = 0
                # ── 注入 ProjectContext 到 context ──
                context["_project_context"] = getattr(self, '_project_context', None)

                # 事件驱动：emit 字段表 + 保存状态 + 返回（不阻塞）
                self._stage = "scout"
                self._context = context
                from hagoku.tools.data_io import load_data as _load
                _df = _load(data_path)
                self._df_clean = _df
                self._df_raw = _df
                scout_msg = scout_field_review_pause_payload(context)
                scout_msg["interaction_revision"] = interaction_revision
                scout_msg = self._attach_pause_dialogue_message("scout", scout_msg)
                # USER_INPUT_REQUESTED 由 _handle_scout_reply 空输入分支统一 emit，
                # 避免此处与 respond() 重复发送导致前端双倍渲染
                # AGENT_COMPLETED 不在此处发——Scout 在用户确认前不应标记"完成"
                # 用户确认进入下一阶段时由 _handle_scout_reply 切 Cleaner 后发

                return {
                    "status": "scout_review",
                    "message": "字段理解完成",
                    "phase": "scout",
                }


        except Exception as e:
            duration_ms = int((datetime.now() - run_start).total_seconds() * 1000)
            self.db.fail_run(run_id, duration_ms=duration_ms)
            self.event_bus.emit(EventType.RUN_FAILED, "manager", {"error": str(e)})
            raise

    def _create_plan(
        self,
        query: str,
        parsed_intent: Any | None = None,
    ) -> dict[str, Any]:
        """创建分析计划：LLM 唯一决策引擎，零硬编码规则。"""
        try:
            return self._call_llm_for_plan(query, parsed_intent=parsed_intent)
        except RuntimeError:
            self.event_bus.emit(EventType.AGENT_THINKING, "manager", {
                "thought": "LLM 计划生成失败：LLM 不可达，请检查 API 配置后重试。",
            })
            raise

    def _call_llm_for_plan(
        self,
        query: str,
        parsed_intent: Any | None = None,
    ) -> dict[str, Any] | None:
        """LLM 驱动的分析计划生成（唯一路径）。

        Returns:
            计划 dict，LLM 失败时返回 None。
        """
        from ..llm.plan_schema import (
            DEFAULT_EXPLORATORY_FOCUS,
            VALID_ANALYST_FOCUS,
            LLMPlanResponse,
        )
        from ..llm.prompts import PLAN_GENERATION_SYSTEM, PLAN_GENERATION_USER

        try:
            if self._llm_client is None:
                self._llm_client = create_structured_llm_client(self.config.llm)

            intent_context = self._build_intent_context(query, parsed_intent)
            messages = [
                {"role": "system", "content": PLAN_GENERATION_SYSTEM},
                {"role": "user", "content": PLAN_GENERATION_USER.format(query=intent_context)},
            ]

            response: LLMPlanResponse = self._llm_client.chat.completions.create(
                model=self.config.llm.model,
                messages=messages,
                response_model=LLMPlanResponse,
                temperature=self.config.llm.temperature,
                max_tokens=self.config.llm.max_tokens,
                timeout=30,
            )

            validated_focus = [f for f in response.analyst_focus if f in VALID_ANALYST_FOCUS]
            if not validated_focus:
                validated_focus = DEFAULT_EXPLORATORY_FOCUS.copy()

            agents = list(response.agents)
            if "scout" not in agents:
                agents.insert(0, "scout")
            if "reporter" not in agents:
                agents.append("reporter")

            plan = {
                "plan_name": response.plan_name,
                "agents": agents,
                "analyst_focus": validated_focus,
                "target": response.target,
                "query": response.query,
                "reasoning": response.reasoning,
                "llm_generated": True,
            }
            self.event_bus.emit(EventType.PLAN_CREATED, "manager", {
                "source": "llm",
                "plan_name": plan["plan_name"],
                "reasoning": plan.get("reasoning", ""),
            })
            return plan

        except Exception as e:
            raise RuntimeError(
                f"Manager LLM 计划生成失败：LLM 不可达，请检查配置。原始错误: {e}"
            ) from e

    def _persist_scout_field_updates(
        self,
        project_name: str,
        applied_scout: list[str],
        context: dict[str, Any],
    ) -> None:
        """
        将用户在 Scout 字段核对中的字段理解回复持久化到项目记忆。

        从 `applied_scout`（如 "Code←店铺编号"）中提取字段名与含义，
        通过 MemoryManager.persist_field_descriptions() 写入 SQLite + YAML。
        下次同一项目分析时，这些字段理解会被重新加载，避免重复询问。
        """
        if not self.memory or not applied_scout or not context:
            return

        descs: dict[str, Any] = context.get("column_descriptions", {}) or {}
        display_names: dict[str, Any] = context.get("column_display_names", {}) or {}
        new_descs: dict[str, str] = {}
        new_dnames: dict[str, str] = {}

        # 只持久化用户确认过的字段（律 10）：跳过 LLM 初始推断的
        confirmed_cols = {
            str(s.get("column_name", ""))
            for s in context.get("column_semantics", [])
            if s.get("confirmed_by_user")
        }

        for a in applied_scout:
            if not a or "←" not in a:
                continue
            # 格式: "col←desc" 或 "col:[display]←中文名"
            col_part, _, val = a.partition("←")
            col = col_part.strip()
            val = val.strip()
            if not col or not val:
                continue

            # 不持久化 used_in_analysis 和 role（当次分析特有，非字段描述）
            if ':[used_in_analysis]' in col or ':[role]' in col:
                continue

            # 跳过非用户确认的字段（律 10）
            pure_col = col.replace(":[display]", "").strip() if ":[display]" in col else col
            if pure_col not in confirmed_cols:
                continue

            if col.endswith(":[display]"):
                col = col.replace(":[display]", "").strip()
                new_dnames[col] = val
            else:
                new_descs[col] = val

        # 补充 context 中已有的 column_descriptions（不上覆盖的应用字段）
        full_descs: dict[str, str] = {}
        for col, d in descs.items():
            if isinstance(d, str) and d.strip():
                full_descs[str(col)] = str(d).strip()
        full_descs.update(new_descs)

        if full_descs:
            self.memory.persist_field_descriptions(
                project_name, full_descs, column_display_names=new_dnames,
            )

    def _on_event(self, event) -> None:
        """统一事件处理器，Step 4 仅处理 3 个影响 kanban 状态的事件。"""
        etype = event.event_type
        if etype == EventType.AGENT_STARTED:
            self._on_agent_started(event)
        elif etype == EventType.AGENT_COMPLETED:
            self._on_agent_completed(event)
        elif etype == EventType.AGENT_FAILED:
            self._on_agent_failed(event)

    def _on_agent_started(self, event) -> None:
        agent = event.agent
        goal = event.data.get("goal", "")
        # 优先复用 _init_pipeline_tasks 创建的任务（状态为 ready）
        ready_task = self.kanban.get_ready_task(agent.lower())
        if ready_task:
            ok = self.kanban.claim_task(ready_task["id"], f"{agent.lower()}_agent")
            if not ok:
                pass  # claim failed, task already taken
        else:
            task = self.kanban.get_active_task(agent.lower())
            if not task:
                task_id = self.kanban.create_task(
                    agent=agent.lower(),
                    title=f"{agent}: {goal}",
                    description=f"Started at {datetime.now().strftime('%H:%M:%S')}",
                )
                self.kanban.update_status(task_id, "todo")
                self.kanban.update_status(task_id, "ready")

    def _on_agent_completed(self, event) -> None:
        agent = event.agent
        result = event.data.get("result_summary", "")
        lock_holder = f"{agent.lower()}_agent"
        self.kanban.complete_agent_task_atomic(
            agent=agent.lower(),
            lock_holder=lock_holder,
            result=result,
        )
        # 自动 promote 下游任务
        self._auto_promote_next(agent)

    def _on_agent_failed(self, event) -> None:
        agent = event.agent
        error = event.data.get("error", "")
        task = self.kanban.get_active_task(agent.lower())
        if task and task["status"] == "running":
            self.kanban.update_status(task["id"], "blocked")
            self.kanban.add_comment(task["id"], "system", f"Failed: {error}")

    def _auto_promote_next(self, agent: str) -> None:
        """上游 Agent 完成后，自动 promote 下游任务为 ready。

        Scout done → Cleaner ready
        Cleaner done → Analyst ready
        Analyst done → Reporter ready
        Reporter done → Pipeline 完成（所有任务 done）
        """
        pipeline = ["scout", "cleaner", "analyst", "reporter"]
        try:
            idx = pipeline.index(agent.lower())
        except ValueError:
            return

        downstream = pipeline[idx + 1] if idx + 1 < len(pipeline) else None
        if downstream is None:
            # Reporter 完成 → 所有任务完成
            for ag in pipeline:
                task = self.kanban.get_any_task(ag)
                if task and task["status"] != "done":
                    self.kanban.update_status(task["id"], "done")
            return

        # Promote 下游任务
        task = self.kanban.get_any_task(downstream)
        if task and task["status"] in ("todo", "triage"):
            self.kanban.update_status(task["id"], "ready")

    def block_task(self, agent_name: str, reason: str) -> bool:
        """Block 指定 Agent 的任务（等用户输入）。

        Step 4 起：4 agent 直接调本方法（不再经 Scribe）。
        """
        if not hasattr(self, "kanban") or self.kanban is None:
            return False
        task = self.kanban.get_active_task(agent_name.lower())
        if not task:
            return False
        return self.kanban.block_task(task["id"], reason)

    def unblock_task(self, agent_name: str) -> bool:
        """Unblock 指定 Agent 的任务。Step 1 内联：直接走 kanban。"""
        if not hasattr(self, "kanban") or self.kanban is None:
            return False
        task = self.kanban.get_active_task(agent_name.lower())
        if not task:
            return False
        return self.kanban.unblock_task(task["id"])

    def _save_field_descriptions(
        self,
        project_name: str,
        corrections: dict[str, dict[str, str]],
    ) -> None:
        """保存用户确认的字段描述到 memory/progress.yaml"""
        if not corrections:
            return

        if self.output_mgr is None:
            self.output_mgr = OutputManager(self.config.output, project_name)

        try:
            # 构建 schema 更新
            schema_file = self.output_mgr.project_dir / "progress.yaml"
            import yaml

            # 读取现有 schema
            schema_data: dict[str, Any] = {}
            if schema_file.exists():
                with open(schema_file, "r", encoding="utf-8") as f:
                    schema_data = yaml.safe_load(f) or {}

            if "columns" not in schema_data:
                schema_data["columns"] = {}

            # 更新 columns
            for col, info in corrections.items():
                if col not in schema_data["columns"]:
                    schema_data["columns"][col] = {}
                schema_data["columns"][col]["description"] = f"{info['chinese_name']}（{info['business_meaning']}）"

            # 写回 progress.yaml
            schema_file.parent.mkdir(parents=True, exist_ok=True)
            with open(schema_file, "w", encoding="utf-8") as f:
                yaml.dump(schema_data, f, allow_unicode=True, default_flow_style=False)

        except Exception as e:
            # 保存失败不影响主流程，只打印警告
            print(f"   ⚠️ 保存字段描述失败: {e}")


# ── CH-5 方法委托：将提取的实例方法挂回 Orchestrator ─────────

Orchestrator._parse_user_query = _parse_user_query
Orchestrator._describe_intent = _describe_intent
Orchestrator._build_analysis_purpose = _build_analysis_purpose
Orchestrator._get_upstream_summary = _get_upstream_summary
Orchestrator._llm_classify_confirmation = _llm_classify_confirmation
Orchestrator._build_intent_context = _build_intent_context
Orchestrator._request_field_confirmation = _request_field_confirmation
Orchestrator._apply_field_corrections = _apply_field_corrections
Orchestrator._handle_scout_reply = _handle_scout_reply
Orchestrator._handle_cleaner_reply = _handle_cleaner_reply
Orchestrator._handle_analyst_reply = _handle_analyst_reply
Orchestrator._handle_reporter_reply = _handle_reporter_reply
Orchestrator.respond = respond
Orchestrator._ensure_memory_for_respond = _ensure_memory_for_respond
Orchestrator._check_mandatory_guardrails = _check_mandatory_guardrails
Orchestrator._handle_mandatory_violations = _handle_mandatory_violations
Orchestrator._finish_run_cancelled = _finish_run_cancelled
Orchestrator._handle_command_if_present = _handle_command_if_present
Orchestrator._init_pipeline_tasks = _init_pipeline_tasks
Orchestrator._attach_pause_dialogue_message = _attach_pause_dialogue_message
