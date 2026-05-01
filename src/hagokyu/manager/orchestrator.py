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
from ..agents.analyst import AnalystAgent, AnalysisResult
from ..agents.cleaner import CleanerAgent
from ..agents.reporter import ReporterAgent
from ..agents.scout import DataContext, ScoutAgent
from ..tools.data_io import save_data


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

        # 订阅显示
        self.event_bus.subscribe(self.display)

        # 规则引擎
        self.rule_engine = RuleEngine()

        # 护栏
        self.guardrails = StatisticalGuardrails()

    def run(
        self,
        data_path: str,
        query: str = "",
        *,
        project_name: str | None = None,
        mode: str = "standard",
        user_mode: str | None = None,
        output_dir: str | None = None,
        formats: list[str] | None = None,
        resume: bool = False,
        schema_path: str | None = None,
    ) -> dict[str, Any]:
        """
        主入口：执行完整分析流程

        Args:
            data_path: 数据文件路径
            query: 用户的分析问题
            project_name: 项目名（默认从文件名推断）
            mode: Manager 模式 (local_weak / local_strong / cloud / pure_rule)
            user_mode: 用户模式 (quick / standard / expert)
            output_dir: 自定义输出目录
            formats: 报告输出格式
            resume: 是否从上次断点继续
            schema_path: 外部 schema.yaml 路径

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
            "mode": mode,
        })

        self.output_mgr = OutputManager(self.config.output, project_name)
        schema_file = self.output_mgr.project_dir / "schema.yaml"
        self.memory = MemoryManager(self.db, schema_path=schema_file)

        # 处理 --schema 参数
        if schema_path:
            n = self.memory.import_schema_yaml(project_name, Path(schema_path))
            if n > 0:
                self.event_bus.emit(EventType.AGENT_THINKING, "Manager", {
                    "thought": f"📄 导入了 {n} 条 schema 定义",
                })

        run_dir = self.output_mgr.create_run_dir()
        run_id = run_dir.name

        # 创建数据库记录
        self.db.create_project(project_name, data_path=data_path)
        plan = self._create_plan(query, mode)
        self.db.create_run(run_id, project_name, query=query, plan=plan, manager_mode=mode)

        # 初始化 Agent
        scout = ScoutAgent(self.config.llm, self.event_bus)
        cleaner = CleanerAgent(self.config.llm, self.event_bus)
        analyst = AnalystAgent(self.config.llm, self.event_bus)
        reporter = ReporterAgent(self.config.llm, self.event_bus)

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

        try:
            # Scout + Cleaner（如果不是 resume）
            if context is None:
                # 3. Scout: 数据侦察（传入 MemoryManager）
                context = scout.run(data_path, query, project_id=project_name, memory=self.memory)

                # 3.5 用户交互：确认不确定的字段
                uncertain = context.get_uncertain_columns()
                if uncertain and user_mode != "quick":
                    self.event_bus.emit(EventType.USER_INPUT_REQUESTED, "Manager", {
                        "question": f"有 {len(uncertain)} 个字段需要确认，是否继续？",
                        "uncertain_columns": [s.column_name for s in uncertain],
                    })

                # 4. Cleaner: 数据清洗
                df_clean, cleaning_report = cleaner.run(
                    data_path, context,
                    impact_warning=self.config.manager.cleaning_impact_warning,
                )

                # 保存清洗后数据
                cleaned_path = self.output_mgr.data_dir / f"cleaned_{run_id}.parquet"
                save_data(df_clean, cleaned_path)
                cleaned_path_str = str(cleaned_path)

                # 保存 resume 状态
                self.memory.save_resume_state(
                    project_name, "cleaned",
                    cleaned_path=cleaned_path_str,
                    context=context, run_id=run_id,
                )

                # 5. 质量检查
                self.event_bus.emit(EventType.QUALITY_CHECK, "Manager", {
                    "verdict": "pass" if cleaning_report.impact_rate < self.config.manager.cleaning_impact_warning else "warning",
                    "detail": f"清洗影响率 {cleaning_report.impact_rate:.1%}",
                })

            # 6. Analyst: 统计分析
            assert df_clean is not None and context is not None
            results = analyst.run(df_clean, context, plan)

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
                user_mode=user_mode,
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

            # 10. 学习 + 导出 schema.yaml
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

    def _create_plan(self, query: str, mode: str) -> dict[str, Any]:
        """
        创建分析计划

        规则权重 + AI 权重 双驱动：
        - local_weak: 90% 规则 + 10% AI
        - local_strong: 50% 规则 + 50% AI
        - cloud: 10% 规则 + 90% AI
        - pure_rule: 100% 规则
        """
        rule_weight = self.config.manager.rule_weight
        llm_weight = self.config.manager.llm_weight

        # 1. 规则匹配
        rule_plan = self.rule_engine.match_plan(query)

        if rule_plan and rule_weight >= 0.9:
            # 规则权重高，直接用规则结果
            return rule_plan

        if rule_plan and rule_weight > 0:
            # 混合模式：规则为基础，AI 可调整
            plan = rule_plan.copy()
            plan["rule_match"] = True
            plan["rule_confidence"] = rule_weight
            return plan

        # 2. 无规则匹配或 AI 权重高 → 默认通用分析
        return {
            "plan_name": "通用分析",
            "agents": ["scout", "cleaner", "analyst", "reporter"],
            "analyst_focus": ["regression", "hypothesis_test", "correlation"],
            "query": query,
            "rule_match": False,
        }

    def _learn_from_run(
        self,
        project_name: str,
        context: DataContext,
        results: list[AnalysisResult],
        cleaning_report: Any,
    ) -> None:
        """从本次运行中学习，将确认的信息存入记忆"""
        learned = 0

        # 1. 学习目标变量：如果 Scout 推断了目标变量且分析成功了，记住
        target_candidates = context.get_target_candidates()
        for sem in target_candidates:
            if sem.confidence >= 0.8:
                self.db.learn_target_variable(project_name, sem.column_name)
                learned += 1

        # 2. 学习清洗偏好：记录此次用的清洗策略
        if hasattr(cleaning_report, "operations"):
            for op in cleaning_report.operations:
                self.db.learn_cleaning_preference(
                    project_name,
                    op.column,
                    op.strategy.value,
                    reason=op.reason,
                )
                learned += 1

        # 3. 学习分析模式：记录查询→计划匹配结果
        plan = self.rule_engine.match_plan(context.data_path)  # 不会真正用 data_path
        # 改为记录实际使用的分析类型
        for result in results:
            self.db.save_memory(
                project_name,
                "analysis_pattern",
                result.analysis_type,
                value={"question": result.question, "significance": result.significance},
                source="auto",
                confidence=0.6,
            )
            learned += 1

        if learned > 0:
            self.event_bus.emit(EventType.AGENT_THINKING, "Manager", {
                "thought": f"🧠 学习了 {learned} 条记忆，下次分析将自动应用",
            })
