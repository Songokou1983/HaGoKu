"""
Scribe Agent — 内部记录员

职责：
- 监听 EventBus，记录所有事件
- 维护项目看板（KanbanDB SQLite）
- 维护 context.md 接力棒文件

不与用户直接对话，只在后台工作。
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import yaml

from ...config import LLMConfig
from ...observability.event_bus import EventBus
from ...observability.events import EventType
from ...storage.kanban import KanbanDB


class ScribeAgent:
    """
    Scribe：内部记录员

    - 监听 EventBus，记录所有事件到 process_log.md
    - 维护项目 kanban.db（状态机 + 交接记录）
    - 维护 context.md（接力棒数据）
    """

    def __init__(self, llm_config: LLMConfig, event_bus: EventBus, project_path: Path) -> None:
        self.role = "Scribe"
        self.llm_config = llm_config
        self.event_bus = event_bus
        self.project_path = Path(project_path)

        # KanbanDB（每个项目一个）
        self.kanban = KanbanDB.get_instance(self.project_path)

        # 文件路径
        self.process_log_path = self.project_path / "process_log.md"
        self.context_path = self.project_path / "context.md"

        # 事件钩子
        self._register_hooks()

        # 初始化文件
        self._ensure_process_log()
        self._ensure_context()

    # ── 初始化 ────────────────────────────────────────────

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

        # claim 并完成当前 running 任务
        task = self.kanban.get_active_task(agent.lower())
        if task:
            if task["status"] == "running":
                self.kanban.complete_task(task["id"], result)
            elif task["status"] == "blocked":
                # 被 block 的任务：先 unblock 再 complete
                self.kanban.unblock_task(task["id"])
                self.kanban.claim_task(task["id"], f"{agent.lower()}_agent")
                self.kanban.complete_task(task["id"], result)

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
        reporter_id = self.kanban.create_task(
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

        # 更新 context.md
        if self.context_path.exists():
            content = self.context_path.read_text(encoding="utf-8")
            new_entry = (
                f'\n  - agent: {agent}\n'
                f'    timestamp: "{datetime.now().isoformat()}"\n'
                f'    user: "{user_input}"\n'
                f'    agent: "{agent_response[:80]}"'
            )
            if "interactions: []" in content:
                content = content.replace("interactions: []", f"interactions:[{new_entry}\n  ]")
            elif "interactions:" in content:
                content = re.sub(r"(\n  \]:)", f"{new_entry}\\1", content)
            self.context_path.write_text(content, encoding="utf-8")

    def update_context(self, phase: str, data: dict) -> None:
        """更新 context.md 中的某个阶段产出"""
        if not self.context_path.exists():
            return

        content = self.context_path.read_text(encoding="utf-8")

        # 替换对应 phase 的 data 块
        yaml_str = yaml.dump(data, default_flow_style=False, allow_unicode=True)
        indent_yaml = "\n".join(f"  {line}" for line in yaml_str.strip().split("\n"))

        # 匹配 phase 名下的 data 块
        pattern = rf"({phase} 产出\n\n```yaml\n)data:.*?(\n```)"
        if re.search(pattern, content, re.DOTALL):
            content = re.sub(pattern, rf"\1{indent_yaml}\2", content, flags=re.DOTALL)
        else:
            # 找不到就只更新 completed
            pattern2 = rf"({phase} 产出\n\n```yaml\n)completed: (true|false)"
            if re.search(pattern2, content):
                content = re.sub(pattern2, rf"\1completed: true", content)

        # 更新 current_phase
        content = re.sub(r"(current_phase: )\w+", rf"\1{phase}", content)

        self.context_path.write_text(content, encoding="utf-8")

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
