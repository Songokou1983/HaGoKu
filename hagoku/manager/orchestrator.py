"""HaGoKu Studio Manager — 编排器：LLM 决策驱动，代码构建通道"""

from __future__ import annotations

import logging
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("hagoku.orchestrator")

from ..agents.agent import DataAnalystAgent
from ..config import HaGoKuConfig
from ..guardrails.statistical import StatisticalGuardrails
from ..llm.client import create_raw_client, create_structured_llm_client
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

# ── CH-5 拆分：从子模块重导出，保持外部 import 路径不变 ─────────

from .payloads.scout_payload import (  # noqa: F401 — 供类内方法使用 + 外部测试导入
    _expand_column_range,
    _known_scout_columns,
    _md_table_cell,
    _resolve_scout_column_token,
    _resolve_scout_column_token_with_context,
    _scout_description_is_meaningful_for_user,
    _try_parse_json,
    scout_user_input_received_state,
    derive_display_names,
    derive_descriptions,
    sync_legacy_dicts,
)

# Phase D 后：scout_reply 功能已迁入 agent.py + reply_handlers.py。
# 旧的 scout_reply.py 已删除。测试函数已迁移至 tests/helpers/scout_reply_legacy.py。
# 生产不再依赖任何 scout_reply 模块。

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
    ReplyHandlersMixin,
)

from .llm_dispatch.plan_generation import PlanGenerationMixin  # noqa: F401
from .llm_dispatch.confirmation import ConfirmationMixin  # noqa: F401
from .payloads.pipeline_helpers import PipelineHelpersMixin  # noqa: F401

from .payloads.pipeline_helpers import (  # noqa: F401
    _attach_pause_dialogue_message,
    _check_mandatory_guardrails,
    _finish_run_cancelled,
    _handle_command_if_present,
    _handle_mandatory_violations,
    _init_pipeline_tasks,
)

class Orchestrator(
    ReplyHandlersMixin,
    PlanGenerationMixin,
    ConfirmationMixin,
    PipelineHelpersMixin,
):
    """HaGoKu Studio 编排器：规则+AI 双驱动，协调四个 Agent"""

    def _log_channel(self, agent: str, event: str, **kw: Any) -> None:
        """通道日志——记录每个关键决策点。"""
        try:
            cl = getattr(self, "_channel_logger", None)
            if cl: cl.log(agent, event, **kw)
        except Exception: pass

    _STAGE_HANDLERS: dict[str, str] = {
        "scout": "_handle_scout_reply",
        "cleaner": "_handle_cleaner_reply",
        "analyst": "_handle_analyst_reply",
        "reporter": "_handle_reporter_reply",
    }

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
        self._llm: Any | None = None  # 统一结构化客户端
        self._llm_raw: Any | None = None  # 原始客户端

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
        self._analyst_agent: Any = None
        self._analyst_first_pass_done: bool = False
        self._cleaner_agent: Any = None
        self._cleaner_dialog_open: bool = False
        self._reporter_agent: Any = None
        self._error: Exception | None = None


    @property
    def llm_deep(self) -> Any:
        """深度推理客户端（懒初始化）"""

    @property
    def llm_quick(self) -> Any:
        """快速客户端（懒初始化，instructor 包装，用于结构化输出）"""


    @property
    def llm(self) -> Any:
        """统一结构化 LLM 客户端（instructor 包装）。"""
        if self._llm is None:
            self._llm = create_structured_llm_client(self.config.llm)
        return self._llm

    @property
    def llm_raw(self) -> Any:
        """原始客户端（非 instructor 包装，用于 JSON-only 调用）。"""
        if self._llm_raw is None:
            self._llm_raw = create_raw_client(self.config.llm)
        return self._llm_raw

    def _reset_run_state(self) -> None:
        """新一轮分析前清理上次残留。"""
        self._stage = ""
        self._df_clean = None
        self._df_raw = None
        self._analyst_agent = None
        self._analyst_first_pass_done = False
        self._cleaner_agent = None
        self._cleaner_dialog_open = False
        self._error = None

    def save_state(self) -> str | None:
        """保存当前分析状态到 run_dir，供 app 重启后恢复。

        保存内容：stage、context（可序列化部分）、DataFrames（parquet）。
        ProjectContext 已通过 _save_path 自动增量写入 JSONL。
        返回状态文件路径，失败返回 None。
        """
        import json as _json
        try:
            # 从 project_context 的 _save_path 推导 run_dir
            pc = getattr(self, '_project_context', None)
            if pc is None:
                return None
            save_path = getattr(pc, '_save_path', None)
            if not save_path:
                return None
            run_dir = Path(save_path).parent
            run_dir.mkdir(parents=True, exist_ok=True)

            ctx = getattr(self, '_context', None) or {}
            # 只保留可 JSON 序列化的字段，剔除 DataFrame/LLM client 等
            safe_ctx = {}
            skip_keys = {'_project_context', '_memory_manager', '_llm_client', '_df'}
            for k, v in ctx.items():
                if k in skip_keys:
                    continue
                try:
                    _json.dumps({k: v}, default=str)
                    safe_ctx[k] = v
                except (TypeError, ValueError):
                    safe_ctx[k] = str(v)

            state = {
                "stage": self._stage,
                "project_name": getattr(self, '_project_name', ''),
                "run_id": getattr(self._project_context, 'run_id', '') if hasattr(self, '_project_context') else '',
                "query": safe_ctx.get('query', ''),
                "data_path": safe_ctx.get('data_path', ''),
                "context": safe_ctx,
                "analyst_first_pass_done": self._analyst_first_pass_done,
            }
            (run_dir / "orch_state.json").write_text(
                _json.dumps(state, ensure_ascii=False, default=str), encoding="utf-8")

            # 保存 DataFrames
            if self._df_raw is not None:
                self._df_raw.to_parquet(run_dir / "df_raw.parquet")
            if self._df_clean is not None and self._df_clean is not self._df_raw:
                self._df_clean.to_parquet(run_dir / "df_clean.parquet")

            return str(run_dir / "orch_state.json")
        except Exception:
            logger.warning("save_state 失败", exc_info=True)
            return None

    @classmethod
    def restore_session(cls, config: "HaGoKuConfig", run_dir: str) -> "Orchestrator | None":
        """从 run_dir 恢复未完成的 session。失败返回 None。"""
        import json as _json
        import pandas as _pd
        try:
            from pathlib import Path as _Path
            rdir = _Path(run_dir)
            state_file = rdir / "orch_state.json"
            if not state_file.exists():
                return None
            state = _json.loads(state_file.read_text(encoding="utf-8"))

            orch = cls(config)
            orch._project_name = state.get("project_name", "")
            orch._stage = state.get("stage", "")
            orch._analyst_first_pass_done = state.get("analyst_first_pass_done", False)
            orch._context = state.get("context", {})

            # 恢复 DataFrames
            df_raw_path = rdir / "df_raw.parquet"
            if df_raw_path.exists():
                orch._df_raw = _pd.read_parquet(df_raw_path)
                orch._df_clean = orch._df_raw
            df_clean_path = rdir / "df_clean.parquet"
            if df_clean_path.exists():
                orch._df_clean = _pd.read_parquet(df_clean_path)

            # 恢复 ProjectContext
            ctx_jsonl = rdir / "project_context.jsonl"
            if ctx_jsonl.exists():
                from ..context.project_context import ProjectContext
                pc = ProjectContext.load_jsonl(
                    str(ctx_jsonl),
                    run_id=state.get("run_id", rdir.name),
                    analysis_goal=state.get("query", ""),
                )
                pc._save_path = str(ctx_jsonl)
                orch._project_context = pc
                # 恢复 event 订阅
                pc.subscribe(orch.event_bus, context_ref=orch._context)
                # 补充未持久化的字段
                orch._context["_project_context"] = pc

            # 恢复 OutputManager
            from ..storage.output import OutputManager
            orch.output_mgr = OutputManager(orch.config.output, orch._project_name)

            logger.info("restore_session: 恢复 session stage=%s project=%s",
                        orch._stage, orch._project_name)
            return orch
        except Exception:
            logger.warning("restore_session 失败", exc_info=True)
            return None

    def request_cancel(self) -> None:
        """前端「重置分析」：设置取消标志。"""
        with self._cancel_lock:
            self._cancel_requested_flag = True
        # 保存当前状态，以便恢复
        self.save_state()

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
        self.output_mgr.save_run_meta(run_dir, {"run_id": run_id, "query": query, "project": project_name})

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

        # Phase D: 唯一 DataAnalystAgent
        self._agent = DataAnalystAgent(self.config.llm, self.event_bus, orchestrator=self, llm_client=self.llm)

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
                self._agent.memory_project = memory_project
                # 注入 ProjectContext 到 context（必须在 run_scout_phase 之前，
                # 因为 infer_field_semantics 依赖它构造 messages）
                context["_project_context"] = getattr(self, '_project_context', None)
                self._agent._context = {"_project_context": getattr(self, '_project_context', None)}
                result = self._agent.run_scout_phase(
                    data_path, query, project_id=project_name,
                    memory_project=memory_project,
                )
                context.update(result)
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
                context["_memory_manager"] = self.memory
                context["_project_name"] = project_name

                self._stage = "scout"
                self._context = context
                from hagoku.tools.data_io import load_data as _load
                _df = _load(data_path)
                self._df_clean = _df
                self._df_raw = _df
                self.save_state()

                return {
                    "status": "scout_review",
                    "message": "",
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

            from hagoku.channel import build_messages

            intent_context = self._build_intent_context(query, parsed_intent)
            # EXEMPT: 辅助 LLM — 分析计划生成，非主对话通道
            messages = build_messages(
                query=query,
                user_input=PLAN_GENERATION_USER.format(query=intent_context),
                system_extra=PLAN_GENERATION_SYSTEM,
            )
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
