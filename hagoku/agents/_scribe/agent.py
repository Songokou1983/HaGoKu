"""
Scribe Agent — 内部记录员

职责：
- 监听 EventBus，记录所有事件
- 维护项目看板（KanbanDB SQLite）
- 维护 context.md 接力棒文件
- LLM 兜底恢复遗漏字段描述

不与用户直接对话，只在后台工作。
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from ...config import LLMConfig
from ...observability.event_bus import EventBus
from ...observability.events import EventType
from ...storage.kanban import KanbanDB


class ScribeAgent:
    """
    Scribe：内部记录员（项目管家）

    4 大通道：
    - Channel 1: process_log.md — 项目全过程时间线档案
    - Channel 2: context.md — Agent 间接力棒（Markdown 叙事 + YAML 数据）
    - Channel 3: kanban.db — 看板状态机（7 状态流转）
    - Channel 4: handover_notes.md — LLM 生成的交接笔记（持久的项目知识）

    额外能力：
    - LLM 兜底恢复遗漏字段描述（recover_field_descriptions）
    - 上游摘要生成（get_upstream_summary）
    """

    def __init__(self, llm_config: LLMConfig, event_bus: EventBus, project_path: Path) -> None:
        self.role = "Scribe"
        self.llm_config = llm_config
        self.event_bus = event_bus
        self.project_path = Path(project_path)

        # 加载 prompt.md（角色定义）
        self.prompt = self._load_prompt()

        # KanbanDB（每个项目一个）
        self.kanban = KanbanDB.get_instance(self.project_path)

        # 文件路径 — 4 通道
        self.process_log_path = self.project_path / "process_log.md"   # Channel 1
        self.context_path = self.project_path / "context.md"           # Channel 2
        self.handover_notes_path = self.project_path / "handover_notes.md"  # Channel 4

        # 事件钩子
        self._register_hooks()

        # 初始化文件
        self._ensure_process_log()
        self._ensure_context()
        self._ensure_handover_notes()

    # ── 初始化 ────────────────────────────────────────────

    def _load_prompt(self) -> str:
        """从 prompt.md 加载角色定义"""
        path = Path(__file__).parent / "prompt.md"
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    def _ensure_process_log(self) -> None:
        if not self.process_log_path.exists():
            self.process_log_path.write_text(
                "# Process Log\n\n```yaml\nruns: []\n```\n",
                encoding="utf-8",
            )

    def _ensure_context(self) -> None:
        if not self.context_path.exists():
            self._write_default_context()

    def _write_default_context(self) -> None:
        self.context_path.write_text(
            "# Context — 接力棒\n\n"
            "## 项目信息\n\n"
            "```yaml\n"
            f"project: {self.project_path.name}\n"
            f"current_phase: none\n"
            "```\n\n"
            "## Scout 产出\n\n"
            "```yaml\n"
            "completed: false\n"
            "data: {}\n"
            "```\n\n"
            "## Cleaner 产出\n\n"
            "```yaml\n"
            "completed: false\n"
            "data: {}\n"
            "```\n\n"
            "## Analyst 产出\n\n"
            "```yaml\n"
            "completed: false\n"
            "results: []\n"
            "```\n\n"
            "## Reporter 产出\n\n"
            "```yaml\n"
            "completed: false\n"
            "report_path: ''\n"
            "```\n",
            encoding="utf-8",
        )

    def _register_hooks(self) -> None:
        # EventBus 使用 subscribe(callback)，Scribe 是单一 callback 监听所有事件
        self.event_bus.subscribe(self._on_event)

    def _on_event(self, event) -> None:
        """统一事件处理器，根据 event.type 路由"""
        etype = event.event_type
        if etype == EventType.AGENT_STARTED:
            self._on_agent_started(event)
        elif etype == EventType.AGENT_COMPLETED:
            self._on_agent_completed(event)
        elif etype == EventType.AGENT_FAILED:
            self._on_agent_failed(event)
        elif etype == EventType.AGENT_THINKING:
            self._on_agent_thinking(event)
        elif etype == EventType.TOOL_CALLED:
            self._on_tool_called(event)
        elif etype == EventType.TOOL_RESULT:
            self._on_tool_result(event)
        elif etype == EventType.TOOL_ERROR:
            self._on_tool_error(event)
        elif etype == EventType.QUALITY_CHECK:
            self._on_quality_check(event)

    def _now(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    # ── 事件处理 ────────────────────────────────────────────

    def _on_agent_started(self, event) -> None:
        agent = event.agent
        goal = event.data.get("goal", "")
        self._log(f"{agent} STARTED: {goal}")

        # 优先复用 init_pipeline 创建的任务（状态为 ready）
        ready_task = self.kanban.get_ready_task(agent.lower())
        if ready_task:
            ok = self.kanban.claim_task(ready_task["id"], f"{agent.lower()}_agent")
            if not ok:
                self._log(f"{agent} claim failed, task already taken")
        else:
            # 没有预创建任务时，正常创建
            task = self.kanban.get_active_task(agent.lower())
            if not task:
                task_id = self.kanban.create_task(
                    agent=agent.lower(),
                    title=f"{agent}: {goal}",
                    description=f"Started at {self._now()}",
                )
                self.kanban.update_status(task_id, "todo")
                self.kanban.update_status(task_id, "ready")

    def _on_agent_completed(self, event) -> None:
        agent = event.agent
        result = event.data.get("result_summary", "")
        self._log(f"{agent} COMPLETED: {result}")

        # 原子操作：claim → complete，防止中间崩溃导致任务卡死
        lock_holder = f"{agent.lower()}_agent"
        self.kanban.complete_agent_task_atomic(
            agent=agent.lower(),
            lock_holder=lock_holder,
            result=result,
        )

        # ── Channel 4: 自动生成交接笔记 ──
        self._auto_generate_handover(agent, event)

        # ── 自动 promote 下游任务 ──
        self._auto_promote_next(agent)

    def _on_agent_failed(self, event) -> None:
        agent = event.agent
        error = event.data.get("error", "")
        self._log(f"{agent} FAILED: {error}")

        task = self.kanban.get_active_task(agent.lower())
        if task and task["status"] == "running":
            self.kanban.update_status(task["id"], "blocked")
            self.kanban.add_comment(task["id"], "system", f"Failed: {error}")

    def _on_agent_thinking(self, event) -> None:
        agent = event.agent
        thought = event.data.get("thought", "")
        if thought:
            self._log(f"{agent} THINKING: {thought[:100]}")

    def _on_tool_called(self, event) -> None:
        tool = event.data.get("tool", "")
        args = event.data.get("args_summary", "")
        self._log(f"TOOL_CALL: {tool}({args})")

    def _on_tool_result(self, event) -> None:
        summary = event.data.get("summary", "")
        self._log(f"TOOL_RESULT: {summary[:80]}")

    def _on_tool_error(self, event) -> None:
        error = event.data.get("error", "")
        self._log(f"TOOL_ERROR: {error}")

    def _on_quality_check(self, event) -> None:
        verdict = event.data.get("verdict", "")
        detail = event.data.get("detail", "")
        self._log(f"QUALITY_CHECK: [{verdict}] {detail}")

    def _log(self, entry: str) -> None:
        timestamp = self._now()
        line = f"\n[{timestamp}] {entry}"

        content = self.process_log_path.read_text(encoding="utf-8")
        if "```yaml" in content:
            content = content + line
        self.process_log_path.write_text(content, encoding="utf-8")

    # ── 公共接口 ────────────────────────────────────────────

    def init_pipeline(self) -> str:
        """
        初始化分析 pipeline：创建 Scout → Cleaner → Analyst → Reporter 任务链。
        Scout 直接设为 ready（第一个运行），其余为 triage（等父任务完成自动 promote）。
        返回 Scout 任务 ID。
        """
        # Scout 是根节点，直接 ready（第一个运行）
        scout_id = self.kanban.create_task(
            agent="scout",
            title="Scout: 理解数据字段",
            description="加载数据，推断字段语义",
        )
        self.kanban.update_status(scout_id, "ready")

        # Cleaner 依赖 Scout（triage，等待 Scout 完成自动 promote）
        cleaner_id = self.kanban.create_task(
            agent="cleaner",
            title="Cleaner: 清洗数据",
            description="检测异常并清洗数据",
            parent_id=scout_id,
        )

        # Analyst 依赖 Cleaner
        analyst_id = self.kanban.create_task(
            agent="analyst",
            title="Analyst: 跑统计分析",
            description="执行统计分析",
            parent_id=cleaner_id,
        )

        # Reporter 是叶子节点
        self.kanban.create_task(
            agent="reporter",
            title="Reporter: 生成报告",
            description="生成分析报告",
            parent_id=analyst_id,
        )

        return scout_id

    def claim_task(self, agent: str) -> str | None:
        """Claim 当前 Agent 的任务（从 ready 或 running 状态），返回 task_id"""
        task = self.kanban.get_any_task(agent.lower())
        if not task:
            return None

        ok = self.kanban.claim_task(task["id"], f"{agent.lower()}_agent")
        return task["id"] if ok else None

    def block_task(self, agent: str, reason: str) -> bool:
        """Block 当前 Agent 的任务（等用户输入）"""
        task = self.kanban.get_any_task(agent.lower())
        if not task:
            return False
        return self.kanban.block_task(task["id"], reason)

    def unblock_task(self, agent: str) -> bool:
        """Unblock 当前 Agent 的任务"""
        task = self.kanban.get_active_task(agent.lower())
        if not task:
            return False
        return self.kanban.unblock_task(task["id"])

    def complete_task(self, agent: str, result: str) -> bool:
        """完成当前 Agent 的任务"""
        task = self.kanban.get_active_task(agent.lower())
        if not task:
            return False
        return self.kanban.complete_task(task["id"], result)

    def heartbeat(self, agent: str) -> bool:
        """长任务续期"""
        task = self.kanban.get_active_task(agent.lower())
        if not task:
            return False
        return self.kanban.heartbeat(task["id"], f"{agent.lower()}_agent")

    def add_comment(self, agent: str, author: str, body: str) -> str | None:
        """给当前 Agent 任务添加评论"""
        task = self.kanban.get_active_task(agent.lower())
        if not task:
            return None
        return self.kanban.add_comment(task["id"], author, body)

    def record_interaction(self, agent: str, user_input: str, agent_response: str) -> None:
        """记录与用户的对话"""
        self._log(f"INTERACTION {agent}: user='{user_input}' → agent='{agent_response}'")

        # 更新 context.md — 使用 YAML 解析而非正则替换
        if self.context_path.exists():
            content = self.context_path.read_text(encoding="utf-8")
            try:
                doc = yaml.safe_load(content)
            except yaml.YAMLError:
                return

            if not isinstance(doc, dict):
                return

            interactions = doc.get("interactions", [])
            if not isinstance(interactions, list):
                interactions = []
            interactions.append({
                "agent": agent,
                "timestamp": datetime.now().isoformat(),
                "user": user_input,
                "agent_response": agent_response[:80],
            })
            doc["interactions"] = interactions

            # 重新序列化：保留 YAML 注释区域之外的内容
            # 策略：用 yaml.dump 重写整个文件，保证 YAML 结构正确
            self.context_path.write_text(
                yaml.dump(doc, default_flow_style=False, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )

    def update_context(self, phase: str, data: dict) -> None:
        """更新 context.md 中的某个阶段产出 — 使用 YAML 解析而非正则替换"""
        if not self.context_path.exists():
            return

        content = self.context_path.read_text(encoding="utf-8")
        try:
            doc = yaml.safe_load(content)
        except yaml.YAMLError:
            return

        if not isinstance(doc, dict):
            return

        # 更新对应 phase 的 data
        phases = doc.get("phases", doc)  # 支持 phases 键或顶层 phase 键
        if isinstance(phases, dict) and phase in phases:
            target = phases[phase]
            if isinstance(target, dict):
                target["data"] = data
                target["completed"] = True
        elif isinstance(doc, dict):
            # 顶层直接有 phase 键
            doc[phase] = {"data": data, "completed": True}

        # 更新 current_phase
        doc["current_phase"] = phase

        # 重新序列化
        self.context_path.write_text(
            yaml.dump(doc, default_flow_style=False, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

    def generate_handover_note(
        self,
        from_agent: str,
        to_agent: str,
        source_summary: dict,
        context: dict | None = None,
    ) -> str:
        """
        生成交接笔记：纯数据搬运，不做任何格式化或语义转换。

        P0 通道原则：代码只负责 serialize → transport。
        下游 Agent 的 LLM 自行解读 raw JSON。

        Args:
            from_agent: 上游 Agent 名
            to_agent: 下游 Agent 名
            source_summary: 上游 Agent 的产出摘要 dict
            context: 当前项目的完整上下文（未使用，保留接口兼容）

        Returns:
            source_summary 的 JSON 序列化文本
        """
        import json

        self._log(f"HANDOVER transport: {from_agent} → {to_agent}")
        return json.dumps(source_summary, ensure_ascii=False, indent=2, default=str)

    def _get_context_data(self) -> dict:
        """读取 context.md 中所有阶段的产出数据，返回聚合 dict。

        供 generate_handover_note 和编排层使用，提供项目的全过程快照。

        M5 修复：用完整的 yaml.safe_load 解析整个文件替代正则提取阶段产出。
        context.md 是 YAML 前端数据 + Markdown 叙述的混合格式，
        不能直接用 yaml.safe_load 整个文件。
        但拆分为 YAML fenced 代码块逐个解析即可。
        """
        if not self.context_path.exists():
            return {}

        content = self.context_path.read_text(encoding="utf-8")
        result: dict = {}

        # 使用 yaml.safe_load_all 处理多文档 YAML，先提取所有 fenced yaml 块
        blocks = re.findall(r"```yaml\n(.*?)\n```", content, re.DOTALL)

        # 按顺序分配给各阶段（context.md 中顺序固定）
        phases = ("Scout", "Cleaner", "Analyst", "Reporter")
        for i, block in enumerate(blocks):
            if i >= len(phases):
                break
            try:
                parsed = yaml.safe_load(block)
                if isinstance(parsed, dict):
                    result[phases[i].lower()] = parsed
            except yaml.YAMLError:
                pass

        return result

    def get_task_status(self, agent: str) -> dict | None:
        """获取当前 Agent 任务状态（含 done）"""
        task = self.kanban.get_any_task(agent.lower())
        if not task:
            return None
        return {
            "id": task["id"],
            "status": task["status"],
            "title": task["title"],
            "description": task.get("description", ""),
        }

    def get_pipeline_status(self) -> dict[str, str]:
        """获取整个 pipeline 状态"""
        agents = ["scout", "cleaner", "analyst", "reporter"]
        result = {}
        for agent in agents:
            task = self.kanban.get_any_task(agent)
            result[agent] = task["status"] if task else "none"
        return result

    def get_stats(self) -> dict:
        """获取看板统计"""
        return self.kanban.get_stats()

    # ── Channel 4: handover_notes.md ─────────────────────

    def _ensure_handover_notes(self) -> None:
        """确保 handover_notes.md 存在（Channel 4 初始化）"""
        if not self.handover_notes_path.exists():
            self.handover_notes_path.write_text(
                "# 交接笔记（Handover Notes）\n\n"
                "> 本文件由 Scribe 自动生成，记录每个 Agent 向下游的交接内容。\n"
                "> 每次上游 Agent 完成后自动追加，形成完整的项目知识传承链。\n\n"
                "---\n\n",
                encoding="utf-8",
            )

    def append_handover_notes(self, note: str) -> None:
        """追加交接笔记到 handover_notes.md（Channel 4 写入）"""
        self._ensure_handover_notes()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"\n<!-- 生成时间: {timestamp} -->\n\n{note}\n\n---\n"
        with open(self.handover_notes_path, "a", encoding="utf-8") as f:
            f.write(entry)

    def get_upstream_summary(self, agent: str) -> str | None:
        """
        获取指定 Agent 的上游交接笔记摘要，供编排层注入到下游 Agent prompt。

        返回最近一次从上游到当前 Agent 的交接笔记内容。
        若 Agent 是第一个（scout），返回 None（无上游）。

        编排层用法：
            upstream = scribe.get_upstream_summary("analyst")
            if upstream:
                analyst_prompt += f"\\n## 上游摘要\\n{upstream}"
        """
        if agent.lower() == "scout":
            return None  # Scout 无上游

        pipeline_order = ["scout", "cleaner", "analyst", "reporter"]
        try:
            idx = pipeline_order.index(agent.lower())
        except ValueError:
            return None

        if idx == 0:
            return None

        from_agent = pipeline_order[idx - 1]
        to_agent = agent.lower()

        # 从 handover_notes.md 中查找对应的交接笔记
        if not self.handover_notes_path.exists():
            return None

        content = self.handover_notes_path.read_text(encoding="utf-8")

        # 匹配标题：## 数据侦察 → 数据清洗 交接笔记
        phase_labels: dict[str, str] = {
            "scout": "数据侦察",
            "cleaner": "数据清洗",
            "analyst": "统计分析",
            "reporter": "报告生成",
        }

        from_label = phase_labels.get(from_agent, from_agent)
        to_label = phase_labels.get(to_agent, to_agent)

        # 最近一次匹配（倒序查找，取最后一个）
        pattern = rf"## {from_label} → {to_label} 交接笔记\n(.*?)\n---"
        matches = list(re.finditer(pattern, content, re.DOTALL))
        if not matches:
            return None

        # 取最后一个匹配（最近生成的）
        last_match = matches[-1]
        note_block = last_match.group(1).strip()

        # 格式化输出：加上标题和上游标识
        return (
            f"## 上游摘要（来自 {from_label} 阶段）\n\n"
            f"> 以下内容由 Scribe 根据 {from_label} Agent 的实际产出自动生成，"
            f"帮助你理解项目当前的全过程进展。\n\n"
            f"{note_block}"
        )

    def _auto_generate_handover(self, agent: str, event) -> None:
        """上游 Agent 完成后，自动生成交接笔记（LLM 驱动全过程理解版）。

        在 _on_agent_completed 中调用，为下游 Agent 准备上下文。
        增强点：
        1. 聚合 context.md 中所有已完成阶段的完整产出数据
        2. 纳入看板任务链状态（依赖/阻塞/完成）
        3. 引用已有的历史交接笔记作为延续性上下文
        4. 将清洗影响（_cleaning_impact）作为交接内容的一部分传递
        """
        pipeline = ["scout", "cleaner", "analyst", "reporter"]
        try:
            idx = pipeline.index(agent.lower())
        except ValueError:
            return

        # Reporter 完成后无下游，无需生成
        downstream = pipeline[idx + 1] if idx + 1 < len(pipeline) else None
        if downstream is None:
            return

        # ==== 构建丰富的上游产出摘要（不再仅依赖 event 中的简短字符串） ====
        source_summary: dict[str, Any] = {}

        # 1. 从 event 中提取基础摘要
        raw_summary = event.data.get("result_summary", {})
        if isinstance(raw_summary, str):
            source_summary["summary"] = raw_summary
        elif isinstance(raw_summary, dict):
            source_summary.update(raw_summary)

        # 2. 聚合 context.md 中所有阶段产出（全过程上下文）
        ctx = self._get_context_data()
        phase_ctx = ctx.get(agent.lower(), {})

        # 将上游阶段的 data 注入 source_summary
        if "data" in phase_ctx and isinstance(phase_ctx["data"], dict):
            source_summary["phase_data"] = phase_ctx["data"]

        # 3. 纳入所有已完成阶段的关键信息作为"全过程理解"
        completed_phases: dict[str, dict] = {}
        for phase_key, phase_data in ctx.items():
            if phase_data.get("completed") is True or phase_key == agent.lower():
                completed_phases[phase_key] = {
                    "completed": phase_data.get("completed", False),
                    "data_keys": list(phase_data.get("data", {}).keys()) if isinstance(phase_data.get("data"), dict) else [],
                }
        source_summary["completed_phases"] = completed_phases

        # 4. 看板状态：当前 pipeline 状态 + Agent 任务链
        kanban_status = self.get_pipeline_status()
        source_summary["kanban_status"] = kanban_status

        # 5. 引用已有的历史交接笔记作为延续性上下文
        prior_handover = ""
        if self.handover_notes_path.exists():
            handover_content = self.handover_notes_path.read_text(encoding="utf-8")
            # 提取最后一条交接笔记的标题和产出摘要（不超过 500 字）
            last_sections = handover_content.split("---")
            if len(last_sections) >= 2:
                prior_handover = last_sections[-2].strip()[:500]
        if prior_handover:
            source_summary["_prior_handover_context"] = prior_handover

        # 生成交接笔记（LLM 将以更丰富的上下文生成全过程理解的笔记）
        note = self.generate_handover_note(
            from_agent=agent.lower(),
            to_agent=downstream,
            source_summary=source_summary,
            context=phase_ctx,
        )

        # 追加到 handover_notes.md (Channel 4)
        self.append_handover_notes(note)

        self._log(f"HANDOVER_SAVED: {agent} → {downstream}")

    def _auto_promote_next(self, agent: str) -> None:
        """上游 Agent 完成后，自动 promote 下游任务为 ready。

        Scout done → Cleaner ready
        Cleaner done → Analyst ready
        Analyst done → Reporter ready
        Reporter done → Pipeline 完成（父任务 done）
        """
        pipeline = ["scout", "cleaner", "analyst", "reporter"]
        try:
            idx = pipeline.index(agent.lower())
        except ValueError:
            return

        downstream = pipeline[idx + 1] if idx + 1 < len(pipeline) else None
        if downstream is None:
            # Reporter 完成 → 所有任务完成
            self._log("PIPELINE: All agents completed")
            # 将所有 remaining 任务标记 done
            for ag in pipeline:
                task = self.kanban.get_any_task(ag)
                if task and task["status"] != "done":
                    self.kanban.update_status(task["id"], "done")
            return

        # Promote 下游任务
        task = self.kanban.get_any_task(downstream)
        if task and task["status"] in ("todo", "triage"):
            self.kanban.update_status(task["id"], "ready")
            self._log(f"PROMOTE: {downstream} → ready")

    # ── 字段描述恢复（LLM 兜底） ──────────────────────────

    def recover_field_descriptions(
        self,
        row_count: int,
        col_count: int,
        existing: dict[str, str],
        sample_rows: list[dict[str, object]] | None = None,
        dtypes: dict[str, str] | None = None,
        column_names: list[str] | None = None,
    ) -> dict[str, str]:
        """
        LLM 兜底恢复遗漏列描述。

        仅在 Scout 产出部分列描述缺失时调用。使用不同 prompt 策略，
        要求只生成白话中文短语，禁止技术术语。

        Args:
            row_count: 数据总行数
            col_count: 数据总列数
            existing: 已有列描述 {col_name: desc}
            sample_rows: 样本行（前 5-10 行），用于上下文推断
            dtypes: 列数据类型 {col_name: dtype_str}
            column_names: 所有列名（用于推断缺失列）

        Returns:
            补全后的完整 {col_name: desc} 字典
        """
        import json

        if column_names is None:
            column_names = list(existing.keys())

        missing = [c for c in column_names if c not in existing or not existing[c]]
        if not missing:
            return existing

        # 转义样本行中的复杂类型（日期等）为字符串
        serializable_rows: list[dict[str, str | None]] = []
        if sample_rows:
            for row in sample_rows[:8]:
                safe: dict[str, str | None] = {}
                for k, v in row.items():
                    if v is None:
                        safe[k] = None
                    elif isinstance(v, (str, int, float, bool)):
                        safe[k] = str(v)
                    else:
                        safe[k] = str(v)
                serializable_rows.append(safe)

        dtypes_safe = dtypes or {}

        prompt = f"""你是一位数据分析师，现在需要帮助理解数据集的列含义。

数据概览：{row_count} 行 × {col_count} 列

已有的列描述（不要修改）：
{json.dumps({k: v for k, v in existing.items() if v}, ensure_ascii=False, indent=2)}

缺失描述的列（需要你生成）：
{json.dumps(missing, ensure_ascii=False)}

样本数据（前 {len(serializable_rows)} 行）：
{json.dumps(serializable_rows, ensure_ascii=False, indent=2)}

列数据类型：
{json.dumps({k: dtypes_safe.get(k, "未知") for k in missing}, ensure_ascii=False, indent=2)}

要求：
1. 为每个缺失描述的列生成一句白话中文描述（10-25字）
2. 描述要面向业务用户，禁止出现 dtype/int64/float64 等技术术语
3. 参考样本数据值和数据类型推断业务含义
4. 不要重复已有描述中的内容
5. 返回严格的 JSON 对象，格式：{{"列名": "描述"}}

只返回 JSON，不要任何其他文字。"""

        try:
            from ...llm.client import create_quick_client

            client = create_quick_client(self.llm_config)
            system_content = self.prompt if self.prompt else "你是数据分析助手，只返回 JSON 对象。"
            response = client.chat.completions.create(
                model=self.llm_config.model_quick or self.llm_config.model,
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=max(256, len(missing) * 64),
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content.strip()

            # 尝试提取 JSON
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()

            recovered = json.loads(content)
            if isinstance(recovered, dict):
                merged = {**existing}
                for col, desc in recovered.items():
                    if col in missing and isinstance(desc, str) and desc.strip():
                        merged[col] = desc.strip()
                return merged

        except Exception:
            import logging

            logging.getLogger("hagoku").warning(
                "Scribe LLM recover failed — using fallback placeholder for %d missing columns: %s",
                len(missing),
                missing,
            )

        # ==== CHANNEL ZONE: 兜底占位，禁止语义推断 ====
        # 仅生成"字段 xxx（dtype）"格式的占位描述，不根据列名做任何语义猜测。
        # 此路径仅在 LLM 完全不可达时触发，确保下游至少有字段标识符可用。
        merged = {**existing}
        for col in missing:
            dtype_hint = (dtypes_safe or {}).get(col, "")
            if dtype_hint:
                merged[col] = f"字段 {col}（{dtype_hint}）"
            else:
                merged[col] = f"字段 {col}"
        merged["_scribe_fallback"] = True  # 标记降级，调用方可据此区分 LLM 产出 vs 占位
        return merged

