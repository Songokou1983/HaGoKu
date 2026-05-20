"""HaGoKu Studio SQLite 元数据库"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

# SQL 字段白名单，防止动态 SQL 注入
_PROJECT_ALLOWED_FIELDS = frozenset({"description", "data_path", "schema_path"})
_RUN_ALLOWED_FIELDS = frozenset({
    "query", "plan_json", "status", "completed_at",
    "duration_ms", "token_count", "manager_mode", "output_path"
})
_PROJECT_STATE_ALLOWED_FIELDS = frozenset({
    "goal", "data_path", "data_hash", "stage", "context_json",
    "cleaned_path", "cleaning_json", "results_json", "report_path", "next_action", "updated_at",
    "raw_path"
})


# ── SQL 建表语句 ──────────────────────────────────────────────

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS projects (
    id          TEXT PRIMARY KEY,
    created_at  DATETIME,
    description TEXT,
    data_path   TEXT,
    schema_path TEXT
);

CREATE TABLE IF NOT EXISTS data_sources (
    id          TEXT PRIMARY KEY,
    project_id  TEXT REFERENCES projects(id),
    name        TEXT,
    type        TEXT,
    connection  TEXT,
    schema_json TEXT,
    last_loaded DATETIME,
    row_count   INTEGER,
    quality_score FLOAT
);

CREATE TABLE IF NOT EXISTS runs (
    id          TEXT PRIMARY KEY,
    project_id  TEXT REFERENCES projects(id),
    query       TEXT,
    plan_json   TEXT,
    status      TEXT,
    started_at  DATETIME,
    completed_at DATETIME,
    duration_ms INTEGER,
    token_count INTEGER,
    manager_mode TEXT,
    output_path TEXT
);

CREATE TABLE IF NOT EXISTS findings (
    id          TEXT PRIMARY KEY,
    run_id      TEXT REFERENCES runs(id),
    analysis_type TEXT,
    question    TEXT,
    conclusion_plain TEXT,
    conclusion_statistical TEXT,
    p_value     FLOAT,
    effect_size FLOAT,
    effect_type TEXT,
    confidence_interval TEXT,
    significance TEXT,
    created_at  DATETIME
);

CREATE TABLE IF NOT EXISTS artifacts (
    id          TEXT PRIMARY KEY,
    run_id      TEXT REFERENCES runs(id),
    agent       TEXT,
    type        TEXT,
    file_path   TEXT,
    lineage     TEXT,
    metadata    TEXT,
    created_at  DATETIME
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_runs_project ON runs(project_id);
CREATE INDEX IF NOT EXISTS idx_findings_run ON findings(run_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_run ON artifacts(run_id);
CREATE INDEX IF NOT EXISTS idx_data_sources_project ON data_sources(project_id);
CREATE INDEX IF NOT EXISTS idx_findings_significance ON findings(significance);
CREATE INDEX IF NOT EXISTS idx_findings_analysis_type ON findings(analysis_type);

-- 记忆系统：跨运行学习和偏好持久化
CREATE TABLE IF NOT EXISTS memory (
    id          TEXT PRIMARY KEY,
    project_id  TEXT,                    -- NULL = 全局记忆
    category    TEXT NOT NULL,           -- column_semantic / cleaning_pref / analysis_pattern / target_variable / user_note
    key         TEXT NOT NULL,           -- 列名/模式名等
    value       TEXT NOT NULL,           -- JSON 值
    source      TEXT DEFAULT 'user',     -- user / auto / learned
    confidence  REAL DEFAULT 1.0,
    created_at  DATETIME,
    updated_at  DATETIME
);

CREATE INDEX IF NOT EXISTS idx_memory_project ON memory(project_id);
CREATE INDEX IF NOT EXISTS idx_memory_category ON memory(category);
CREATE UNIQUE INDEX IF NOT EXISTS idx_memory_uniq ON memory(project_id, category, key);

-- 项目工作台状态（目的/数据/进度/结果/下一步）
CREATE TABLE IF NOT EXISTS project_state (
    project_id  TEXT PRIMARY KEY,
    goal        TEXT DEFAULT '',            -- 分析目的（用户的问题）
    data_path   TEXT DEFAULT '',            -- 数据在哪
    data_hash   TEXT DEFAULT '',            -- 数据指纹（检测数据是否变化）
    stage       TEXT DEFAULT 'created',     -- 当前阶段: created / profiled / cleaned / analyzed / reported
    context_json TEXT DEFAULT '',            -- Scout 产出的数据上下文（JSON）
    cleaned_path TEXT DEFAULT '',            -- 清洗后数据路径
    raw_path TEXT DEFAULT '',                -- 原始数据路径（供 Analyst 按分析类型选用）
    cleaning_json TEXT DEFAULT '',           -- 清洗报告（JSON）
    results_json TEXT DEFAULT '',            -- 分析结果摘要（JSON）
    report_path TEXT DEFAULT '',             -- 报告路径
    next_action TEXT DEFAULT '',             -- 下一步建议
    updated_at  DATETIME
);

CREATE INDEX IF NOT EXISTS idx_project_state_stage ON project_state(stage);
"""


class HaGoKuDB:
    """SQLite 元数据库，单例模式，全局一个连接"""

    _instance: HaGoKuDB | None = None

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False 允许从 worker 线程访问（由 _lock 保证线程安全）
        self.conn = sqlite3.connect(str(db_path), timeout=30, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._init_tables()
        self._lock = threading.RLock()  # 保护 conn 的线程锁

    @classmethod
    def get_instance(cls, db_path: Path | None = None) -> HaGoKuDB:
        """获取全局单例"""
        if cls._instance is None:
            if db_path is None:
                db_path = Path.home() / ".hagoku" / "hagoku.db"
            cls._instance = cls(db_path)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """重置单例（测试用）"""
        if cls._instance is not None:
            cls._instance.close()
            cls._instance = None

    def _init_tables(self) -> None:
        """建表"""
        self.conn.executescript(_SCHEMA_SQL)
        self.conn.commit()

    def close(self) -> None:
        """关闭连接"""
        self.conn.close()

    @contextmanager
    def transaction(self):
        """事务上下文管理器，自动 commit / rollback（线程安全）"""
        with self._lock:
            try:
                yield self.conn
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise

    # ── Projects ───────────────────────────────────────────

    def create_project(
        self,
        project_id: str,
        description: str = "",
        data_path: str = "",
        schema_path: str = "",
    ) -> dict[str, Any] | None:
        """创建项目"""
        now = datetime.now().isoformat()
        self.conn.execute(
            "INSERT OR IGNORE INTO projects (id, created_at, description, data_path, schema_path) "
            "VALUES (?, ?, ?, ?, ?)",
            (project_id, now, description, data_path, schema_path),
        )
        self.conn.commit()
        return self.get_project(project_id)

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        """获取项目"""
        row = self.conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_projects(self) -> list[dict[str, Any]]:
        """列出所有项目"""
        rows = self.conn.execute(
            "SELECT * FROM projects ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def update_project(self, project_id: str, **kwargs: Any) -> None:
        """更新项目字段（仅允许白名单内的字段）"""
        if not kwargs:
            return
        # 白名单验证，防止 SQL 注入
        filtered = {k: v for k, v in kwargs.items() if k in _PROJECT_ALLOWED_FIELDS}
        if not filtered:
            return
        sets = ", ".join(f"{k} = ?" for k in filtered)
        vals = list(filtered.values()) + [project_id]
        self.conn.execute(f"UPDATE projects SET {sets} WHERE id = ?", vals)
        self.conn.commit()

    # ── Data Sources ───────────────────────────────────────

    def add_data_source(
        self,
        source_id: str,
        project_id: str,
        name: str,
        source_type: str,
        connection: str = "",
        schema_json: dict | None = None,
        row_count: int = 0,
        quality_score: float = 0.0,
    ) -> dict[str, Any] | None:
        """注册数据源"""
        schema_str = json.dumps(schema_json, ensure_ascii=False) if schema_json else ""
        self.conn.execute(
            "INSERT OR REPLACE INTO data_sources "
            "(id, project_id, name, type, connection, schema_json, last_loaded, row_count, quality_score) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (source_id, project_id, name, source_type, connection,
             schema_str, datetime.now().isoformat(), row_count, quality_score),
        )
        self.conn.commit()
        return self.get_data_source(source_id)

    def get_data_source(self, source_id: str) -> dict[str, Any] | None:
        """获取数据源"""
        row = self.conn.execute(
            "SELECT * FROM data_sources WHERE id = ?", (source_id,)
        ).fetchone()
        if row is None:
            return None
        d = dict(row)
        if d.get("schema_json"):
            d["schema_json"] = json.loads(d["schema_json"])
        return d

    def list_data_sources(self, project_id: str) -> list[dict[str, Any]]:
        """列出项目的所有数据源"""
        rows = self.conn.execute(
            "SELECT * FROM data_sources WHERE project_id = ? ORDER BY name",
            (project_id,),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if d.get("schema_json"):
                d["schema_json"] = json.loads(d["schema_json"])
            result.append(d)
        return result

    # ── Runs ───────────────────────────────────────────────

    def create_run(
        self,
        run_id: str,
        project_id: str,
        query: str = "",
        plan: dict | None = None,
        manager_mode: str = "balanced",
    ) -> dict[str, Any] | None:
        """创建分析运行。

        ``manager_mode`` 为写入 runs 表的内部编排元数据（计划生成策略标签），
        **并非**已移除的「用户三档位 / HAGOKYU_MANAGER_MODE」产品开关。
        """
        plan_str = json.dumps(plan, ensure_ascii=False) if plan else ""
        now = datetime.now().isoformat()
        self.conn.execute(
            "INSERT INTO runs (id, project_id, query, plan_json, status, started_at, manager_mode) "
            "VALUES (?, ?, ?, ?, 'running', ?, ?)",
            (run_id, project_id, query, plan_str, now, manager_mode),
        )
        self.conn.commit()
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        """获取运行记录"""
        row = self.conn.execute(
            "SELECT * FROM runs WHERE id = ?", (run_id,)
        ).fetchone()
        if row is None:
            return None
        d = dict(row)
        if d.get("plan_json"):
            d["plan_json"] = json.loads(d["plan_json"])
        return d

    def update_run(self, run_id: str, **kwargs: Any) -> None:
        """更新运行字段（仅允许白名单内的字段）"""
        if not kwargs:
            return
        # 白名单验证，防止 SQL 注入
        filtered = {k: v for k, v in kwargs.items() if k in _RUN_ALLOWED_FIELDS}
        if not filtered:
            return
        # plan_json 需要序列化
        if "plan_json" in filtered and isinstance(filtered["plan_json"], dict):
            filtered["plan_json"] = json.dumps(filtered["plan_json"], ensure_ascii=False)
        sets = ", ".join(f"{k} = ?" for k in filtered)
        vals = list(filtered.values()) + [run_id]
        self.conn.execute(f"UPDATE runs SET {sets} WHERE id = ?", vals)
        self.conn.commit()

    def complete_run(self, run_id: str, duration_ms: int, token_count: int = 0, output_path: str = "") -> None:
        """标记运行完成"""
        now = datetime.now().isoformat()
        self.conn.execute(
            "UPDATE runs SET status = 'completed', completed_at = ?, "
            "duration_ms = ?, token_count = ?, output_path = ? WHERE id = ?",
            (now, duration_ms, token_count, output_path, run_id),
        )
        self.conn.commit()

    def fail_run(self, run_id: str, duration_ms: int = 0) -> None:
        """标记运行失败"""
        now = datetime.now().isoformat()
        self.conn.execute(
            "UPDATE runs SET status = 'failed', completed_at = ?, duration_ms = ? WHERE id = ?",
            (now, duration_ms, run_id),
        )
        self.conn.commit()

    def get_run_history(self, project_id: str) -> list[dict[str, Any]]:
        """获取项目运行历史"""
        rows = self.conn.execute(
            "SELECT * FROM runs WHERE project_id = ? ORDER BY started_at DESC",
            (project_id,),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if d.get("plan_json"):
                d["plan_json"] = json.loads(d["plan_json"])
            result.append(d)
        return result

    # ── Findings ───────────────────────────────────────────

    def save_finding(self, finding: dict[str, Any]) -> dict[str, Any]:
        """保存分析发现（单条）"""
        now = datetime.now().isoformat()
        self.conn.execute(
            "INSERT INTO findings "
            "(id, run_id, analysis_type, question, conclusion_plain, conclusion_statistical, "
            "p_value, effect_size, effect_type, confidence_interval, significance, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                finding["id"],
                finding["run_id"],
                finding.get("analysis_type", ""),
                finding.get("question", ""),
                finding.get("conclusion_plain", ""),
                finding.get("conclusion_statistical", ""),
                finding.get("p_value"),
                finding.get("effect_size"),
                finding.get("effect_type", ""),
                finding.get("confidence_interval", ""),
                finding.get("significance", ""),
                now,
            ),
        )
        self.conn.commit()
        return finding

    def save_findings(self, findings: list[dict[str, Any]]) -> None:
        """批量保存发现（事务保证原子性）"""
        now = datetime.now().isoformat()
        with self.transaction():
            for f in findings:
                self.conn.execute(
                    "INSERT INTO findings "
                    "(id, run_id, analysis_type, question, conclusion_plain, conclusion_statistical, "
                    "p_value, effect_size, effect_type, confidence_interval, significance, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        f["id"], f["run_id"],
                        f.get("analysis_type", ""), f.get("question", ""),
                        f.get("conclusion_plain", ""), f.get("conclusion_statistical", ""),
                        f.get("p_value"), f.get("effect_size"),
                        f.get("effect_type", ""), f.get("confidence_interval", ""),
                        f.get("significance", ""), now,
                    ),
                )

    def get_findings(self, run_id: str) -> list[dict[str, Any]]:
        """获取某次运行的所有发现"""
        rows = self.conn.execute(
            "SELECT * FROM findings WHERE run_id = ? ORDER BY created_at",
            (run_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def query_findings(
        self,
        project_id: str | None = None,
        analysis_type: str | None = None,
        significance: str | None = None,
        min_effect_size: float | None = None,
        max_p_value: float | None = None,
    ) -> list[dict[str, Any]]:
        """按条件查询发现"""
        conditions = []
        params: list[Any] = []

        if project_id:
            conditions.append(
                "run_id IN (SELECT id FROM runs WHERE project_id = ?)"
            )
            params.append(project_id)
        if analysis_type:
            conditions.append("analysis_type = ?")
            params.append(analysis_type)
        if significance:
            conditions.append("significance = ?")
            params.append(significance)
        if min_effect_size is not None:
            conditions.append("effect_size >= ?")
            params.append(min_effect_size)
        if max_p_value is not None:
            conditions.append("p_value <= ?")
            params.append(max_p_value)

        where = " AND ".join(conditions) if conditions else "1=1"
        rows = self.conn.execute(
            f"SELECT * FROM findings WHERE {where} ORDER BY created_at DESC",
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Artifacts ──────────────────────────────────────────

    def save_artifact(self, artifact: dict[str, Any]) -> dict[str, Any]:
        """保存数据制品记录"""
        now = datetime.now().isoformat()
        lineage_str = json.dumps(artifact.get("lineage"), ensure_ascii=False) if artifact.get("lineage") else ""
        metadata_str = json.dumps(artifact.get("metadata"), ensure_ascii=False) if artifact.get("metadata") else ""
        self.conn.execute(
            "INSERT INTO artifacts (id, run_id, agent, type, file_path, lineage, metadata, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                artifact["id"],
                artifact["run_id"],
                artifact.get("agent", ""),
                artifact.get("type", ""),
                artifact.get("file_path", ""),
                lineage_str,
                metadata_str,
                now,
            ),
        )
        self.conn.commit()
        return artifact

    def get_artifacts(self, run_id: str) -> list[dict[str, Any]]:
        """获取某次运行的所有制品"""
        rows = self.conn.execute(
            "SELECT * FROM artifacts WHERE run_id = ? ORDER BY created_at",
            (run_id,),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if d.get("lineage"):
                d["lineage"] = json.loads(d["lineage"])
            if d.get("metadata"):
                d["metadata"] = json.loads(d["metadata"])
            result.append(d)
        return result

    def get_artifacts_by_agent(self, run_id: str, agent: str) -> list[dict[str, Any]]:
        """获取某次运行中某 agent 的制品"""
        rows = self.conn.execute(
            "SELECT * FROM artifacts WHERE run_id = ? AND agent = ? ORDER BY created_at",
            (run_id, agent),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if d.get("lineage"):
                d["lineage"] = json.loads(d["lineage"])
            if d.get("metadata"):
                d["metadata"] = json.loads(d["metadata"])
            result.append(d)
        return result

    # ── Diff ───────────────────────────────────────────────

    def diff_runs(self, run_id_1: str, run_id_2: str) -> dict[str, Any]:
        """对比两次运行的发现"""
        findings_1 = self.get_findings(run_id_1)
        findings_2 = self.get_findings(run_id_2)

        # 按 analysis_type + question 匹配
        map_1 = {(f["analysis_type"], f["question"]): f for f in findings_1}
        map_2 = {(f["analysis_type"], f["question"]): f for f in findings_2}

        common_keys = set(map_1.keys()) & set(map_2.keys())
        only_in_1 = set(map_1.keys()) - set(map_2.keys())
        only_in_2 = set(map_2.keys()) - set(map_1.keys())

        changed = []
        for key in common_keys:
            f1, f2 = map_1[key], map_2[key]
            if f1["conclusion_statistical"] != f2["conclusion_statistical"]:
                changed.append({
                    "analysis_type": key[0],
                    "question": key[1],
                    "run_1": {
                        "conclusion": f1["conclusion_statistical"],
                        "p_value": f1["p_value"],
                        "effect_size": f1["effect_size"],
                    },
                    "run_2": {
                        "conclusion": f2["conclusion_statistical"],
                        "p_value": f2["p_value"],
                        "effect_size": f2["effect_size"],
                    },
                })

        return {
            "run_1": run_id_1,
            "run_2": run_id_2,
            "only_in_run_1": [{"analysis_type": k[0], "question": k[1]} for k in only_in_1],
            "only_in_run_2": [{"analysis_type": k[0], "question": k[1]} for k in only_in_2],
            "changed": changed,
        }

    # ── Project State (工作台状态) ────────────────────────────

    def get_project_state(self, project_id: str) -> dict[str, Any] | None:
        """获取项目工作台状态"""
        row = self.conn.execute(
            "SELECT * FROM project_state WHERE project_id = ?", (project_id,)
        ).fetchone()
        if row is None:
            return None
        d = dict(row)
        for key in ("context_json", "cleaning_json", "results_json"):
            if d.get(key):
                try:
                    d[key] = json.loads(d[key])
                except (json.JSONDecodeError, TypeError):
                    pass
        return d

    def init_project_state(
        self, project_id: str, goal: str = "", data_path: str = "", data_hash: str = "",
    ) -> dict[str, Any]:
        """初始化项目状态"""
        now = datetime.now().isoformat()
        self.conn.execute(
            "INSERT OR IGNORE INTO project_state "
            "(project_id, goal, data_path, data_hash, stage, next_action, updated_at) "
            "VALUES (?, ?, ?, ?, 'created', 'run hagoku profile to start', ?)",
            (project_id, goal, data_path, data_hash, now),
        )
        self.conn.commit()
        return self.get_project_state(project_id) or {}

    def update_project_state(self, project_id: str, **kwargs: Any) -> None:
        """
        更新项目工作台状态（仅允许白名单内的字段）

        允许字段: goal, data_path, data_hash, stage, context_json,
                  cleaned_path, cleaning_json, results_json, report_path, next_action
        """
        if not kwargs:
            return
        # 白名单验证，防止 SQL 注入
        filtered = {k: v for k, v in kwargs.items() if k in _PROJECT_STATE_ALLOWED_FIELDS}
        if not filtered:
            return
        # JSON 字段自动序列化
        for key in ("context_json", "cleaning_json", "results_json"):
            if key in filtered and not isinstance(filtered[key], str):
                filtered[key] = json.dumps(filtered[key], ensure_ascii=False)
        filtered["updated_at"] = datetime.now().isoformat()

        # 使用 INSERT OR REPLACE 处理竞态，避免 TOCTOU 问题
        # 先尝试 INSERT，如果已存在则 UPDATE
        sets = ", ".join(f"{k} = ?" for k in filtered)
        vals = list(filtered.values()) + [project_id]

        with self.transaction():
            # 尝试直接 UPDATE
            self.conn.execute(
                f"UPDATE project_state SET {sets} WHERE project_id = ?",
                vals
            )
            # 如果没有更新任何行，则插入新行
            if self.conn.execute("SELECT changes()").fetchone()[0] == 0:
                self.init_project_state(project_id)
                self.conn.execute(
                    f"UPDATE project_state SET {sets} WHERE project_id = ?",
                    vals
                )

    # ── Memory 已迁移到 storage/memory.py (MemoryManager) ───────────
    # memory 表的 SQL 建表语句保留在此（SqliteMemoryBackend 直接操作）
    # 高层方法 save_memory / get_project_memory / learn_target_variable / learn_cleaning_preference 已删除

    def list_projects_by_stage(self, stage: str | None = None) -> list[dict[str, Any]]:
        """按阶段列出项目（看哪些做到哪了）"""
        if stage:
            rows = self.conn.execute(
                "SELECT * FROM project_state WHERE stage = ? ORDER BY updated_at DESC",
                (stage,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM project_state ORDER BY updated_at DESC"
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            for key in ("context_json", "cleaning_json", "results_json"):
                if d.get(key):
                    try:
                        d[key] = json.loads(d[key])
                    except (json.JSONDecodeError, TypeError):
                        pass
            result.append(d)
        return result
