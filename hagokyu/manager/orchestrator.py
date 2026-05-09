"""HaGoKu Manager — 编排器，规则+AI 双驱动"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import HaGoKuConfig
from ..guardrails.statistical import StatisticalGuardrails
from ..observability.display import TerminalDisplay
from ..observability.event_bus import EventBus
from ..observability.events import EventType
from ..storage.database import HaGoKuDB
from ..storage.memory import MemoryManager
from ..storage.output import OutputManager
from ..storage.project_manager import ProjectManager
from ..agents._scribe.agent import ScribeAgent
from ..agents.analyst import AnalystAgent, AnalysisResult
from ..agents.cleaner import CleanerAgent
from ..agents.reporter import ReporterAgent
from ..agents.scout import DataContext, ScoutAgent
from ..llm.client import create_structured_llm_client, create_deep_client, create_quick_client
from ..tools.data_io import save_data
from .query_parser import QueryParser, parse_query


# ── 规则引擎 ──────────────────────────────────────────────────

PLAN_TEMPLATES: dict[str, dict[str, Any]] = {
    "趋势分析": {
        "agents": ["scout", "cleaner", "analyst", "reporter"],
        "analyst_focus": ["trend", "regression"],
    },
    "差异比较": {
        "agents": ["scout", "cleaner", "analyst", "reporter"],
        "analyst_focus": ["hypothesis_test", "effect_size"],
    },
    "因果推断": {
        "agents": ["scout", "cleaner", "analyst", "reporter"],
        "analyst_focus": ["regression", "causal"],
    },
    "相关性分析": {
        "agents": ["scout", "cleaner", "analyst", "reporter"],
        "analyst_focus": ["correlation"],
    },
    "数据画像": {
        "agents": ["scout", "reporter"],
        "analyst_focus": [],
    },
}

KEYWORD_MAP: dict[str, str] = {
    r"趋势|变化|增长|下降|走势|上升|波动": "趋势分析",
    r"差异|对比|比较|不同|A/B|ab测试|是否不同": "差异比较",
    r"因果|影响|导致|因为|效果|是否有效": "因果推断",
    r"相关|关系|联系|关联|有关": "相关性分析",
    r"画像|概况|什么数据|什么样|描述|概览": "数据画像",
}


class RuleEngine:
    """Manager 的规则引擎，覆盖 80% 常见决策"""

    def match_plan(self, query: str) -> dict[str, Any] | None:
        """关键词匹配计划模板"""
        for pattern, plan_name in KEYWORD_MAP.items():
            if re.search(pattern, query):
                return {**PLAN_TEMPLATES[plan_name], "plan_name": plan_name}
        return None


# ── 编排器 ────────────────────────────────────────────────────


class Orchestrator:
    """HaGoKu 编排器：规则+AI 双驱动，协调四个 Agent"""

    def __init__(self, config: HaGoKuConfig | None = None) -> None:
        self.config = config or HaGoKuConfig.load()
        self.config.ensure_work_dir()

        # 核心组件
        self.event_bus = EventBus()
        self.db = HaGoKuDB.get_instance(self.config.work_dir / "hagokyu.db")
        self.display = TerminalDisplay(verbosity="normal")
        self.output_mgr: OutputManager | None = None  # 按项目初始化
        self.memory: MemoryManager | None = None  # 按项目初始化
        self.project_mgr = ProjectManager(self.config.output.project_dir)  # 全局项目管理器

        # 订阅显示
        self.event_bus.subscribe(self.display)

        # 规则引擎
        self.rule_engine = RuleEngine()

        # 护栏
        self.guardrails = StatisticalGuardrails()

        # LLM 客户端（懒初始化，pure_rule 模式永远不会触发）
        self._llm_client: Any | None = None
        self._llm_deep: Any | None = None  # 深度推理客户端（懒初始化）
        self._llm_quick: Any | None = None  # 快速客户端（懒初始化）

        # 设置模块级配置
        from ..tools.analysis import set_analysis_config
        from ..tools.cleaning import set_cleaning_config
        set_analysis_config(self.config.analysis)
        set_cleaning_config(self.config.cleaning)

    @property
    def llm_deep(self) -> Any:
        """深度推理客户端（懒初始化）"""
        if self._llm_deep is None:
            self._llm_deep = create_deep_client(self.config)
        return self._llm_deep

    @property
    def llm_quick(self) -> Any:
        """快速客户端（懒初始化）"""
        if self._llm_quick is None:
            self._llm_quick = create_quick_client(self.config)
        return self._llm_quick

    def run(
        self,
        data_path: str,
        query: str = "",
        *,
        project_name: str | None = None,
        user_mode: str | None = None,
        output_dir: str | None = None,
        formats: list[str] | None = None,
        template: str | None = None,
        resume: bool = False,
        progress_path: str | None = None,
        phase: str = "full",
        scout_context: "DataContext | None" = None,
        cleaning_operations: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        主入口：执行完整分析流程

        Args:
            data_path: 数据文件路径
            query: 用户的分析问题
            project_name: 项目名（默认从文件名推断）
            user_mode: 用户模式 (quick / standard / expert)
            output_dir: 自定义输出目录
            formats: 报告输出格式
            template: 报告模板 (default/academic/brief/business_analysis/ab_test/executive_brief/data_audit)
            resume: 是否从上次断点继续
            progress_path: 外部 progress.yaml 路径
            phase: 运行阶段
                - "scout_first": 只跑 Scout，返回字段信息
                - "cleaning_first": Scout（缓存）+ Cleaner（strategy_only），返回清洗策略
                - "analyst_first": Scout（缓存）+ Cleaner（strategy_only，已确认）+ Analyst（preliminary）
                - "full": 完整 pipeline
            scout_context: Scout 的缓存上下文（用于避免重复跑 Scout）
            cleaning_operations: 用户确认的清洗操作（Cleaner 直接执行，不重新规划）

        Returns:
            运行结果摘要
        """
        run_start = datetime.now()
        user_mode = user_mode or self.config.user_mode.default_mode

        # 1. 创建项目
        if project_name is None:
            project_name = Path(data_path).stem.replace(" ", "_")

        self.event_bus.emit(EventType.RUN_STARTED, "Manager", {
            "query": query,
            "project": project_name,
        })

        self.output_mgr = OutputManager(self.config.output, project_name)
        schema_file = self.output_mgr.project_dir / "progress.yaml"
        self.memory = MemoryManager(self.db, progress_path=schema_file)

        # 初始化 Scribe Agent（看板驱动）
        self.scribe = ScribeAgent(self.config.llm, self.event_bus, self.output_mgr.project_dir)
        self.scribe.init_pipeline()

        # 处理 --progress 参数
        if progress_path:
            n = self.memory.import_progress_yaml(project_name, Path(progress_path))
            if n > 0:
                self.event_bus.emit(EventType.AGENT_THINKING, "Manager", {
                    "thought": f"📄 导入了 {n} 条进度定义",
                })

        run_dir = self.output_mgr.create_run_dir()
        run_id = run_dir.name

        # 创建数据库记录
        self.db.create_project(project_name, data_path=data_path)

        # 1.5 解析用户查询 — 理解用户真正想问什么
        parsed_intent = self._parse_user_query(query)
        self.event_bus.emit(EventType.AGENT_THINKING, "Manager", {
            "thought": f"🔍 理解你的问题：{self._describe_intent(parsed_intent)}",
        })

        # 2. 创建分析计划
        plan = self._create_plan(query, parsed_intent=parsed_intent)
        self.db.create_run(run_id, project_name, query=query, plan=plan, manager_mode="balanced")

        # 初始化 Agent（传入 scribe 用于看板 block/unblock）
        # 双层 LLM 策略：Scout/Cleaner/Reporter 用 quick，Analyst 用 deep
        scout = ScoutAgent(self.config.llm, self.event_bus, llm_client=self.llm_quick, scribe=self.scribe)
        cleaner = CleanerAgent(self.config.llm, self.event_bus, llm_client=self.llm_quick, scribe=self.scribe)
        analyst = AnalystAgent(self.config.llm, self.event_bus, llm_client=self.llm_deep, scribe=self.scribe)
        reporter = ReporterAgent(self.config.llm, self.event_bus, llm_client=self.llm_quick, scribe=self.scribe)

        # Resume 支持
        context: DataContext | None = None
        df_clean = None
        cleaning_report = None
        cleaned_path_str = ""

        if resume:
            state = self.memory.get_resume_state(project_name)
            if state and state["stage"] in ("cleaned", "analyzed", "reported"):
                self.event_bus.emit(EventType.AGENT_THINKING, "Manager", {
                    "thought": f"⏩ 从 {state['stage']} 阶段恢复，跳过 Scout 和 Cleaner",
                })
                # 恢复上下文
                if state.get("context") and isinstance(state["context"], dict):
                    context = DataContext.from_dict(state["context"])
                # 加载清洗后数据
                if state.get("cleaned_path"):
                    import pandas as pd
                    cleaned_path_str = state["cleaned_path"]
                    if Path(cleaned_path_str).exists():
                        df_clean = pd.read_parquet(cleaned_path_str)

        # ── Scout 交互确认阶段 ──────────────────────────────────
        # phase="scout_first" 时只跑 Scout，返回 pending_items 供用户确认
        if phase == "scout_first":
            self.event_bus.emit(EventType.AGENT_THINKING, "Manager", {
                "thought": "🔍 正在识别数据字段，请稍候...",
            })
            scout = ScoutAgent(self.config.llm, self.event_bus, llm_client=self.llm_quick, scribe=self.scribe)
            ir = scout.begin(data_path=data_path, query=query, project_id=project_name)
            # begin() 已触发 AGENT_STARTED（由 Scribe claim 任务），并在需要确认时 block 了看板
            # 返回 InteractionResult 给 UI 显示确认项
            return {
                "status": "scout_confirm",
                "phase": ir.phase,
                "message": ir.message,
                "needs_confirmation": ir.needs_confirmation,
                "pending_items": ir.pending_items,
                "data": ir.data,
                "final": ir.final,
            }

        # ── Cleaner 策略阶段 ────────────────────────────────────
        # phase="cleaning_first"：跑 Scout（缓存）+ Cleaner（strategy_only），返回清洗策略供用户确认
        if phase == "cleaning_first":
            # Scout（使用缓存上下文或重新跑）
            if scout_context is not None:
                context = scout_context
                self.event_bus.emit(EventType.AGENT_THINKING, "Manager", {
                    "thought": f"🔍 使用缓存的字段信息（{context.n_cols} 个字段）",
                })
            else:
                self.event_bus.emit(EventType.AGENT_THINKING, "Manager", {
                    "thought": "🔍 Scout 缓存未命中，重新识别字段...",
                })
                scout_agent = ScoutAgent(self.config.llm, self.event_bus, llm_client=self.llm_quick)
                context = scout_agent.run(data_path, query="", project_id=project_name)

            # Cleaner：只检测+计划，不执行清洗
            self.event_bus.emit(EventType.AGENT_THINKING, "Manager", {
                "thought": "🧹 检测数据质量，生成清洗策略...",
            })
            cleaner = CleanerAgent(self.config.llm, self.event_bus, llm_client=self.llm_quick)
            strategy_result = cleaner.get_strategy_summary(data_path, context)
            operations = strategy_result.get("operations", [])
            quality = strategy_result.get("data_quality", "unknown")
            quality_labels = {"good": "数据质量良好", "medium": "数据质量一般", "poor": "数据质量问题较多"}
            if operations:
                llm_message = f"数据质量：{quality_labels.get(quality, quality)}。我计划执行 {len(operations)} 个清洗操作："
                for op in operations[:6]:
                    col = op.get("column", "")
                    reason = op.get("reason", "")
                    llm_message += f"\n• **{col}**：{reason[:50]}{'...' if len(reason) > 50 else ''}"
                if len(operations) > 6:
                    llm_message += f"\n... 还有 {len(operations) - 6} 个操作"
                llm_message += "\n\n这个清洗方案可以吗？或者你想调整某个处理方式？"
            else:
                llm_message = f"数据质量：{quality_labels.get(quality, quality)}。未检测到需要清洗的问题，数据可以直接分析。这个清洗方案可以吗？或者你想做其他特殊处理？"
            if isinstance(strategy_result, dict):
                self.event_bus.emit(EventType.AGENT_COMPLETED, "Cleaner", {
                    "result_summary": f"检测完成：{len(operations)} 个计划操作",
                })
                return {
                    "status": "cleaner_strategy",
                    "message": llm_message,
                    "scout_data": {
                        "n_cols": context.n_cols,
                        "n_rows": context.n_rows,
                        "columns": [s.column_name for s in context.column_semantics],
                        "uncertain_columns": [s.column_name for s in context.get_uncertain_columns()],
                        "column_descriptions": context.column_descriptions,
                    },
                    "outliers": strategy_result.get("outliers", {}),
                    "missing_mechanisms": strategy_result.get("missing_mechanisms", {}),
                    "operations": operations,
                    "data_quality": quality,
                    "duration_ms": int((datetime.now() - run_start).total_seconds() * 1000),
                }
            # 正常执行（用户已确认操作，直接清洗）
            df_clean, cleaning_report = strategy_result

        # ── Analyst 初步发现阶段 ─────────────────────────────────
        # phase="analyst_first"：Scout（缓存）+ Cleaner（strategy_only，已确认）+ Analyst（preliminary）
        if phase == "analyst_first":
            # Scout
            if scout_context is not None:
                context = scout_context
                self.event_bus.emit(EventType.AGENT_THINKING, "Manager", {
                    "thought": f"🔍 使用缓存的字段信息（{context.n_cols} 个字段）",
                })
            else:
                scout_agent = ScoutAgent(self.config.llm, self.event_bus, llm_client=self.llm_quick)
                context = scout_agent.run(data_path, query="", project_id=project_name)

            # Cleaner
            self.event_bus.emit(EventType.AGENT_THINKING, "Manager", {
                "thought": "🧹 数据清洗（已确认策略）...",
            })
            cleaner = CleanerAgent(self.config.llm, self.event_bus, llm_client=self.llm_quick)
            if cleaning_operations is not None:
                # 用户已确认策略 → 执行清洗
                df_clean, cleaning_report = cleaner.run(
                    data_path, context,
                    user_operations=cleaning_operations,
                    impact_warning=self.config.manager.cleaning_impact_warning,
                    phase="full",
                )
            else:
                # 未确认 → 只返回策略供用户确认
                strategy_result = cleaner.run(
                    data_path, context,
                    user_operations=cleaning_operations,
                    impact_warning=self.config.manager.cleaning_impact_warning,
                    phase="strategy_only",
                )
                if isinstance(strategy_result, dict):
                    # 用户未确认操作，用自动规划的执行
                    auto_ops = strategy_result.get("operations", [])
                    df_clean, cleaning_report = cleaner.run(
                        data_path, context,
                        user_operations=auto_ops,
                        impact_warning=self.config.manager.cleaning_impact_warning,
                        phase="full",
                    )
                else:
                    df_clean, cleaning_report = strategy_result

            # Analyst：初步发现或完整分析（取决于phase）
            analyst_phase = "full" if phase == "full" else "preliminary"
            self.event_bus.emit(EventType.AGENT_THINKING, "Manager", {
                "thought": "📊 初步分析，发现数据中的规律..." if analyst_phase == "preliminary" else "📊 完整分析中...",
            })
            analyst = AnalystAgent(self.config.llm, self.event_bus, llm_client=self.llm_deep)
            analyst_result = analyst.run(df_clean, context, plan, phase=analyst_phase)
            if isinstance(analyst_result, dict):
                self.event_bus.emit(EventType.AGENT_COMPLETED, "Analyst", {
                    "result_summary": f"初步发现 {len(analyst_result.get('preliminary_findings', []))} 个，待确认",
                })
                findings = analyst_result.get("preliminary_findings", [])
                suggested = analyst_result.get("suggested_focus", "")
                power_warnings = analyst_result.get("power_warnings", [])[:2]
                llm_lines = []
                if power_warnings:
                    llm_lines.append(f"⚡ {power_warnings[0]}")
                if findings:
                    llm_lines.append(f"初步找到了 {len(findings)} 个分析方向：")
                    for f in findings[:5]:
                        sig = "✅ 显著" if f.get("significance") == "significant" else "⚪ 不显著"
                        q = f.get("question", "")
                        p = f.get("p_value")
                        p_str = f"（p={p:.4f}）" if p is not None else ""
                        llm_lines.append(f"• {sig} {p_str}：{q}")
                else:
                    llm_lines.append("初步分析没有发现明显的统计规律。")
                if suggested:
                    llm_lines.append(f"💡 {suggested}")
                llm_lines.append("\n你想重点关注哪个方向？或者有其他想看的维度？")
                llm_message = "\n".join(llm_lines)
                return {
                    "status": "analyst_preliminary",
                    "message": llm_message,
                    "power_warnings": power_warnings,
                    "business_metrics": analyst_result.get("business_metrics", []),
                    "preliminary_findings": findings,
                    "suggested_focus": suggested,
                    "cleaning_impact": cleaning_report.impact_rate if cleaning_report else 0,
                    "duration_ms": int((datetime.now() - run_start).total_seconds() * 1000),
                }
            results, business_metrics = analyst_result

        try:
            # ── LLM 门卫：分类用户问题 ────────────────────────────
            if context is None and query:
                classification, llm_response = scout.classify_query(query, data_path=data_path)
                if classification == "not_relevant":
                    self.event_bus.emit(EventType.AGENT_THINKING, "Scout", {
                        "thought": f"🤖 {llm_response}",
                    })
                    return {
                        "status": "skipped",
                        "reason": "query_not_relevant_to_data",
                        "llm_response": llm_response,
                        "duration_ms": int((datetime.now() - run_start).total_seconds() * 1000),
                    }
                elif classification == "ambiguous":
                    self.event_bus.emit(EventType.AGENT_THINKING, "Scout", {
                        "thought": f"❓ {llm_response}",
                    })
                    return {
                        "status": "ambiguous",
                        "reason": "query_needs_clarification",
                        "llm_response": llm_response,
                        "duration_ms": int((datetime.now() - run_start).total_seconds() * 1000),
                    }
                # relevant → 继续跑分析 pipeline

            # Scout + Cleaner（如果不是 resume）
            if context is None:
                # 3. Scout: 数据侦察（Scout 自己会和用户对话确认字段）
                context = scout.run(data_path, query, project_id=project_name)

                # 4. Cleaner: 数据清洗
                df_clean, cleaning_report = cleaner.run(
                    data_path, context,
                    impact_warning=self.config.manager.cleaning_impact_warning,
                )

                # 保存清洗后数据（如有）
                if df_clean is not None:
                    cleaned_path = self.output_mgr.data_dir / f"cleaned_{run_id}.parquet"
                    save_data(df_clean, cleaned_path)
                    cleaned_path_str = str(cleaned_path)
                else:
                    cleaned_path_str = ""
                    self.event_bus.emit(EventType.QUALITY_CHECK, "Manager", {
                        "verdict": "warning",
                        "detail": "数据清洗未成功，尝试使用原始数据",
                    })

                # 保存 resume 状态
                self.memory.save_resume_state(
                    project_name, "cleaned",
                    cleaned_path=cleaned_path_str,
                    context=context, run_id=run_id,
                )

                # 5. 质量检查
                if cleaning_report:
                    self.event_bus.emit(EventType.QUALITY_CHECK, "Manager", {
                        "verdict": "pass" if cleaning_report.impact_rate < self.config.manager.cleaning_impact_warning else "warning",
                        "detail": f"清洗影响率 {cleaning_report.impact_rate:.1%}",
                    })

            # 6. Analyst: 统计分析
            if df_clean is None or context is None:
                # 尝试加载原始数据继续
                if context is not None and context.data_path:
                    try:
                        from ..tools.data_io import load_data
                        df_clean = load_data(context.data_path)
                        self.event_bus.emit(EventType.QUALITY_CHECK, "Manager", {
                            "verdict": "warning",
                            "detail": "使用原始数据继续分析",
                        })
                    except Exception:
                        raise RuntimeError(
                            f"无法获取有效数据（context.data_path={context.data_path}），分析无法继续"
                        )
                else:
                    raise RuntimeError(
                        "Pipeline error: 缺少有效数据和上下文，无法继续分析。"
                    )
            results, business_metrics = analyst.run(df_clean, context, plan)

            # 7. Reporter: 生成报告
            output_path = str(run_dir / "output" / "report.html")
            report = reporter.run(
                results=results,
                context=context,
                cleaning_summary=cleaning_report.to_dict() if cleaning_report else {},
                project_name=project_name,
                query=query,
                output_path=output_path,
                formats=formats or self.config.output.formats,
                template=template,
                user_mode=user_mode,
                df=df_clean,
                business_metrics=business_metrics,
            )

            # 8. 保存运行元数据
            run_meta = {
                "run_id": run_id,
                "project": project_name,
                "query": query,
                "plan": plan,
                "n_results": len(results),
                "cleaning_impact": cleaning_report.impact_rate if cleaning_report else 0,
                "output_path": output_path,
            }
            self.output_mgr.save_run_meta(run_dir, run_meta)

            # 9. 更新数据库
            duration_ms = int((datetime.now() - run_start).total_seconds() * 1000)
            self.db.complete_run(run_id, duration_ms=duration_ms, output_path=output_path)

            # 保存 findings
            for result in results:
                self.db.save_finding({
                    "id": result.result_id,
                    "run_id": run_id,
                    "analysis_type": result.analysis_type,
                    "question": result.question,
                    "conclusion_plain": result.conclusion_plain,
                    "conclusion_statistical": result.conclusion_statistical,
                    "p_value": result.p_value,
                    "effect_size": result.effect_size,
                    "effect_type": result.effect_type,
                    "confidence_interval": result.confidence_interval,
                    "significance": result.significance,
                })

            # 10. 学习 + 导出 progress.yaml
            learned = self.memory.learn_from_run(project_name, context, results, cleaning_report)
            if learned > 0:
                self.event_bus.emit(EventType.AGENT_THINKING, "Manager", {
                    "thought": f"🧠 学习了 {learned} 条记忆，下次分析将自动应用",
                })

            # 保存 resume 状态
            self.memory.save_resume_state(
                project_name, "reported",
                cleaned_path=cleaned_path_str,
                context=context, run_id=run_id,
            )

            # 11. 创建 latest 链接
            self.output_mgr.create_latest_symlink(run_dir)

            # 11.5 记录到项目管理器（更新运行计数等）
            if self.project_mgr.exists(project_name):
                self.project_mgr.record_run(project_name)

            # 12. 事件日志
            events_path = run_dir / "events.jsonl"
            self.event_bus.save_to_file(events_path)

            # 13. 发射完成事件
            self.event_bus.emit(EventType.RUN_COMPLETED, "Manager", {
                "duration": f"{duration_ms / 1000:.1f}s",
                "token_count": sum(
                    e.data.get("token_count", 0)
                    for e in self.event_bus.events
                    if e.event_type == EventType.TOOL_RESULT and "token_count" in e.data
                ),
                "output_path": output_path,
            })

            return {
                "status": "completed",
                "message": f"✅ 分析完成！共生成 {len(results)} 项发现，报告已保存。",
                "run_id": run_id,
                "project": project_name,
                "output_path": output_path,
                "n_results": len(results),
                "duration_ms": duration_ms,
            }

        except Exception as e:
            duration_ms = int((datetime.now() - run_start).total_seconds() * 1000)
            self.db.fail_run(run_id, duration_ms=duration_ms)
            self.event_bus.emit(EventType.RUN_FAILED, "Manager", {"error": str(e)})
            raise

    def _create_plan(
        self,
        query: str,
        parsed_intent: Any | None = None,
    ) -> dict[str, Any]:
        """
        创建分析计划：规则优先匹配，AI 辅助微调
        """
        rule_plan = self.rule_engine.match_plan(query)

        if rule_plan:
            # 规则匹配成功，AI 做微调
            llm_plan = self._create_plan_hybrid(query, rule_plan, parsed_intent=parsed_intent)
            if llm_plan is not None:
                llm_plan["rule_match"] = True
                return llm_plan
            rule_plan["rule_match"] = True
            if parsed_intent and parsed_intent.target:
                rule_plan["target"] = parsed_intent.target
            return rule_plan

        # 无匹配规则，AI 生成
        llm_plan = self._create_plan_llm(query, rule_plan, parsed_intent=parsed_intent)
        if llm_plan is not None:
            return llm_plan
        plan = self._generic_plan(query)
        if parsed_intent and parsed_intent.target:
            plan["target"] = parsed_intent.target
        return plan

    def _generic_plan(self, query: str) -> dict[str, Any]:
        """返回通用分析计划（探索性分析）"""
        return {
            "plan_name": "通用分析",
            "agents": ["scout", "cleaner", "analyst", "reporter"],
            "analyst_focus": ["regression", "hypothesis_test", "correlation"],
            "query": query,
            "rule_match": False,
        }

    def _create_plan_hybrid(
        self,
        query: str,
        rule_plan: dict[str, Any],
        parsed_intent: Any | None = None,
    ) -> dict[str, Any]:
        """混合模式：规则计划为基础，LLM 调整优化"""
        llm_plan = self._call_llm_for_plan(
            query=query,
            rule_plan=rule_plan,
            mode="adjust",
            parsed_intent=parsed_intent,
        )
        if llm_plan is not None:
            llm_plan["rule_match"] = True
            llm_plan["llm_adjusted"] = True
            self.event_bus.emit(EventType.PLAN_ADJUSTED, "Manager", {
                "original": rule_plan.get("plan_name"),
                "adjusted": llm_plan.get("plan_name"),
                "reasoning": llm_plan.get("reasoning", ""),
            })
            return llm_plan
        # LLM 失败，返回规则计划不变
        rule_plan["rule_match"] = True
        return rule_plan

    def _create_plan_llm(
        self,
        query: str,
        rule_plan: dict[str, Any] | None = None,
        parsed_intent: Any | None = None,
    ) -> dict[str, Any] | None:
        """LLM 从零生成分析计划（rule_plan 可作为参考 hint）"""
        llm_plan = self._call_llm_for_plan(
            query=query,
            rule_plan=rule_plan,
            mode="generate",
            parsed_intent=parsed_intent,
        )
        if llm_plan is not None:
            llm_plan["rule_match"] = rule_plan is not None
            llm_plan["llm_generated"] = True
            self.event_bus.emit(EventType.PLAN_CREATED, "Manager", {
                "source": "llm",
                "plan_name": llm_plan.get("plan_name"),
                "reasoning": llm_plan.get("reasoning", ""),
            })
            return llm_plan
        return None

    def _call_llm_for_plan(
        self,
        query: str,
        rule_plan: dict[str, Any] | None = None,
        mode: str = "generate",
        parsed_intent: Any | None = None,
    ) -> dict[str, Any] | None:
        """
        调用 LLM 生成或调整分析计划

        Args:
            query: 用户分析问题
            rule_plan: 规则引擎输出（混合模式下作为上下文）
            mode: "generate"（从零生成）或 "adjust"（调整规则计划）

        Returns:
            计划 dict，LLM 失败时返回 None
        """
        from ..llm.client import create_structured_llm_client
        from ..llm.plan_schema import VALID_ANALYST_FOCUS, DEFAULT_EXPLORATORY_FOCUS, LLMPlanResponse
        from ..llm.prompts import PLAN_GENERATION_SYSTEM, PLAN_GENERATION_USER, PLAN_ADJUSTMENT_USER

        try:
            # 懒初始化 LLM 客户端
            if self._llm_client is None:
                self._llm_client = create_structured_llm_client(self.config.llm)

            # 构建消息
            messages = [{"role": "system", "content": PLAN_GENERATION_SYSTEM}]

            # 基于解析意图构建更丰富的用户查询上下文
            intent_context = self._build_intent_context(query, parsed_intent)

            if mode == "adjust" and rule_plan:
                user_content = PLAN_ADJUSTMENT_USER.format(
                    query=intent_context,
                    plan_name=rule_plan.get("plan_name", ""),
                    agents=", ".join(rule_plan.get("agents", [])),
                    analyst_focus=", ".join(rule_plan.get("analyst_focus", [])),
                    target=rule_plan.get("target") or "null",
                )
            else:
                user_content = PLAN_GENERATION_USER.format(query=intent_context)

            messages.append({"role": "user", "content": user_content})

            # 通过 instructor 获取结构化输出
            response: LLMPlanResponse = self._llm_client.chat.completions.create(
                model=self.config.llm.model,
                messages=messages,
                response_model=LLMPlanResponse,
                temperature=self.config.llm.temperature,
                max_tokens=self.config.llm.max_tokens,
                timeout=30,
            )

            # 服务端二次校验 analyst_focus
            validated_focus = [f for f in response.analyst_focus if f in VALID_ANALYST_FOCUS]
            if not validated_focus:
                validated_focus = DEFAULT_EXPLORATORY_FOCUS.copy()

            # 确保 agents 包含 scout 和 reporter
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
            }
            return plan

        except Exception as e:
            self.event_bus.emit(EventType.AGENT_THINKING, "Manager", {
                "thought": f"LLM 计划生成失败: {e}",
            })
            return None

    def _parse_user_query(self, query: str) -> Any:
        """解析用户查询为结构化意图"""
        try:
            from .query_parser import parse_query
            return parse_query(query)
        except Exception:
            return None

    def _describe_intent(self, parsed_intent: Any) -> str:
        """将解析后的意图翻译成用户能理解的话"""
        if parsed_intent is None:
            return "探索这份数据有什么规律"

        intent_names = {
            "comparison": "对比不同组之间的差异",
            "causation": "找某个结果的原因",
            "correlation": "找变量之间的关系",
            "trend": "看某个指标随时间的变化趋势",
            "diagnostic": "诊断数据中的问题",
            "exploration": "探索数据有什么规律",
        }

        parts = []
        intent_name = intent_names.get(parsed_intent.intent_type, "探索数据")
        parts.append(intent_name)

        if parsed_intent.target:
            parts.append(f"，关注「{parsed_intent.target}」")

        if parsed_intent.time_range:
            parts.append(f"，时间范围「{parsed_intent.time_range}」")

        if parsed_intent.group_by:
            parts.append(f"，按「{'/'.join(parsed_intent.group_by)}」分组")

        return "".join(parts)

    def _build_intent_context(self, query: str, parsed_intent: Any) -> str:
        """将解析后的意图构建成 LLM 可用的上下文"""
        if parsed_intent is None:
            return query

        parts = [query]

        if parsed_intent.intent_type != "exploration":
            intent_labels = {
                "comparison": "用户想对比不同组的差异",
                "causation": "用户想找原因",
                "correlation": "用户想知道变量之间的关系",
                "trend": "用户想看变化趋势",
                "diagnostic": "用户想诊断问题",
            }
            if parsed_intent.intent_type in intent_labels:
                parts.append(f"\n【意图】：{intent_labels[parsed_intent.intent_type]}")

        if parsed_intent.target:
            parts.append(f"\n【目标变量】：{parsed_intent.target}")

        if parsed_intent.time_range:
            parts.append(f"\n【时间范围】：{parsed_intent.time_range}")

        if parsed_intent.group_by:
            parts.append(f"\n【分组维度】：{'、'.join(parsed_intent.group_by)}")

        if parsed_intent.filters:
            parts.append(f"\n【筛选条件】：{parsed_intent.filters}")

        return "".join(parts)

    def _request_field_confirmation(
        self,
        context: "DataContext",
        project_name: str,
    ) -> "DataContext | None":
        """
        Scout 识别完字段后，和用户对话确认字段含义。
        Scout 展示理解，用户纠正，直到用户确认。
        必须用户明确说"好"才能继续。
        """
        print("\n" + "=" * 60)
        print("📋 字段理解")
        print("=" * 60)

        # 展示 Scout 识别出的所有字段
        print("\n我看到了这些字段：")
        for sem in context.column_semantics:
            col = sem.column_name
            desc = context.column_descriptions.get(col, sem.inferred_type.value)
            print(f"  {col} → {desc}")

        print("\n有不对的，纠正我。直接说就行")
        print("  比如：Inc1 是销售额，不是收入")
        print()

        corrections: dict[str, dict[str, str]] = {}

        while True:
            user_input = input("➜ ").strip()

            if user_input.lower() in ("cancel", "q", "取消"):
                print("\n❌ 已取消")
                return None

            if not user_input:
                continue

            # 用户说"好"或"继续"或"是"表示确认
            if user_input.lower() in ("好", "是", "ok", "继续", "next", "y", "yes"):
                # Scout 展示最终理解，建议进入数据清洗
                print("\n📋 最终字段理解：")
                for sem in context.column_semantics:
                    col = sem.column_name
                    desc = context.column_descriptions.get(col, sem.inferred_type.value)
                    print(f"  {col} = {desc}")
                print("\n我准备进入数据清洗阶段，可以吗？")
                confirm = input("➜ (回车确认，或继续纠正) ").strip()
                if confirm.lower() in ("好", "是", "ok", "y", "yes", ""):
                    break
                elif confirm:
                    user_input = confirm
                else:
                    continue

            # 让 LLM 理解用户说的话，更新 context
            understood = self._llm_understand_field_update(context, user_input)
            if understood:
                corrections.update(understood)

        if corrections:
            print(f"\n📝 保存 {len(corrections)} 个字段...")
            for col, info in corrections.items():
                context.column_descriptions[col] = f"{info['chinese_name']}（{info['business_meaning']}）"
                for s in context.column_semantics:
                    if s.column_name == col:
                        s.evidence = info['business_meaning']
                        break
            self._save_field_descriptions(project_name, corrections)

        print("\n✅ 进入数据清洗...")
        return context

    def _llm_understand_field_update(
        self,
        context: "DataContext",
        user_input: str,
    ) -> dict[str, dict[str, str]] | None:
        """让 LLM 理解用户说的字段更新，返回更新的字段字典"""
        try:
            from openai import OpenAI

            columns = [s.column_name for s in context.column_semantics]

            client = OpenAI(
                api_key=self.config.llm.api_key,
                base_url=self.config.llm.base_url,
            )

            response = client.chat.completions.create(
                model=self.config.llm.model,
                messages=[
                    {"role": "system", "content": "你是数据分析师。用户告诉你字段的含义。请理解用户说的话，提取出字段名、中文名、业务含义。\n输出格式（JSON，只输出JSON）：\n{\"字段名\": {\"chinese_name\": \"中文名\", \"business_meaning\": \"业务含义\"}}"},
                    {"role": "user", "content": f"字段列表：{', '.join(columns)}\n用户说：{user_input}"}
                ],
                temperature=0.1,
                max_tokens=200,
            )
            import json
            result_text = response.choices[0].message.content.strip()
            if result_text.startswith("```"):
                result_text = result_text.split("```")[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:]
            result = json.loads(result_text.strip())

            valid_updates = {}
            for col, info in result.items():
                if col in columns:
                    valid_updates[col] = info
                    print(f"   ✅ {col} = {info['chinese_name']}（{info['business_meaning']}）")

            return valid_updates if valid_updates else None

        except Exception as e:
            print(f"   ⚠️ 没理解：{e}")
            return None

    def respond(
        self,
        user_input: dict,
        project_name: str | None = None,
    ) -> dict[str, Any]:
        """
        处理 Agent 暂停后的用户响应，继续工作流。

        user_input 格式:
          {
            "agent": "scout",           # 当前等待的 agent
            "phase": "confirm_fields",   # 当前阶段
            "confirmed": {...},          # Scout.respond() 格式
            "action": "进入清洗",        # 用户选择的操作（next_step 阶段）
          }

        Returns:
            与 run() 返回格式相同的 dict
        """
        agent_name = user_input.get("agent", "")
        phase = user_input.get("phase", "")

        # 重新初始化 scribe（因为 respond() 是新调用，scribe 需要恢复状态）
        if self.output_mgr is None:
            self.output_mgr = OutputManager(self.config.output, project_name or "default")
        self.scribe = ScribeAgent(self.config.llm, self.event_bus, self.output_mgr.project_dir)

        if agent_name == "scout" and phase == "confirm_fields":
            # 恢复 Scout 状态
            scout = ScoutAgent(self.config.llm, self.event_bus, llm_client=self.llm_quick, scribe=self.scribe)
            # 从 user_input 恢复 Scout 内部状态
            scout._phase = "confirm_fields"
            scout._data_path = user_input.get("data_path", "")
            scout._query = user_input.get("query", "")
            scout._context = user_input.get("context")

            ir = scout.respond(user_input, project_id=project_name)

            if ir.final:
                # Scout 完成了，返回后续指令
                return {
                    "status": "scout_done",
                    "message": ir.message,
                    "phase": ir.phase,
                    "data": ir.data,
                    "final": True,
                }

            # Scout 再次暂停（next_step），返回给 UI
            return {
                "status": "scout_next_step",
                "phase": ir.phase,
                "message": ir.message,
                "actions": ir.actions,
                "pending_items": ir.pending_items,
                "data": ir.data,
                "final": ir.final,
            }

        elif agent_name == "scout" and phase == "next_step":
            action = user_input.get("action", "")
            if action in ("进入清洗", "继续"):
                # 进入清洗阶段
                return {
                    "status": "ready_for_cleaning",
                    "phase": "cleaning_first",
                    "message": "好的，进入清洗阶段",
                    "data": user_input.get("data", {}),
                }
            elif action in ("重新理解字段", "重新开始"):
                # 重新跑 Scout
                return {
                    "status": "restart_scout",
                    "phase": "scout_first",
                    "message": "好的，重新开始字段理解",
                }
            elif action in ("结束分析", "结束"):
                return {
                    "status": "done",
                    "message": "分析结束",
                }
            return {
                "status": "done",
                "message": "未知的操作",
            }

        # 未知 agent/phase
        return {
            "status": "error",
            "message": f"未知阶段: {agent_name}/{phase}",
        }

    def _save_field_descriptions(
        self,
        project_name: str,
        corrections: dict[str, dict[str, str]],
    ) -> None:
        """保存用户确认的字段描述到 memory/progress.yaml"""
        if not corrections:
            return

        try:
            # 构建 schema 更新
            schema_file = self.output_mgr.project_dir / "progress.yaml"
            import yaml

            # 读取现有 schema
            schema_data = {}
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
