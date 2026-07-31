"""HaGoKuApp — 进程级应用单例

持有 ProjectRepository（文件 I/O）和当前活跃 Orchestrator。
API 层通过 app.state 访问，不再使用全局变量。

职责：
- 项目 CRUD（delegate 到 Repository）
- Orchestrator 生命周期（切换/加载/恢复）
- 状态快照（供前端恢复 UI）
- 忙检测（防止并发分析）
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("hagoku.app")



class HaGoKuApp:
    """进程级应用单例。

    API 层用法：
        app = request.app.state.hagoku_app
        orch = app.orch
        snap = app.switch_project("my_project")
    """

    def __init__(self, config: Any) -> None:
        self.config = config
        from hagoku.repository.project import ProjectRepository
        self._repo = ProjectRepository(config.output.project_dir)
        self._active_project: str | None = None
        self._active_orch: Any = None

    # ── Repository delegate ────────────────────────────────────

    def list_projects(self) -> list[str]:
        """返回项目名列表。"""
        return [p.name for p in self._repo.list_projects()]

    def create_project(self, name: str) -> bool:
        """创建新项目。"""
        try:
            from hagoku.manager.orchestrator import Orchestrator
            self._repo.create(name)
            self._active_project = name
            self._active_orch = Orchestrator(self.config)
            self._active_orch._project_name = name
            return True
        except Exception:
            logger.warning("create_project 失败: %s", name, exc_info=True)
            return False

    def delete_project(self, name: str) -> bool:
        """安全删除项目。"""
        if self._active_project == name:
            self._active_project = None
            self._active_orch = None
        try:
            return self._repo.delete(name)
        except Exception:
            logger.warning("delete_project 失败: %s", name, exc_info=True)
            return False

    # ── Orchestrator 生命周期 ──────────────────────────────────

    @property
    def orch(self) -> Any:
        """获取当前活跃 Orchestrator（懒创建）。"""
        if self._active_orch is None:
            from hagoku.manager.orchestrator import Orchestrator
            self._active_orch = Orchestrator(self.config)
        return self._active_orch

    @property
    def active_project(self) -> str | None:
        return self._active_project

    def is_busy(self) -> bool:
        """当前项目是否有活跃的分析处理。"""
        if self._active_orch is None:
            return False
        return self._active_orch._processing

    def switch_project(self, project_name: str) -> dict | None:
        """切换到目标项目，返回状态快照。失败返回 None。"""
        from hagoku.manager.orchestrator import Orchestrator

        # 保存当前项目 + 取消飞行中的 respond
        if self._active_orch is not None:
            try:
                self._active_orch.request_cancel_respond()
                self._active_orch.save_state()
            except Exception:
                logger.warning("save_state 失败（切换项目时）", exc_info=True)

        self._active_orch = None
        self._active_project = None

        # 加载目标项目
        proj_dir = self.config.output.project_dir / project_name
        if not proj_dir.exists():
            return None

        orch = self._load_project(project_name)
        if orch is None:
            orch = Orchestrator(self.config)
            orch._project_name = project_name

        self._active_orch = orch
        self._active_project = project_name

        return self.build_snapshot()

    def _load_project(self, project_name: str) -> Any | None:
        """从磁盘恢复项目 orchestrator。"""
        from hagoku.manager.orchestrator import Orchestrator

        proj_dir = self.config.output.project_dir / project_name
        proj_file = proj_dir / "project.json"
        if not proj_file.exists():
            return None

        import json as _json
        try:
            meta = _json.loads(proj_file.read_text(encoding="utf-8"))
        except Exception:
            return None

        run_id = meta.get("current_run_id", "")
        # 解析 run 目录
        run_dir = str(proj_dir / "runs" / run_id) if run_id else ""
        if not run_id or not Path(run_dir).exists():
            runs_dir = proj_dir / "runs"
            if runs_dir.exists():
                for rdir in sorted(runs_dir.iterdir(), reverse=True):
                    if (rdir / "orch_state.json").exists():
                        run_dir = str(rdir)
                        break
            if not Path(run_dir).exists():
                return None

        try:
            return Orchestrator.restore_session(self.config, run_dir)
        except Exception:
            logger.warning("恢复项目 %s 失败", project_name, exc_info=True)
            return None

    # ── 状态快照 ───────────────────────────────────────────────

    def build_snapshot(self) -> dict[str, Any] | None:
        """从当前 Orchestrator 构建前端状态快照。

        纯读操作，用于 WebSocket 重连/项目切换时恢复 UI。
        不生成用户可见内容——所有展示数据由 LLM 流式输出提供。
        """
        orch = self._active_orch
        if orch is None:
            return None

        try:
            ctx = getattr(orch, '_context', None) or {}
            session = ctx.get("_session")
            if session:
                with session._lock:
                    raw_msgs = list(session.messages)
            else:
                raw_msgs = []

            # 将 tool 消息转换为 toolExchange 卡片，前端直接用
            rendered: list[dict[str, Any]] = []
            tool_batch: list[dict[str, Any]] = []
            pending_asst: dict[str, Any] | None = None
            for m in raw_msgs:
                role = m.get("role", "")
                if role == "workflow":
                    if tool_batch:
                        rendered.append({"role": "agent", "text": "",
                            "toolExchange": {"stage": "工具", "tool_calls": tool_batch}})
                        tool_batch = []
                    wtype = m.get("type", "")
                    if wtype == "field_review":
                        rendered.append({"role": "workflow", "text": "", "fieldReview": m.get("field_review", m)})
                    elif wtype == "cleaning_review":
                        rendered.append({"role": "workflow", "text": "", "cleaningReview": m.get("cleaning_review", m)})
                    elif wtype == "ask_user":
                        rendered.append({"role": "workflow", "text": "", "askUser": {"question": m.get("question", ""), "expected_format": m.get("expected_format", ""), "options": m.get("options")}})
                    continue
                if role == "tool":
                    tc_id = m.get("tool_call_id", "")
                    tc_name = ""
                    if pending_asst and pending_asst.get("tool_calls"):
                        for tc in pending_asst["tool_calls"]:
                            if tc.get("id") == tc_id:
                                tc_name = tc.get("function", {}).get("name", "")
                                break
                    tool_batch.append({
                        "id": tc_id, "name": tc_name,
                        "arguments_summary": "", "result_summary": str(m.get("content", ""))[:200],
                        "error": None, "duration_ms": 0,
                    })
                else:
                    if tool_batch:
                        rendered.append({
                            "role": "agent", "text": "",
                            "toolExchange": {"stage": "工具", "tool_calls": tool_batch},
                        })
                        tool_batch = []
                    if role == "assistant":
                        pending_asst = m
                    rendered.append({
                        "role": role,
                        "content": m.get("content", ""),
                        "tool_calls": m.get("tool_calls"),
                        "timestamp": m.get("timestamp", ""),
                    })
            if tool_batch:
                rendered.append({
                    "role": "agent", "text": "",
                    "toolExchange": {"stage": "工具", "tool_calls": tool_batch},
                })

            snap: dict[str, Any] = {
                "project_name": getattr(orch, '_project_name', '') or "",
                "query": ctx.get('query') or "",
                "data_path": ctx.get('data_path') or "",
                "report_url": ctx.get("_report_html_path"),
                "messages": rendered,
            }
            return snap
        except Exception:
            return None

    # ── 会话恢复 ───────────────────────────────────────────────

    def try_restore_session(self) -> bool:
        """从磁盘恢复当前项目的未完成 session。返回 True 表示已恢复。"""
        import os
        if os.environ.get("HAGOKU_SKIP_AUTO_RESTORE", "0") != "0":
            return False

        # 只恢复活跃项目，不跨项目扫描
        if not self._active_project:
            return False

        try:
            from hagoku.manager.orchestrator import Orchestrator

            proj_dir = Path(self.config.output.project_dir) / self._active_project
            runs_dir = proj_dir / "runs"
            if not runs_dir.exists():
                return False

            # 找最新 run
            candidates: list[tuple[float, str]] = []  # (mtime, run_dir_path)
            for run_dir in runs_dir.iterdir():
                state_file = run_dir / "orch_state.json"
                if not state_file.exists():
                    continue
                candidates.append((run_dir.stat().st_mtime, str(run_dir)))

            if not candidates:
                return False

            candidates.sort(reverse=True)
            for _, run_dir_path in candidates:
                orch = Orchestrator.restore_session(self.config, run_dir_path)
                if orch is not None:
                    self._active_orch = orch
                    return True

            return False
        except Exception:
            logger.warning("try_restore_session 失败", exc_info=True)
            return False
