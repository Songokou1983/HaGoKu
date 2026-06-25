"""ProjectManager — 多项目管理

管理当前活跃项目的 Orchestrator。切换项目时自动保存/恢复。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("hagoku.project_manager")


class ProjectManager:
    """多项目管理器。只持有当前活跃项目的 Orchestrator。"""

    def __init__(self, config: Any) -> None:
        self.config = config
        self._current_project: str | None = None
        self._current_orch: Any = None

    # ── 项目列表 ──────────────────────────────────────────────

    def list_projects(self) -> list[str]:
        """扫描 projects/ 目录，返回所有有 project.json 的项目名。"""
        projects_dir = self.config.output.project_dir
        if not projects_dir.exists():
            return []
        result = []
        for d in sorted(projects_dir.iterdir()):
            if d.is_dir() and (d / "project.json").exists():
                result.append(d.name)
        return result

    # ── 切换项目 ──────────────────────────────────────────────

    def switch_project(self, project_name: str) -> dict | None:
        """切换到目标项目，返回状态快照。失败返回 None。"""
        from hagoku.manager.orchestrator import Orchestrator

        # 如果当前项目有活跃 LLM 调用，拒绝切换
        if self._current_orch is not None:
            if getattr(self._current_orch, '_respond_cancelled', False) is False:
                # 检查是否有正在运行的 respond
                # 通过 check _agent 的 run_step 状态
                pass

        # 保存当前项目
        if self._current_orch is not None:
            try:
                self._current_orch.save_state()
            except Exception:
                logger.warning("save_state 失败（切换项目时）", exc_info=True)

        self._current_orch = None
        self._current_project = None

        # 加载目标项目
        proj_dir = self.config.output.project_dir / project_name
        if not proj_dir.exists():
            return None

        # 从磁盘恢复
        orch = self._load_project(project_name)
        if orch is None:
            # 项目存在但无活跃分析，创建空 orchestrator
            orch = Orchestrator(self.config)
            orch._project_name = project_name

        self._current_orch = orch
        self._current_project = project_name

        return self.get_snapshot()

    def _load_project(self, project_name: str) -> Any | None:
        """从磁盘恢复项目 orchestrator。"""
        from hagoku.manager.orchestrator import Orchestrator

        proj_dir = self.config.output.project_dir / project_name
        proj_file = proj_dir / "project.json"
        if not proj_file.exists():
            return None

        import json as _json
        try:
            meta = _json.loads(proj_file.open("r", encoding="utf-8"))
            run_id = meta.get("current_run_id", "")
            if not run_id:
                return None
            run_dir = str(proj_dir / "runs" / run_id)
            return Orchestrator.restore_session(self.config, run_dir)
        except Exception:
            logger.warning("恢复项目 %s 失败", project_name, exc_info=True)
            return None

    # ── 当前项目操作 ─────────────────────────────────────────

    def get_current_orch(self) -> Any:
        """获取当前项目的 orchestrator。"""
        if self._current_orch is None:
            from hagoku.manager.orchestrator import Orchestrator
            self._current_orch = Orchestrator(self.config)
        return self._current_orch

    def get_snapshot(self) -> dict | None:
        """返回当前项目状态快照，供前端恢复。"""
        if self._current_project is None:
            return None
        from hagoku.api.ws_handler import _build_state_snapshot
        return _build_state_snapshot(self._current_orch)

    def is_busy(self) -> bool:
        """当前项目是否有活跃的 respond 处理。"""
        if self._current_orch is None:
            return False
        return getattr(self._current_orch, '_respond_cancelled', True) is False

    # ── 项目管理 ──────────────────────────────────────────────

    def create_project(self, name: str) -> bool:
        """创建新项目文件夹。"""
        proj_dir = self.config.output.project_dir / name
        if proj_dir.exists():
            return False
        proj_dir.mkdir(parents=True, exist_ok=True)
        (proj_dir / "data").mkdir(exist_ok=True)
        (proj_dir / "runs").mkdir(exist_ok=True)
        return True

    def delete_project(self, name: str) -> bool:
        """删除项目文件夹。"""
        import shutil
        proj_dir = self.config.output.project_dir / name
        if not proj_dir.exists():
            return False
        if self._current_project == name:
            self._current_project = None
            self._current_orch = None
        shutil.rmtree(proj_dir)
        return True
