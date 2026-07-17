"""HaGoKu Studio Manager — 编排器：LLM 决策驱动，代码构建通道"""

from __future__ import annotations

import logging
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
from ..storage.memory import MemoryManager
from ..storage.output import OutputManager

# ── CH-5 拆分：从子模块重导出，保持外部 import 路径不变 ─────────

from .llm_dispatch.reply_handlers import ReplyHandlersMixin  # noqa: F401
from .payloads.pipeline_helpers import PipelineHelpersMixin  # noqa: F401


class Orchestrator(
    ReplyHandlersMixin,
    PipelineHelpersMixin,
):
    """HaGoKu Studio 编排器"""

    def _log_channel(self, agent: str, event: str, **kw: Any) -> None:
        """通道日志——记录每个关键决策点。"""
        try:
            cl = getattr(self, "_channel_logger", None)
            if cl:
                cl.log(agent, event, **kw)
        except Exception:
            logger.debug("_log_channel 失败", exc_info=True)

    def __init__(self, config: HaGoKuConfig | None = None) -> None:
        self.config = config or HaGoKuConfig.load()
        self.config.ensure_work_dir()

        # 核心组件
        self.event_bus = EventBus()
        self.db = HaGoKuDB.get_instance(self.config.work_dir / "hagoku.db")
        self.display = TerminalDisplay(verbosity="normal")
        self.output_mgr: OutputManager | None = None  # 按项目初始化
        self.memory: MemoryManager | None = None  # 按项目初始化

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
        # respond() 重入守卫 + _respond_cancelled 保护（共用锁）
        self._respond_lock = threading.Lock()
        self._respond_cancelled = False
        # 事件驱动状态机字段
        self._df_clean: pd.DataFrame | None = None
        self._df_raw: pd.DataFrame | None = None
        self._error: Exception | None = None


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
        self._df_clean = None
        self._df_raw = None
        self._error = None

    def save_state(self) -> str | None:
        """保存当前分析状态到 run_dir，供 app 重启后恢复。

        保存内容：stage、context（可序列化部分）、DataFrames（parquet）。
        Session 已通过 _save_path 自动保存。
        返回状态文件路径，失败返回 None。
        """
        import json as _json
        try:
            # 从 project_context 的 _save_path 推导 run_dir
            session = getattr(self, '_session', None)
            if session is None:
                return None
            save_path = getattr(session, '_save_path', None)
            if not save_path:
                return None
            run_dir = Path(save_path).parent
            run_id = run_dir.name
            run_dir.mkdir(parents=True, exist_ok=True)

            ctx = getattr(self, '_context', None) or {}
            # 只保留可 JSON 序列化的字段，剔除 DataFrame/LLM client 等
            safe_ctx = {}
            skip_keys = {'_session', '_memory_manager', '_llm_client', '_df'}
            for k, v in ctx.items():
                if k in skip_keys:
                    continue
                try:
                    _json.dumps({k: v}, default=str)
                    safe_ctx[k] = v
                except (TypeError, ValueError):
                    safe_ctx[k] = str(v)

            state = {
                "project_name": getattr(self, '_project_name', ''),
                "run_id": run_id,
                "query": safe_ctx.get('query', ''),
                "data_path": safe_ctx.get('data_path', ''),
                "context": safe_ctx,
            }
            (run_dir / "orch_state.json").write_text(
                _json.dumps(state, ensure_ascii=False, default=str), encoding="utf-8")

            # 保存 DataFrames
            if self._df_raw is not None:
                self._df_raw.to_parquet(run_dir / "df_raw.parquet")
            if self._df_clean is not None and self._df_clean is not self._df_raw:
                self._df_clean.to_parquet(run_dir / "df_clean.parquet")

            # ── 更新 project.json 的 current_run_id（不创建项目）──
            project_name = getattr(self, '_project_name', '')
            if project_name:
                proj_file = self.config.output.project_dir / project_name / "project.json"
                if proj_file.exists():
                    try:
                        meta = _json.loads(proj_file.read_text(encoding="utf-8"))
                    except Exception:
                        meta = {}
                    meta["current_run_id"] = run_id
                    _json.dump(meta, proj_file.open("w", encoding="utf-8"),
                              ensure_ascii=False, default=str)

            return str(run_dir / "orch_state.json")
        except Exception:
            logger.error("save_state 失败——刷新页面将丢失分析进度", exc_info=True)
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
            orch._context = state.get("context", {})

            # 恢复 DataFrames
            df_raw_path = rdir / "df_raw.parquet"
            if df_raw_path.exists():
                orch._df_raw = _pd.read_parquet(df_raw_path)
                orch._df_clean = orch._df_raw
            df_clean_path = rdir / "df_clean.parquet"
            if df_clean_path.exists():
                orch._df_clean = _pd.read_parquet(df_clean_path)

            # 恢复 Session
            session_file = rdir / "session.json"
            if session_file.exists():
                from ..context.session import Session
                session = Session.load(str(session_file), analysis_goal=state.get("query", ""))
                session._save_path = str(session_file)
                orch._session = session
                orch._context["_session"] = session

            # 恢复 OutputManager
            from ..storage.output import OutputManager
            orch.output_mgr = OutputManager(orch.config.output, orch._project_name)

            # 恢复 Agent
            from ..agents.agent import DataAnalystAgent
            orch._agent = DataAnalystAgent(
                orch.config.llm, orch.event_bus,
                orchestrator=orch, llm_client=orch.llm,
            )
            orch._agent.prompt = orch._agent._load_prompt()
            # 注入 session 到 agent context
            if getattr(orch, '_session', None):
                orch._agent._context = {"_session": orch._session}

            logger.info("restore_session: 恢复 session project=%s",
                        orch._project_name)
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

    def request_cancel_respond(self) -> None:
        """前端点「停止」：中断当前 respond 处理。"""
        self._respond_cancelled = True

    def is_respond_cancelled(self) -> bool:
        """线程安全地检查 respond 是否已被取消。"""
        return self._respond_cancelled

    def _is_cancel_requested(self) -> bool:
        with self._cancel_lock:
            return self._cancel_requested_flag

    def run(
        self,
        data_path: str,
        query: str = "",
        *,
        sheet_name: int | str = 0,
        aux_sheets: list[str] | None = None,
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

        # 1. 验证项目存在（项目必须由用户通过界面创建，不自动生成）
        if project_name is None:
            raise ValueError("缺少 project_name 参数，无法确定目标项目")
        
        proj_dir = self.config.output.project_dir / project_name
        if not proj_dir.is_dir():
            raise FileNotFoundError(
                f"项目 '{project_name}' 不存在。请先在界面中创建项目。"
            )

        self.event_bus.emit(EventType.RUN_STARTED, "manager", {
            "query": query,
            "project": project_name,
        })

        self.output_mgr = OutputManager(self.config.output, project_name)
        schema_file = self.output_mgr.project_dir / "progress.yaml"
        self.memory = MemoryManager(self.db, progress_path=schema_file)

        # ── 持久 context 引用（必修 3）：Scribe 初始化前声明 ──
        context: dict[str, Any] = {}

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

        # ── Session：统一会话记忆 ──
        from ..context.session import Session
        self._session = Session(analysis_goal=query)
        self._session._save_path = str(run_dir / "session.json")

        # ── 通道日志：初始化 ChannelLogger ──
        from ..observability.channel_logger import ChannelLogger
        self._channel_logger = ChannelLogger(run_dir)
        self._channel_logger.log("orchestrator", "run_start", query=query, project=project_name, run_id=run_id)

        with self._cancel_lock:
            self._cancel_requested_flag = False
        # 事件驱动状态机字段
        self._project_name = project_name
        self._df_clean: pd.DataFrame | None = None
        self._df_raw: pd.DataFrame | None = None
        self._error: Exception | None = None


        # 创建数据库记录
        self.db.create_project(project_name, data_path=data_path)

        self.db.create_run(run_id, project_name, query=query, plan={}, manager_mode="balanced")

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
                # 注入 Session 到 context（必须在 run_scout_phase 之前，
                # 因为 infer_field_semantics 依赖它构造 messages）
                context["_session"] = getattr(self, '_session', None)
                self._agent._context = {"_session": getattr(self, '_session', None)}
                result = self._agent.run_scout_phase(
                    data_path, query, project_id=project_name,
                    memory_project=memory_project,
                    sheet_name=sheet_name,
                    aux_sheets=aux_sheets,
                )
                context.update(result)
                if context.get("error"):
                    raise RuntimeError(str(context["error"]))

                # 写 run_dir 到 context，供 generate_report 等工具使用
                context["_run_dir"] = str(run_dir)

                if self._is_cancel_requested():
                    return self._finish_run_cancelled(run_id, project_name, run_start, run_dir)

                # ── 注入 Session 到 context ──
                context["_session"] = getattr(self, '_session', None)
                context["_memory_manager"] = self.memory
                context["_project_name"] = project_name


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

