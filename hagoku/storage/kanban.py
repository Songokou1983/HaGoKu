"""
HaGoKu Studio 项目看板 — SQLite 持久化

参考 hermes-kanban-mcp (Shin-R2un) 的 SQLite schema 设计
每个项目独立 kanban.db，不做全局管理
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# 有效状态
VALID_STATUSES = frozenset({"triage", "todo", "ready", "running", "blocked", "done", "archived"})

# 状态流转规则
STATUS_TRANSITIONS = {
    "triage": {"todo", "ready"},
    "todo": {"ready", "archived"},
    "ready": {"running", "blocked", "archived"},
    "running": {"done", "blocked", "archived"},
    "blocked": {"ready", "running", "archived"},
    "done": {"archived"},
    "archived": set(),
}


class KanbanDB:
    """
    项目看板数据库

    每个项目一个 kanban.db，在项目文件夹内。
    线程安全（单例 + RLock）。
    """

    _instances: dict[str, "KanbanDB"] = {}

    def __init__(self, db_path: str | Path) -> None:
        self._path = Path(db_path)
        self._conn = sqlite3.connect(
            str(db_path),
            timeout=30,
            check_same_thread=False,
        )
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._ensure_schema()

    @classmethod
    def get_instance(cls, project_path: str | Path) -> "KanbanDB":
        """单例：每个项目路径对应一个实例"""
        key = str(Path(project_path).resolve())
        if key not in cls._instances:
            db_path = Path(project_path) / "kanban.db"
            cls._instances[key] = cls(db_path)
        return cls._instances[key]

    @classmethod
    def clear_instance(cls, project_path: str | Path) -> None:
        """清除实例（测试用）"""
        key = str(Path(project_path).resolve())
        if key in cls._instances:
            inst = cls._instances.pop(key)
            inst._conn.close()

    @contextmanager
    def transaction(self):
        """线程安全的数据库事务"""
        with self._lock:
            try:
                yield self._conn
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def _ensure_schema(self) -> None:
        """确保 schema 存在"""
        with self.transaction() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS kanban_tasks (
                    id              TEXT PRIMARY KEY,
                    agent           TEXT NOT NULL,
                    title           TEXT NOT NULL,
                    description     TEXT,
                    status          TEXT DEFAULT 'triage',
                    priority        INTEGER DEFAULT 0,
                    parent_id       TEXT,
                    workspace_path  TEXT,
                    created_at      TEXT NOT NULL,
                    updated_at      TEXT NOT NULL,
                    completed_at    TEXT,
                    claim_lock      TEXT,
                    claim_expires   INTEGER,
                    result          TEXT,
                    FOREIGN KEY (parent_id) REFERENCES kanban_tasks(id)
                );

                CREATE TABLE IF NOT EXISTS task_events (
                    id          TEXT PRIMARY KEY,
                    task_id     TEXT NOT NULL,
                    event_type  TEXT NOT NULL,
                    actor       TEXT,
                    body        TEXT,
                    created_at  TEXT NOT NULL,
                    FOREIGN KEY (task_id) REFERENCES kanban_tasks(id)
                );

                CREATE TABLE IF NOT EXISTS task_comments (
                    id          TEXT PRIMARY KEY,
                    task_id     TEXT NOT NULL,
                    author      TEXT NOT NULL,
                    body        TEXT,
                    created_at  TEXT NOT NULL,
                    FOREIGN KEY (task_id) REFERENCES kanban_tasks(id)
                );

                CREATE INDEX IF NOT EXISTS idx_tasks_status ON kanban_tasks(status);
                CREATE INDEX IF NOT EXISTS idx_tasks_agent ON kanban_tasks(agent);
                CREATE INDEX IF NOT EXISTS idx_tasks_parent ON kanban_tasks(parent_id);
                CREATE INDEX IF NOT EXISTS idx_events_task ON task_events(task_id);
                CREATE INDEX IF NOT EXISTS idx_comments_task ON task_comments(task_id);
            """)

    # ── 任务 CRUD ──────────────────────────────────────────

    def create_task(
        self,
        agent: str,
        title: str,
        description: str = "",
        parent_id: str | None = None,
        priority: int = 0,
    ) -> str:
        """创建任务，返回 task_id"""
        task_id = uuid.uuid4().hex[:12]
        now = datetime.now().isoformat()

        with self.transaction() as conn:
            conn.execute(
                """INSERT INTO kanban_tasks
                   (id, agent, title, description, parent_id, priority, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (task_id, agent, title, description, parent_id, priority, "triage", now, now),
            )
            self._log_event(conn, task_id, "created", "system", title)

        return task_id

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        """获取任务详情"""
        row = self._conn.execute(
            "SELECT * FROM kanban_tasks WHERE id = ?", (task_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_tasks(
        self,
        agent: str | None = None,
        status: str | None = None,
        parent_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """按条件列出任务"""
        sql = "SELECT * FROM kanban_tasks WHERE 1=1"
        params: list[Any] = []

        if agent:
            sql += " AND agent = ?"
            params.append(agent)
        if status:
            sql += " AND status = ?"
            params.append(status)
        if parent_id is not None:
            sql += " AND parent_id = ?"
            params.append(parent_id)

        sql += " ORDER BY created_at DESC"

        rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def update_status(self, task_id: str, new_status: str, actor: str = "system") -> bool:
        """更新任务状态，返回是否成功"""
        if new_status not in VALID_STATUSES:
            return False

        task = self.get_task(task_id)
        if not task:
            return False

        old_status = task["status"]
        if new_status not in STATUS_TRANSITIONS.get(old_status, set()):
            return False

        now = datetime.now().isoformat()

        with self.transaction() as conn:
            conn.execute(
                "UPDATE kanban_tasks SET status = ?, updated_at = ? WHERE id = ?",
                (new_status, now, task_id),
            )
            self._log_event(conn, task_id, f"status:{old_status}→{new_status}", actor)

            # 完成时间
            if new_status == "done":
                conn.execute(
                    "UPDATE kanban_tasks SET completed_at = ? WHERE id = ?",
                    (now, task_id),
                )

        return True

    # ── Claim 锁 ───────────────────────────────────────────

    def claim_task(self, task_id: str, lock_holder: str, ttl_minutes: int = 15) -> bool:
        """
        原子操作：ready → running
        返回是否成功（失败说明已被其他任务claim）
        """
        task = self.get_task(task_id)
        if not task or task["status"] != "ready":
            return False

        # 检查是否已有有效锁
        if task.get("claim_lock") and task.get("claim_expires"):
            expires = datetime.fromtimestamp(task["claim_expires"])
            if datetime.now() < expires and task["claim_lock"] != lock_holder:
                return False

        now = datetime.now().isoformat()
        expires_ts = int((datetime.now() + timedelta(minutes=ttl_minutes)).timestamp())

        with self.transaction() as conn:
            conn.execute(
                """UPDATE kanban_tasks
                   SET status = 'running', claim_lock = ?, claim_expires = ?, updated_at = ?
                   WHERE id = ? AND status = 'ready'""",
                (lock_holder, expires_ts, now, task_id),
            )
            self._log_event(conn, task_id, "claimed", lock_holder)

        # 检查是否真的变成了 running
        updated = self.get_task(task_id)
        return updated is not None and updated["status"] == "running"

    def heartbeat(self, task_id: str, lock_holder: str, ttl_minutes: int = 15) -> bool:
        """续期 claim 锁"""
        task = self.get_task(task_id)
        if not task or task.get("claim_lock") != lock_holder:
            return False

        expires_ts = int((datetime.now() + timedelta(minutes=ttl_minutes)).timestamp())
        now = datetime.now().isoformat()

        with self.transaction() as conn:
            conn.execute(
                "UPDATE kanban_tasks SET claim_expires = ?, updated_at = ? WHERE id = ?",
                (expires_ts, now, task_id),
            )

        return True

    def release_claim(self, task_id: str, lock_holder: str) -> bool:
        """释放 claim 锁（任务放弃）"""
        task = self.get_task(task_id)
        if not task or task.get("claim_lock") != lock_holder:
            return False

        now = datetime.now().isoformat()

        with self.transaction() as conn:
            conn.execute(
                """UPDATE kanban_tasks
                   SET status = 'ready', claim_lock = NULL, claim_expires = NULL, updated_at = ?
                   WHERE id = ?""",
                (now, task_id),
            )
            self._log_event(conn, task_id, "released", lock_holder)

        return True

    # ── 状态流转 ───────────────────────────────────────────

    def block_task(self, task_id: str, reason: str, actor: str = "system") -> bool:
        """running/ready → blocked"""
        task = self.get_task(task_id)
        if not task or task["status"] not in {"running", "ready"}:
            return False

        with self.transaction() as conn:
            conn.execute(
                "UPDATE kanban_tasks SET status = 'blocked', updated_at = ? WHERE id = ?",
                (datetime.now().isoformat(), task_id),
            )
            self._log_event(conn, task_id, "blocked", actor, reason)

        return True

    def unblock_task(self, task_id: str, actor: str = "system") -> bool:
        """blocked → ready"""
        task = self.get_task(task_id)
        if not task or task["status"] != "blocked":
            return False

        with self.transaction() as conn:
            conn.execute(
                "UPDATE kanban_tasks SET status = 'ready', updated_at = ? WHERE id = ?",
                (datetime.now().isoformat(), task_id),
            )
            self._log_event(conn, task_id, "unblocked", actor)

        return True

    def complete_task(self, task_id: str, result: str = "", actor: str = "system") -> bool:
        """running → done"""
        task = self.get_task(task_id)
        if not task or task["status"] != "running":
            return False

        now = datetime.now().isoformat()

        with self.transaction() as conn:
            conn.execute(
                """UPDATE kanban_tasks
                   SET status = 'done', completed_at = ?, result = ?, claim_lock = NULL, claim_expires = NULL, updated_at = ?
                   WHERE id = ?""",
                (now, result, now, task_id),
            )
            self._log_event(conn, task_id, "completed", actor, result)

        # 父任务全部 done → 晋升子任务到 ready
        self._recompute_ready(task_id)

        return True

    def complete_agent_task_atomic(self, agent: str, lock_holder: str, result: str = "") -> bool:
        """
        原子操作：获取 agent 当前 active 任务 → claim（若需要）→ complete。
        解决 _on_agent_completed 中 claim_task → complete_task 之间崩溃导致
        任务卡在 running 状态的一致性风险。

        处理三种场景：
        1. ready → claim → done（从 ready 直接完成）
        2. running → done（已 claim，直接完成）
        3. blocked → unblock → claim → done（先解阻塞再完成）
        """
        now = datetime.now().isoformat()
        tasks = self.list_tasks(agent=agent, status="running")
        if not tasks:
            tasks = self.list_tasks(agent=agent, status="ready")
        if not tasks:
            tasks = self.list_tasks(agent=agent, status="blocked")

        if not tasks:
            return False

        task = tasks[0]
        task_id = task["id"]
        current_status = task["status"]

        with self.transaction() as conn:
            if current_status == "blocked":
                conn.execute(
                    "UPDATE kanban_tasks SET status = 'ready', updated_at = ? WHERE id = ?",
                    (now, task_id),
                )
                self._log_event(conn, task_id, "unblocked", lock_holder)

            if current_status in ("ready", "blocked"):
                expires_ts = int((datetime.now() + timedelta(minutes=15)).timestamp())
                conn.execute(
                    """UPDATE kanban_tasks
                       SET status = 'running', claim_lock = ?, claim_expires = ?, updated_at = ?
                       WHERE id = ? AND status = 'ready'""",
                    (lock_holder, expires_ts, now, task_id),
                )
                self._log_event(conn, task_id, "claimed", lock_holder)

            conn.execute(
                """UPDATE kanban_tasks
                   SET status = 'done', completed_at = ?, result = ?,
                       claim_lock = NULL, claim_expires = NULL, updated_at = ?
                   WHERE id = ?""",
                (now, result, now, task_id),
            )
            self._log_event(conn, task_id, "completed", lock_holder, result)

        self._recompute_ready(task_id)
        return True

    def _recompute_ready(self, parent_id: str) -> None:
        """
        当父任务完成时，将其所有子任务从 triage → ready。
        HaGoKu Studio 流程：Scout 完成 → Cleaner 自动 ready。
        """
        children = self.list_tasks(parent_id=parent_id)
        if not children:
            return

        now = datetime.now().isoformat()

        for child in children:
            # 子任务从 triage 或 todo 直接晋升到 ready（绕过状态机检查）
            if child["status"] in ("triage", "todo"):
                with self.transaction() as conn:
                    conn.execute(
                        "UPDATE kanban_tasks SET status = 'ready', updated_at = ? WHERE id = ?",
                        (now, child["id"]),
                    )
                    self._log_event(conn, child["id"], f"promoted:{child['status']}→ready", "system")

    # ── 事件与评论 ─────────────────────────────────────────

    def _log_event(
        self,
        conn: sqlite3.Connection,
        task_id: str,
        event_type: str,
        actor: str,
        body: str = "",
    ) -> None:
        event_id = uuid.uuid4().hex[:12]
        now = datetime.now().isoformat()
        conn.execute(
            "INSERT INTO task_events (id, task_id, event_type, actor, body, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (event_id, task_id, event_type, actor, body, now),
        )

    def add_comment(self, task_id: str, author: str, body: str) -> str:
        """添加评论，返回 comment_id"""
        comment_id = uuid.uuid4().hex[:12]
        now = datetime.now().isoformat()

        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO task_comments (id, task_id, author, body, created_at) VALUES (?, ?, ?, ?, ?)",
                (comment_id, task_id, author, body, now),
            )
            self._log_event(conn, task_id, "comment", author, body)

        return comment_id

    def get_events(self, task_id: str) -> list[dict[str, Any]]:
        """获取任务的所有事件"""
        rows = self._conn.execute(
            "SELECT * FROM task_events WHERE task_id = ? ORDER BY created_at ASC",
            (task_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_comments(self, task_id: str) -> list[dict[str, Any]]:
        """获取任务的所有评论"""
        rows = self._conn.execute(
            "SELECT * FROM task_comments WHERE task_id = ? ORDER BY created_at ASC",
            (task_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── 统计 ───────────────────────────────────────────────

    def get_stats(self) -> dict[str, int]:
        """获取看板统计"""
        stats = {}
        for status in VALID_STATUSES:
            count = self._conn.execute(
                "SELECT COUNT(*) FROM kanban_tasks WHERE status = ?", (status,)
            ).fetchone()[0]
            stats[status] = count
        stats["total"] = sum(stats.values())
        return stats

    def get_active_task(self, agent: str) -> dict[str, Any] | None:
        """获取当前 agent 的 running 或 blocked 任务"""
        row = self._conn.execute(
            """SELECT * FROM kanban_tasks
               WHERE agent = ? AND status IN ('running', 'blocked')
               ORDER BY updated_at DESC LIMIT 1""",
            (agent,),
        ).fetchone()
        return dict(row) if row else None

    def get_ready_task(self, agent: str) -> dict[str, Any] | None:
        """获取当前 agent 的 ready 任务（init_pipeline 后等待 claim）"""
        row = self._conn.execute(
            """SELECT * FROM kanban_tasks
               WHERE agent = ? AND status = 'ready'
               ORDER BY updated_at DESC LIMIT 1""",
            (agent,),
        ).fetchone()
        return dict(row) if row else None

    def get_any_task(self, agent: str) -> dict[str, Any] | None:
        """获取当前 agent 的任意活跃任务（ready/running/blocked，不含 done/archived）"""
        row = self._conn.execute(
            """SELECT * FROM kanban_tasks
               WHERE agent = ? AND status NOT IN ('done', 'archived')
               ORDER BY
                 CASE status
                   WHEN 'running' THEN 1
                   WHEN 'blocked' THEN 2
                   WHEN 'ready' THEN 3
                   WHEN 'triage' THEN 4
                   WHEN 'todo' THEN 5
                 END
               LIMIT 1""",
            (agent,),
        ).fetchone()
        return dict(row) if row else None
