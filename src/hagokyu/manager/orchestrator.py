"""HaGoKu Manager — 编排器，规则+AI 双驱动"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from ..config import HaGoKuConfig
from ..guardrails.statistical import StatisticalGuardrails
from ..observability.display import TerminalDisplay
from ..observability.event_bus import EventBus
from ..observability.events import EventType
from ..storage.database import HaGoKuDB
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

        Returns:
            运行结果摘要
        """
        run_start = datetime.now()
        user_mode = user_mode or self.config.user_mode.default_mode

        # 1. 创建项目
        if project_name is None:
            from pathlib import Path

            project_name = Path(data_path).stem.replace(" ", "_")

        self.event_bus.emit(EventType.RUN_STARTED, "Manager", {
            "query": query,
            "project": project_name,
            "mode": mode,
        })

        self.output_mgr = OutputManager(self.config.output, project_name)
        run_dir = self.output_mgr.create_run_dir()
        run_id = run_dir.name

        # 创建数据库记录
        self.db.create_project(project_name, data_path=data_path)
        plan = self._create_plan(query, mode)
        self.db.create_run(run_id, project_name, query=query, plan=plan, manager_mode=mode)

        # 2. 初始化 Agent
        scout = ScoutAgent(self.config.llm, self.event_bus)
        cleaner = CleanerAgent(self.config.llm, self.event_bus)
        analyst = AnalystAgent(self.config.llm, self.event_bus)
        reporter = ReporterAgent(self.config.llm, self.event_bus)

        try:
            # 3. Scout: 数据侦察
            context = scout.run(data_path, query)

            # 3.5 用户交互：确认不确定的字段
            uncertain = context.get_uncertain_columns()
            if uncertain and user_mode != "quick":
                # 在标准/专家模式下，等待用户确认
                # （实际交互在 CLI 层处理，这里只是标记）
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

            # 5. 质量检查
            self.event_bus.emit(EventType.QUALITY_CHECK, "Manager", {
                "verdict": "pass" if cleaning_report.impact_rate < self.config.manager.cleaning_impact_warning else "warning",
                "detail": f"清洗影响率 {cleaning_report.impact_rate:.1%}",
            })

            # 6. Analyst: 统计分析
            results = analyst.run(df_clean, context, plan)

            # 7. Reporter: 生成报告
            output_path = str(run_dir / "output" / "report.html")
            report = reporter.run(
                results=results,
                context=context,
                cleaning_summary=cleaning_report.to_dict(),
                project_name=project_name,
                query=query,
                output_path=output_path,
                formats=formats or self.config.output.formats,
            )

            # 8. 保存运行元数据
            run_meta = {
                "run_id": run_id,
                "project": project_name,
                "query": query,
                "plan": plan,
                "n_results": len(results),
                "cleaning_impact": cleaning_report.impact_rate,
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

            # 10. 创建 latest 链接
            self.output_mgr.create_latest_symlink(run_dir)

            # 11. 事件日志
            events_path = run_dir / "events.jsonl"
            self.event_bus.save_to_file(events_path)

            # 12. 发射完成事件
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
