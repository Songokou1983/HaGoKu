"""HaGoKu Studio 记忆系统 — 独立、灵活的跨运行学习模块

核心设计：
- MemoryManager 是唯一对外接口（Facade）
- 双后端：SQLite（程序化查询）+ YAML（人可读、git 友好）
- YAML 优先级高于 SQLite（用户真相）
- 写同时写两处，读按优先级合并
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from .database import HaGoKuDB
from .memory_backends import SqliteMemoryBackend, YamlMemoryBackend

# ── 数据模型 ──────────────────────────────────────────────────


class MemoryCategory(str, Enum):
    """记忆类别"""
    COLUMN_SEMANTIC = "column_semantic"
    TARGET_VARIABLE = "target_variable"
    CLEANING_PREF = "cleaning_pref"
    ANALYSIS_PATTERN = "analysis_pattern"
    USER_NOTE = "user_note"


class MemorySource(str, Enum):
    """记忆来源"""
    USER = "user"
    AUTO = "auto"
    LEARNED = "learned"


class ColumnSemanticDef(BaseModel):
    """列语义定义，对应 progress.yaml 的 columns 条目"""
    semantic: str = "unknown"
    ignore: bool = False
    ordinal: bool | None = None
    order: list[str] | None = None
    unit: str | None = None
    display_name: str | None = None
    description: str | None = None
    role: str | None = None
    confidence: float = 1.0
    source: str = "auto"


class CleaningPrefDef(BaseModel):
    """清洗偏好"""
    strategy: str = ""
    reason: str = ""


class AnalysisPatternDef(BaseModel):
    """分析模式"""
    analysis_type: str = ""
    question: str = ""
    significance: str = ""


class ProgressYaml(BaseModel):
    """progress.yaml 结构"""
    columns: dict[str, ColumnSemanticDef] = Field(default_factory=dict)
    target: str | None = None
    confounders: list[str] = Field(default_factory=list)
    time_column: str | None = None
    group_columns: list[str] = Field(default_factory=list)
    user_constraints: list[str] = Field(default_factory=list)


# ── MemoryManager ─────────────────────────────────────────────


class MemoryManager:
    """
    独立、灵活的记忆系统

    - 双后端：SQLite + YAML
    - 清洁 API，agents/CLI 无需知道存储细节
    - 可扩展新类别或新后端
    """

    def __init__(
        self,
        db: HaGoKuDB,
        progress_path: Path | None = None,
    ) -> None:
        self._sqlite = SqliteMemoryBackend(db)
        self._yaml = YamlMemoryBackend(progress_path) if progress_path else None
        self._db = db

        # 启动时：如果 YAML 比 SQLite 新，自动同步
        if self._yaml and self._yaml.exists():
            self._auto_sync_yaml()

    def _auto_sync_yaml(self) -> None:
        """YAML 文件比 SQLite 记忆新时，自动 import"""
        if not self._yaml:
            return
        yaml_mtime = self._yaml.mtime()
        if yaml_mtime is None:
            return
        # 比较 YAML 的 mtime 与 SQLite 中记录的时间
        # 获取 SQLite 中最新的 updated_at
        sqlite_entries = self._sqlite.load(None, category=None)
        if sqlite_entries:
            # 找到最新的 updated_at
            latest_sqlite_time = max(
                datetime.fromisoformat(e.get("updated_at", "1970-01-01"))
                for e in sqlite_entries
                if e.get("updated_at")
            )
            yaml_dt = datetime.fromtimestamp(yaml_mtime)
            if yaml_dt > latest_sqlite_time:
                # YAML 更新，从 YAML 导入到 SQLite
                self._import_yaml_to_sqlite()
        else:
            # SQLite 空，从 YAML 导入
            self._import_yaml_to_sqlite()

    # ── 通用读写 ────────────────────────────────────────────

    def save(
        self,
        project_id: str | None,
        category: str,
        key: str,
        value: Any,
        source: str = "auto",
        confidence: float = 1.0,
    ) -> None:
        """保存记忆（upsert），同时写 SQLite 和 YAML"""
        value_str = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value

        # 始终写 SQLite
        self._sqlite.save(project_id, category, key, value_str, source, confidence)

        # 如果有 YAML 后端，也写
        if self._yaml:
            self._yaml.save(project_id, category, key, value_str, source, confidence)

    def load(
        self,
        project_id: str | None,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        """加载记忆，合并双后端（YAML 优先）"""
        sqlite_entries = self._sqlite.load(project_id, category)

        if not self._yaml:
            return sqlite_entries

        yaml_entries = self._yaml.load(project_id, category)

        # 合并：YAML 优先
        # 用 (category, key) 去重，YAML 条目覆盖 SQLite 同 key 条目
        seen: dict[tuple[str, str], dict[str, Any]] = {}
        for e in sqlite_entries:
            k = (e.get("category", ""), e.get("key", ""))
            seen[k] = e
        for e in yaml_entries:
            k = (e.get("category", ""), e.get("key", ""))
            seen[k] = e  # YAML 覆盖 SQLite

        return list(seen.values())

    def delete(self, project_id: str | None, category: str, key: str) -> bool:
        """删除记忆，双后端都删"""
        ok_sqlite = self._sqlite.delete(project_id, category, key)
        ok_yaml = self._yaml.delete(project_id, category, key) if self._yaml else False
        return ok_sqlite or ok_yaml

    # ── 列语义操作 ──────────────────────────────────────────

    def save_column_semantic(
        self,
        project_id: str,
        column: str,
        sem_def: ColumnSemanticDef,
    ) -> None:
        """保存列语义定义"""
        self.save(
            project_id, "column_semantic", column,
            sem_def.model_dump(exclude_none=True),
            source=sem_def.source,
            confidence=sem_def.confidence,
        )

    def get_column_semantics(self, project_id: str) -> dict[str, ColumnSemanticDef]:
        """获取项目的所有列语义定义（YAML 优先）"""
        # YAML 列语义
        yaml_cols: dict[str, dict[str, Any]] = {}
        if self._yaml:
            yaml_cols = self._yaml.load_column_semantics(project_id)

        # SQLite 列语义
        sqlite_cols = self._sqlite.load_column_semantics(project_id)

        # 合并：YAML 优先
        merged: dict[str, dict[str, Any]] = {}
        merged.update(sqlite_cols)
        merged.update(yaml_cols)  # YAML 覆盖

        result: dict[str, ColumnSemanticDef] = {}
        for col_name, col_dict in merged.items():
            try:
                result[col_name] = ColumnSemanticDef(**col_dict)
            except Exception:
                pass

        return result

    # ── 目标变量 ────────────────────────────────────────────

    def save_target(
        self,
        project_id: str,
        column: str,
        source: str = "auto",
    ) -> None:
        """保存目标变量"""
        self.save(
            project_id, "target_variable", column,
            {"column": column, "role": "target"},
            source=source, confidence=0.9,
        )

    def get_target(self, project_id: str) -> str | None:
        """获取目标变量"""
        entries = self.load(project_id, category="target_variable")
        if entries:
            e = entries[0]
            val = e.get("value", {})
            if isinstance(val, dict):
                return val.get("column", e.get("key"))
            return e.get("key")
        return None

    # ── 清洗偏好 ────────────────────────────────────────────

    def save_cleaning_pref(
        self,
        project_id: str,
        column: str,
        strategy: str,
        reason: str = "",
        source: str = "auto",
    ) -> None:
        """保存清洗偏好"""
        self.save(
            project_id, "cleaning_pref", column,
            {"strategy": strategy, "reason": reason},
            source=source, confidence=0.6,
        )

    def get_cleaning_prefs(self, project_id: str) -> dict[str, CleaningPrefDef]:
        """获取清洗偏好"""
        entries = self.load(project_id, category="cleaning_pref")
        result: dict[str, CleaningPrefDef] = {}
        for e in entries:
            val = e.get("value", {})
            if isinstance(val, dict):
                try:
                    result[e["key"]] = CleaningPrefDef(**val)
                except Exception:
                    pass
        return result

    # ── 分析模式 ────────────────────────────────────────────

    def save_analysis_pattern(
        self,
        project_id: str,
        analysis_type: str,
        question: str = "",
        significance: str = "",
        source: str = "auto",
    ) -> None:
        """保存分析模式"""
        self.save(
            project_id, "analysis_pattern", analysis_type,
            {"question": question, "significance": significance},
            source=source, confidence=0.6,
        )

    def get_analysis_patterns(self, project_id: str) -> list[AnalysisPatternDef]:
        """获取分析模式"""
        entries = self.load(project_id, category="analysis_pattern")
        result: list[AnalysisPatternDef] = []
        for e in entries:
            val = e.get("value", {})
            if isinstance(val, dict):
                try:
                    # val 可能包含 analysis_type（来自 YAML export），需要移除避免重复
                    val_clean = {k: v for k, v in val.items() if k != "analysis_type"}
                    result.append(AnalysisPatternDef(
                        analysis_type=e["key"],
                        **val_clean,
                    ))
                except Exception:
                    pass
        return result

    # ── 用户笔记 ────────────────────────────────────────────

    def save_user_note(self, project_id: str, key: str, note: str) -> None:
        """保存用户笔记"""
        self.save(
            project_id, "user_note", key, note,
            source="user", confidence=1.0,
        )

    def get_user_notes(self, project_id: str) -> dict[str, str]:
        """获取用户笔记"""
        entries = self.load(project_id, category="user_note")
        result: dict[str, str] = {}
        for e in entries:
            val = e.get("value", "")
            result[e["key"]] = str(val) if not isinstance(val, str) else val
        return result

    # ── Schema YAML I/O ─────────────────────────────────────

    def export_progress_yaml(self, project_id: str, path: Path | None = None) -> Path:
        """
        导出项目记忆为 progress.yaml

        合并记忆中的 column_semantic、target、confounders 等为完整 YAML
        """
        if path is None and self._yaml:
            path = self._yaml.path
        elif path is None:
            path = Path.home() / ".hagoku" / "projects" / (project_id or "_global") / "progress.yaml"

        # 收集数据
        columns = self.get_column_semantics(project_id)
        target = self.get_target(project_id)
        cleaning_prefs = self.get_cleaning_prefs(project_id)
        analysis_patterns = self.get_analysis_patterns(project_id)
        user_notes = self.get_user_notes(project_id)

        # 构建 YAML 数据
        data: dict[str, Any] = {}

        if columns:
            data["columns"] = {
                col: sem.model_dump(exclude_none=True)
                for col, sem in columns.items()
            }

        if target:
            data["target"] = target

        # 额外元数据（从 column_semantic 中提取 confounders 等）
        confounders = [
            col for col, sem in columns.items()
            if sem.role == "control"
        ]
        if confounders:
            data["confounders"] = confounders

        time_col = [
            col for col, sem in columns.items()
            if sem.semantic == "datetime" and sem.role in ("time_index", "time")
        ]
        if time_col:
            data["time_column"] = time_col[0]

        # _memory 段：非 schema 核心的记忆
        memory_section: dict[str, Any] = {}
        if cleaning_prefs:
            memory_section["cleaning_pref"] = {
                col: pref.model_dump(exclude_none=True)
                for col, pref in cleaning_prefs.items()
            }
        if analysis_patterns:
            memory_section["analysis_pattern"] = {
                p.analysis_type: p.model_dump(exclude_none=True)
                for p in analysis_patterns
            }
        if user_notes:
            memory_section["user_note"] = user_notes

        if memory_section:
            data["_memory"] = memory_section

        # 写入
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        return path

    def import_progress_yaml(self, project_id: str, path: Path | None = None) -> int:
        """
        导入 progress.yaml 到记忆系统

        YAML 值写入 SQLite（双后端同步），YAML 文件保持不变
        返回导入的记忆条数
        """
        if path is None and self._yaml:
            path = self._yaml.path
        elif path is None:
            return 0

        if not path.exists():
            return 0

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        count = 0

        # 导入 columns
        for col_name, col_def in data.get("columns", {}).items():
            if isinstance(col_def, dict):
                sem_def = ColumnSemanticDef(**{k: v for k, v in col_def.items()
                                               if k in ColumnSemanticDef.model_fields})
                sem_def.source = "user"
                self.save_column_semantic(project_id, col_name, sem_def)
                count += 1

        # 导入 target
        target = data.get("target")
        if target:
            self.save_target(project_id, target, source="user")
            count += 1

        # 导入 _memory 段
        for cat_name, entries in data.get("_memory", {}).items():
            if not isinstance(entries, dict):
                continue
            for k, v in entries.items():
                self.save(project_id, cat_name, k, v, source="auto", confidence=0.8)
                count += 1

        return count

    def _import_yaml_to_sqlite(self) -> int:
        """将 YAML 内容同步到 SQLite（内部用）"""
        if not self._yaml:
            return 0
        entries = self._yaml.load(None)  # 全量加载
        count = 0
        for e in entries:
            pid = e.get("project_id")  # 可能为 None（全局记忆）
            cat = e.get("category", "")
            key = e.get("key", "")
            val = e.get("value", {})
            src = e.get("source", "user")
            conf = e.get("confidence", 1.0)
            if cat and key:
                self._sqlite.save(
                    pid, cat, key,
                    json.dumps(val, ensure_ascii=False) if not isinstance(val, str) else val,
                    source=src, confidence=conf,
                )
                count += 1
        return count

    # ── 核心：记忆应用自身 ───────────────────────────────────

    def apply_to_context(self, project_id: str, context: Any) -> Any:
        """
        将记忆应用到 DataContext

        替代 scout._apply_memory()，但更全面：
        1. column_semantic 覆盖推断
        2. target 设置
        3. confounders / time_column / group_columns
        4. column_descriptions / units
        5. user_constraints
        6. derive_from_column_semantics()
        """
        from ..agents.scout import SemanticType

        # 1. 列语义覆盖
        confirmed = self.get_column_semantics(project_id)
        for sem in context.column_semantics:
            if sem.column_name in confirmed:
                override = confirmed[sem.column_name]
                try:
                    sem.inferred_type = SemanticType(override.semantic)
                except ValueError:
                    pass
                if override.role:
                    sem.suggested_role = override.role
                sem.needs_user_input = False
                sem.confidence = override.confidence
                sem.evidence = f"记忆（{'用户确认' if override.source == 'user' else '自动学习'}）"

                # ignore 标记
                if override.ignore:
                    sem.suggested_role = "ignore"

        # 2. 目标变量
        target = self.get_target(project_id)
        if target:
            context.target = target
            for sem in context.column_semantics:
                if sem.column_name == target and sem.inferred_type != SemanticType.TARGET:
                    sem.inferred_type = SemanticType.TARGET
                    sem.suggested_role = "target"
                    sem.needs_user_input = False
                    sem.confidence = 1.0
                    sem.evidence = "记忆（目标变量）"

        # 3. 从 confirmed 语义中提取 confounders / time / group
        for col_name, sem_def in confirmed.items():
            if sem_def.role == "control" and col_name not in context.confounders:
                context.confounders.append(col_name)
            if sem_def.semantic == "datetime" and sem_def.role in ("time_index", "time"):
                context.time_column = col_name
            if sem_def.role == "group" and col_name not in context.group_columns:
                context.group_columns.append(col_name)

        # 4. 描述和单位
        for col_name, sem_def in confirmed.items():
            if sem_def.description:
                context.column_descriptions[col_name] = sem_def.description
            if sem_def.unit:
                context.units[col_name] = sem_def.unit

        # 5. 用户约束
        notes = self.get_user_notes(project_id)
        if notes:
            context.user_constraints = list(notes.values())

        # 6. 推导派生字段
        if hasattr(context, "derive_from_column_semantics"):
            context.derive_from_column_semantics()

        return context

    # ── 项目记忆构建 ─────────────────────────────────────────

    def build_memory_project(self, project_id: str) -> dict[str, Any]:
        """
        构建 Scout Agent 所需的 memory_project 字典。

        格式：{"fields": {"col_name": "description", ...}}

        从已持久化的 column_semantics 中提取有 description 的字段。
        用于每次 Scout 运行时注入历史字段理解，避免用户重复回答。
        """
        fields: dict[str, str] = {}
        display_names: dict[str, str] = {}
        confirmed = self.get_column_semantics(project_id)
        for col_name, sem_def in confirmed.items():
            if sem_def.description:
                fields[col_name] = sem_def.description
            if sem_def.display_name:
                display_names[col_name] = sem_def.display_name
        return {"fields": fields, "display_names": display_names}

    def persist_field_descriptions(
        self,
        project_id: str,
        column_descriptions: dict[str, str],
        column_display_names: dict[str, str] | None = None,
    ) -> int:
        """
        将用户确认的字段描述持久化到项目记忆。

        对每个有描述的列，更新或创建 ColumnSemanticDef，标记 source="user"。
        返回新持久化的字段数。
        """
        count = 0
        display_names = column_display_names or {}

        for col_name, desc in column_descriptions.items():
            desc = (desc or "").strip()
            dn = (display_names.get(col_name, "") or "").strip()
            if not desc and not dn:
                continue

            # 读取已有定义（若存在则合并，否则新建）
            existing = self.get_column_semantics(project_id).get(col_name)
            if existing:
                sem_def = existing
                if desc:
                    sem_def.description = desc
                if dn:
                    sem_def.display_name = dn
                sem_def.source = "user"
                sem_def.confidence = 1.0
            else:
                sem_def = ColumnSemanticDef(
                    semantic="unknown",
                    description=desc if desc else None,
                    unit=dn if dn else None,
                    source="user",
                    confidence=1.0,
                )

            self.save_column_semantic(project_id, col_name, sem_def)
            count += 1

        return count

    # ── 核心：记忆从结果学习 ─────────────────────────────────

    def learn_from_run(
        self,
        project_id: str,
        context: Any,
        results: list[Any],
        cleaning_report: Any,
    ) -> int:
        """
        从一次完整运行中学习

        替代 orchestrator._learn_from_run()
        返回新记忆条数
        """
        count = 0

        # context 兼容 dict 和对象两种格式
        def _get(obj, key, default=None):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        # 1. 学习列语义（高置信度或用户确认的）
        for sem in (_get(context, "column_semantics") or []):
            confidence = _get(sem, "confidence", 0)
            evidence = _get(sem, "evidence", "") or ""
            inferred_type = _get(sem, "inferred_type", "unknown")
            # 兼容 Enum 和字符串
            if hasattr(inferred_type, "value"):
                inferred_type = inferred_type.value
            suggested_role = _get(sem, "suggested_role", "feature") or "feature"
            col_name = _get(sem, "column_name", "")

            if confidence >= 0.8 or "用户" in evidence or "记忆" in evidence:
                sem_def = ColumnSemanticDef(
                    semantic=str(inferred_type),
                    role=suggested_role,
                    confidence=confidence,
                    source="user" if "用户" in evidence else "auto",
                )
                self.save_column_semantic(project_id, col_name, sem_def)
                count += 1

        # 2. 学习目标变量
        target = _get(context, "target")
        if target:
            self.save_target(project_id, target, source="auto")
            count += 1

        # 3. 学习清洗偏好
        if hasattr(cleaning_report, "operations"):
            for op in cleaning_report.operations:
                strategy_val = op.strategy.value if hasattr(op.strategy, "value") else str(op.strategy)
                self.save_cleaning_pref(
                    project_id, op.column, strategy_val,
                    reason=op.reason, source="auto",
                )
                count += 1

        # 4. 学习分析模式
        for result in (results or []):
            self.save_analysis_pattern(
                project_id,
                _get(result, "analysis_type", "unknown"),
                question=_get(result, "question", ""),
                significance=_get(result, "significance", "unknown"),
                source="auto",
            )
            count += 1

        # 5. 自动导出 progress.yaml
        self.export_progress_yaml(project_id)

        return count

    # ── Resume 支持 ─────────────────────────────────────────

    def get_resume_state(self, project_id: str) -> dict[str, Any] | None:
        """获取项目的恢复状态"""
        state = self._db.get_project_state(project_id)
        if not state or state.get("stage") in (None, "created", ""):
            return None
        return {
            "cleaned_path": state.get("cleaned_path", ""),
            "raw_path": state.get("raw_path", ""),
            "context": state.get("context_json"),
            "stage": state.get("stage", "created"),
        }

    def save_resume_state(
        self,
        project_id: str,
        stage: str,
        cleaned_path: str = "",
        raw_path: str = "",
        context: Any = None,
        run_id: str = "",
    ) -> None:
        """保存项目的恢复状态"""
        kwargs: dict[str, Any] = {"stage": stage}
        if cleaned_path:
            kwargs["cleaned_path"] = cleaned_path
        if raw_path:
            kwargs["raw_path"] = raw_path
        if context and hasattr(context, "to_dict"):
            kwargs["context_json"] = context.to_dict()
        self._db.update_project_state(project_id, **kwargs)
