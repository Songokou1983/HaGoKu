"""
Scribe Agent — 项目看板管理器（Step 3 简化版）

职责（仅 kanban 状态机 + 事件路由）：
- 监听 EventBus，维护 kanban.db 任务状态
- 提供 block/unblock/claim/complete/heartbeat 等任务门控
- init_pipeline 创建 Scout→Cleaner→Analyst→Reporter 任务链
- recover_field_descriptions：LLM 兜底恢复字段描述（Step 3 保留，Step 4 决定是否删除）

不再负责（Step 3 删除）：
- 4 通道文件管理：process_log.md / context.md / handover_notes.md
- record_interaction：跨 run 记忆（设计未落地）
- update_context：context.md phase 数据写入（无消费者）
- get_upstream_summary / generate_handover_note / _auto_generate_handover：handover 通道
- _get_context_data：context.md 解析
- _log / _on_thinking / _on_tool_* / _on_quality_check：纯日志写入
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ...config import LLMConfig
from ...observability.event_bus import EventBus
from ...observability.events import EventType
from ...storage.kanban import KanbanDB


class ScribeAgent:
    """Scribe：项目看板管理（kanban 状态机 + 事件路由 + 字段描述 LLM 兜底）"""

    def __init__(self, llm_config: LLMConfig, event_bus: EventBus, project_path: Path) -> None:
        self.role = "Scribe"
        self.llm_config = llm_config
        self.event_bus = event_bus
        self.project_path = Path(project_path)

        # KanbanDB（每个项目一个实例，通过路径单例化）
        self.kanban = KanbanDB.get_instance(self.project_path)

        # 加载 prompt.md（仅 recover_field_descriptions 使用，Step 4 再决定是否删除）
        self.prompt = self._load_prompt()

        # 事件钩子
        self.event_bus.subscribe(self._on_event)

    def _load_prompt(self) -> str:
        """从 prompt.md 加载角色定义（仅 recover_field_descriptions 使用）"""
        path = Path(__file__).parent / "prompt.md"
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    def _now(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    # ── 事件处理（Step 3 简化：仅 kanban 状态更新） ──

    def _on_event(self, event) -> None:
        """统一事件处理器，Step 3 仅处理 3 个影响 kanban 状态的事件"""
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
        # 优先复用 init_pipeline 创建的任务（状态为 ready）
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
                    description=f"Started at {self._now()}",
                )
                self.kanban.update_status(task_id, "todo")
                self.kanban.update_status(task_id, "ready")

    def _on_agent_completed(self, event) -> None:
        agent = event.agent
        result = event.data.get("result_summary", "")
        # 原子操作：claim → complete，防止中间崩溃导致任务卡死
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

    # ── 公共接口（kanban 状态查询 + 控制） ──

    def init_pipeline(self) -> str:
        """
        初始化分析 pipeline：创建 Scout → Cleaner → Analyst → Reporter 任务链。
        Scout 直接设为 ready（第一个运行），其余为 triage（等父任务完成自动 promote）。
        返回 Scout 任务 ID。
        """
        scout_id = self.kanban.create_task(
            agent="scout",
            title="Scout: 理解数据字段",
            description="加载数据，推断字段语义",
        )
        self.kanban.update_status(scout_id, "ready")

        cleaner_id = self.kanban.create_task(
            agent="cleaner",
            title="Cleaner: 清洗数据",
            description="检测异常并清洗数据",
            parent_id=scout_id,
        )

        analyst_id = self.kanban.create_task(
            agent="analyst",
            title="Analyst: 跑统计分析",
            description="执行统计分析",
            parent_id=cleaner_id,
        )

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

    # ── 字段描述恢复（LLM 兜底） ──

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

        Step 3 保留：3 个测试调用 + 0 生产调用方。Step 4 决定删除。
        """
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
        merged = {**existing}
        for col in missing:
            dtype_hint = (dtypes_safe or {}).get(col, "")
            if dtype_hint:
                merged[col] = f"字段 {col}（{dtype_hint}）"
            else:
                merged[col] = f"字段 {col}"
        merged["_scribe_fallback"] = True
        return merged
