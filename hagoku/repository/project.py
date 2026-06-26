"""ProjectRepository — 项目文件 I/O 层

纯文件系统操作，不依赖 Orchestrator。
统一 project.json 格式，兼容读旧 project.yaml。

职责：
- 项目 CRUD（创建/列表/详情/删除/重命名）
- 数据文件管理（添加/删除/查询路径）
- 安全删除（_safe_rmtree 防符号链接攻击）
- 项目锁（防并发写入损坏）
- 元数据读写（JSON 格式，YAML 向后兼容）
"""

from __future__ import annotations

import json as _json
import re
import shutil
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

# Windows 不允许的文件名字符
_WINDOWS_FORBIDDEN_CHARS = re.compile(r'[<>:"/\\|?*]')

# ── 项目锁 ─────────────────────────────────────────────────────

_project_locks: dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()


def _get_project_lock(project_name: str) -> threading.Lock:
    """获取项目的锁（懒创建）"""
    with _locks_lock:
        if project_name not in _project_locks:
            _project_locks[project_name] = threading.Lock()
        return _project_locks[project_name]


# ── 安全函数 ───────────────────────────────────────────────────

def _validate_project_name(name: str) -> None:
    """验证项目名称安全性，防止路径遍历和非法字符。

    Raises:
        ValueError: 名称包含危险字符或路径遍历
    """
    if not name or not name.strip():
        raise ValueError("项目名称不能为空")
    if Path(name).is_absolute():
        raise ValueError("项目名称不能是绝对路径")
    if ".." in name:
        raise ValueError("项目名称不能包含路径遍历符 '..'")
    if _WINDOWS_FORBIDDEN_CHARS.search(name):
        raise ValueError(f"项目名称包含非法字符: {name.strip()}")
    if any(ord(c) < 32 for c in name):
        raise ValueError("项目名称不能包含控制字符")


def _safe_rmtree(path: Path, base_dir: Path) -> None:
    """安全删除目录，防止符号链接攻击。

    Raises:
        ValueError: 路径越界或存在符号链接指向目录外
    """
    real_path = path.resolve()
    real_base = base_dir.resolve()

    try:
        real_path.relative_to(real_base)
    except ValueError:
        raise ValueError(f"禁止删除目录外的内容: {path}")

    if path.is_symlink():
        raise ValueError("禁止删除符号链接")

    for item in real_path.rglob("*"):
        if item.is_symlink():
            try:
                item.resolve().relative_to(real_base)
            except ValueError:
                raise ValueError(f"目录内存在指向外部的符号链接: {item}")


# ── 数据类型 ────────────────────────────────────────────────────

@dataclass
class DataFileInfo:
    """项目内的数据文件"""
    name: str
    path: Path          # 相对于项目根目录的路径
    size_kb: float
    added_at: datetime
    source: str         # "input" | "process"


@dataclass
class ProjectInfo:
    """项目信息（不含运行时状态）"""
    name: str
    description: str
    created_at: datetime
    data_files: list[DataFileInfo] = field(default_factory=list)
    process_files: list[DataFileInfo] = field(default_factory=list)
    run_count: int = 0
    last_run: datetime | None = None
    current_run_id: str = ""
    project_dir: Path = field(default_factory=Path)

    @property
    def latest_input(self) -> Path | None:
        """最新添加的输入文件"""
        inputs = [f for f in self.data_files if f.source == "input"]
        if not inputs:
            return None
        return self.project_dir / inputs[-1].path

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at.isoformat(),
            "data_files": [
                {"name": f.name, "path": str(f.path), "size_kb": f.size_kb,
                 "added_at": f.added_at.isoformat(), "source": f.source}
                for f in self.data_files
            ],
            "process_files": [
                {"name": f.name, "path": str(f.path), "size_kb": f.size_kb,
                 "added_at": f.added_at.isoformat(), "source": f.source}
                for f in self.process_files
            ],
            "run_count": self.run_count,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "current_run_id": self.current_run_id,
        }


# ── ProjectRepository ──────────────────────────────────────────

class ProjectRepository:
    """项目文件 I/O 层。

    每个项目目录结构：
    project_dir/
    ├── project.json     # 元数据
    ├── input/           # 原始数据文件
    ├── process/         # 清洗后数据、中间结果
    ├── output/          # 报告、可视化
    ├── memory/          # 项目记忆笔记
    └── runs/            # 分析运行记录
    """

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        # 项目注册表：name → 目录路径（支持自定义目录）
        self._registry_path = self.base_dir.parent / "project_registry.json"
        self._registry: dict[str, str] = {}
        self._registry_loaded = False

    # ── 注册表 ──────────────────────────────────────────────────

    def _load_registry(self) -> dict[str, str]:
        if self._registry_loaded:
            return self._registry
        self._registry_loaded = True
        if self._registry_path.exists():
            try:
                self._registry = _json.loads(
                    self._registry_path.read_text(encoding="utf-8"))
            except Exception:
                self._registry = {}
        # 兼容旧 YAML 注册表
        old_path = self._registry_path.with_suffix(".yaml")
        if not self._registry and old_path.exists():
            try:
                import yaml
                self._registry = yaml.safe_load(old_path.read_text(encoding="utf-8")) or {}
            except Exception:
                pass
        return self._registry

    def _save_registry(self) -> None:
        self._registry_path.parent.mkdir(parents=True, exist_ok=True)
        # 原子写入
        tmp = self._registry_path.with_suffix(".tmp")
        tmp.write_text(_json.dumps(self._registry, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        tmp.rename(self._registry_path)

    # ── 项目 CRUD ──────────────────────────────────────────────

    def create(self, name: str, description: str = "",
               *, parent_dir: Path | None = None) -> ProjectInfo:
        """创建新项目。

        Raises:
            FileExistsError: 项目已存在
            ValueError: 项目名称非法
        """
        _validate_project_name(name)

        base = Path(parent_dir) if parent_dir else self.base_dir
        base.mkdir(parents=True, exist_ok=True)
        project_dir = base / name

        # 验证最终路径安全
        try:
            project_dir.resolve().relative_to(base.resolve())
        except ValueError:
            raise ValueError(f"禁止在目录外创建项目: {project_dir}")

        if project_dir.exists():
            raise FileExistsError(f"项目 '{name}' 已存在")

        for subdir in ("input", "process", "output", "memory", "runs"):
            (project_dir / subdir).mkdir(parents=True, exist_ok=True)

        now = datetime.now()
        meta = {
            "name": name,
            "description": description,
            "created_at": now.isoformat(),
            "run_count": 0,
            "last_run": None,
            "current_run_id": "",
            "data_files": [],
            "process_files": [],
        }
        self._save_meta(project_dir, meta)

        self._load_registry()
        self._registry[name] = str(project_dir)
        self._save_registry()

        return ProjectInfo(
            name=name, description=description, created_at=now,
            data_files=[], process_files=[], run_count=0, last_run=None,
            project_dir=project_dir,
        )

    def list_projects(self) -> list[ProjectInfo]:
        """列出所有项目（注册表优先，扫描 base_dir 向后兼容）"""
        projects: list[ProjectInfo] = []
        seen: set[str] = set()

        registry = self._load_registry()
        for name, path_str in registry.items():
            d = Path(path_str)
            if not d.exists() or name in seen:
                continue
            try:
                info = self._load_project_info(d)
                if info:
                    projects.append(info)
                    seen.add(name)
            except Exception:
                continue

        if self.base_dir.exists():
            for d in sorted(self.base_dir.iterdir()):
                if not d.is_dir() or d.name in seen:
                    continue
                try:
                    info = self._load_project_info(d)
                    if info:
                        projects.append(info)
                        seen.add(d.name)
                except Exception:
                    continue

        return sorted(projects,
                      key=lambda p: p.last_run or p.created_at, reverse=True)

    def get_info(self, name: str) -> ProjectInfo | None:
        """获取项目详情"""
        d = self._resolve_dir(name)
        return self._load_project_info(d) if d else None

    # 别名（兼容旧 storage/pm.py API）
    def info(self, name: str) -> ProjectInfo | None:
        return self.get_info(name)

    def list(self) -> list[ProjectInfo]:
        return self.list_projects()

    def exists(self, name: str) -> bool:
        """检查项目是否存在"""
        return self._resolve_dir(name) is not None

    def delete(self, name: str) -> bool:
        """安全删除项目。

        Raises:
            ValueError: 路径越界或存在危险的符号链接
        """
        d = self._resolve_dir(name)
        if d is None:
            return False

        _safe_rmtree(d, self.base_dir)
        shutil.rmtree(d)

        registry = self._load_registry()
        registry.pop(name, None)
        self._save_registry()
        return True

    def rename(self, old_name: str, new_name: str) -> bool:
        """重命名项目"""
        old_dir = self._resolve_dir(old_name)
        if old_dir is None:
            return False
        new_dir = old_dir.parent / new_name
        if new_dir.exists():
            return False

        old_dir.rename(new_dir)

        registry = self._load_registry()
        if old_name in registry:
            registry[new_name] = str(new_dir)
            registry.pop(old_name)
            self._save_registry()

        meta = self._load_meta(new_dir)
        if meta:
            meta["name"] = new_name
            self._save_meta(new_dir, meta)

        return True

    def update_description(self, name: str, description: str) -> bool:
        """更新项目描述"""
        d = self._resolve_dir(name)
        if d is None:
            return False
        meta = self._load_meta(d)
        meta["description"] = description
        self._save_meta(d, meta)
        return True

    # ── 路径查询 ────────────────────────────────────────────────

    def get_project_dir(self, name: str) -> Path | None:
        """获取项目根目录"""
        return self._resolve_dir(name)

    def get_latest_data(self, name: str) -> Path | None:
        """获取项目最新添加的输入文件路径"""
        info = self.get_info(name)
        return info.latest_input if info else None

    def get_data_path(self, name: str, filename: str) -> Path | None:
        """获取项目内指定数据文件的绝对路径"""
        d = self._resolve_dir(name)
        if d is None:
            return None
        p = d / "input" / filename
        return p if p.exists() else None

    def get_process_path(self, name: str, filename: str) -> Path:
        """获取过程文件路径（项目内）"""
        d = self._ensure_dir(name)
        return d / "process" / filename

    def get_output_path(self, name: str, filename: str = "report.html") -> Path:
        """获取输出文件路径（项目内）"""
        d = self._ensure_dir(name)
        return d / "output" / filename

    def get_runs_dir(self, name: str) -> Path:
        """获取 runs 目录路径"""
        d = self._ensure_dir(name)
        runs = d / "runs"
        runs.mkdir(exist_ok=True)
        return runs

    # ── 数据文件管理 ────────────────────────────────────────────

    def add_data(self, name: str, file_path: Path, *,
                 copy: bool = True) -> DataFileInfo:
        """向项目添加数据文件。

        Raises:
            FileNotFoundError: 项目或文件不存在
        """
        d = self._ensure_dir(name)
        source = Path(file_path).resolve()
        if not source.exists():
            raise FileNotFoundError(f"数据文件不存在: {file_path}")

        dest_name = source.name
        dest = d / "input" / dest_name
        dest = self._unique_path(dest)
        shutil.copy2(source, dest)

        info = DataFileInfo(
            name=dest.name, path=Path("input") / dest.name,
            size_kb=round(source.stat().st_size / 1024, 1),
            added_at=datetime.now(), source="input",
        )

        meta = self._load_meta(d)
        if "data_files" not in meta:
            meta["data_files"] = []
        meta["data_files"].append({
            "name": info.name, "path": str(info.path),
            "size_kb": info.size_kb, "added_at": info.added_at.isoformat(),
            "source": "input",
        })
        self._save_meta(d, meta)
        return info

    def remove_data(self, name: str, filename: str) -> bool:
        """从项目移除数据文件"""
        d = self._ensure_dir(name)
        target = d / "input" / filename
        if not target.exists():
            return False
        target.unlink()
        meta = self._load_meta(d)
        meta["data_files"] = [
            f for f in meta.get("data_files", []) if f["name"] != filename
        ]
        self._save_meta(d, meta)
        return True

    def add_process_file(self, name: str, filename: str,
                         content: bytes | None = None) -> DataFileInfo:
        """向项目添加过程文件（如清洗后的数据）。"""
        d = self._ensure_dir(name)
        dest = d / "process" / filename
        dest = self._unique_path(dest)
        if content:
            dest.write_bytes(content)
        else:
            dest.touch()

        info = DataFileInfo(
            name=dest.name, path=Path("process") / dest.name,
            size_kb=round(dest.stat().st_size / 1024, 1),
            added_at=datetime.now(), source="process",
        )

        meta = self._load_meta(d)
        if "process_files" not in meta:
            meta["process_files"] = []
        meta["process_files"].append({
            "name": info.name, "path": str(info.path),
            "size_kb": info.size_kb, "added_at": info.added_at.isoformat(),
            "source": "process",
        })
        self._save_meta(d, meta)
        return info

    def list_data_files(self, name: str) -> list[DataFileInfo]:
        """列出项目所有输入文件"""
        info = self.get_info(name)
        if info is None:
            return []
        return [f for f in info.data_files if f.source == "input"]

    # ── 运行记录 ────────────────────────────────────────────────

    def record_run(self, name: str) -> None:
        """记录一次分析运行"""
        d = self._ensure_dir(name)
        meta = self._load_meta(d)
        meta["run_count"] = meta.get("run_count", 0) + 1
        meta["last_run"] = datetime.now().isoformat()
        self._save_meta(d, meta)

    def set_current_run(self, name: str, run_id: str) -> None:
        """设置当前活跃 run ID"""
        d = self._ensure_dir(name)
        meta = self._load_meta(d)
        meta["current_run_id"] = run_id
        self._save_meta(d, meta)

    # ── 记忆笔记 ────────────────────────────────────────────────

    def get_memory_dir(self, name: str) -> Path | None:
        d = self._resolve_dir(name)
        return (d / "memory") if d else None

    def save_memory(self, name: str, notes: str) -> Path | None:
        memory_dir = self.get_memory_dir(name)
        if memory_dir is None:
            return None
        memory_dir.mkdir(parents=True, exist_ok=True)
        p = memory_dir / "notes.md"
        p.write_text(notes, encoding="utf-8")
        return p

    def load_memory(self, name: str) -> str:
        memory_dir = self.get_memory_dir(name)
        if memory_dir is None:
            return ""
        p = memory_dir / "notes.md"
        return p.read_text(encoding="utf-8") if p.exists() else ""

    # ── 存储统计 ────────────────────────────────────────────────

    def get_storage_stats(self, name: str) -> dict[str, dict[str, Any]]:
        d = self._resolve_dir(name)
        if d is None:
            return {}
        stats: dict[str, dict[str, Any]] = {}
        total_count, total_size = 0, 0.0
        for sub in ("input", "process", "output", "memory", "runs"):
            sp = d / sub
            files = [f for f in sp.iterdir() if f.is_file()] if sp.exists() else []
            sz = sum(f.stat().st_size for f in files) / (1024 * 1024)
            stats[sub] = {"count": len(files), "size_mb": round(sz, 3)}
            total_count += len(files)
            total_size += sz * 1024 * 1024
        stats["total"] = {
            "count": total_count,
            "size_mb": round(total_size / (1024 * 1024), 3),
        }
        return stats

    # ── 内部方法 ────────────────────────────────────────────────

    def _resolve_dir(self, name: str) -> Path | None:
        """解析项目真实目录（注册表优先）"""
        registry = self._load_registry()
        if name in registry:
            d = Path(registry[name])
            return d if d.exists() else None
        d = self.base_dir / name
        return d if d.exists() else None

    def _ensure_dir(self, name: str) -> Path:
        d = self._resolve_dir(name)
        if d is None:
            raise FileNotFoundError(f"项目不存在: {name}")
        return d

    def _meta_path(self, project_dir: Path) -> Path:
        return project_dir / "project.json"

    def _load_meta(self, project_dir: Path) -> dict[str, Any]:
        """读取项目元数据。优先 project.json，回退 project.yaml。"""
        json_path = project_dir / "project.json"
        if json_path.exists():
            try:
                return _json.loads(json_path.read_text(encoding="utf-8")) or {}
            except Exception:
                pass

        yaml_path = project_dir / "project.yaml"
        if yaml_path.exists():
            try:
                import yaml
                return yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
            except Exception:
                pass

        return {}

    def _save_meta(self, project_dir: Path, meta: dict[str, Any]) -> None:
        """原子写入 project.json（加锁）"""
        lock = _get_project_lock(project_dir.name)
        with lock:
            json_path = project_dir / "project.json"
            tmp = json_path.with_suffix(".tmp")
            tmp.write_text(
                _json.dumps(meta, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            tmp.rename(json_path)

    def _load_project_info(self, project_dir: Path) -> ProjectInfo | None:
        meta = self._load_meta(project_dir)
        if not meta:
            return None
        name = meta.get("name") or project_dir.name

        data_files = [
            DataFileInfo(
                name=f["name"], path=Path(f["path"]),
                size_kb=f.get("size_kb", 0),
                added_at=datetime.fromisoformat(f["added_at"]),
                source=f.get("source", "input"),
            )
            for f in meta.get("data_files", []) if f.get("path")
        ]
        process_files = [
            DataFileInfo(
                name=f["name"], path=Path(f["path"]),
                size_kb=f.get("size_kb", 0),
                added_at=datetime.fromisoformat(f["added_at"]),
                source=f.get("source", "process"),
            )
            for f in meta.get("process_files", []) if f.get("path")
        ]

        last_run = None
        if meta.get("last_run"):
            try:
                last_run = datetime.fromisoformat(meta["last_run"])
            except (ValueError, TypeError):
                last_run = None

        created_at = datetime.now()
        if meta.get("created_at"):
            try:
                created_at = datetime.fromisoformat(meta["created_at"])
            except (ValueError, TypeError):
                pass

        return ProjectInfo(
            name=name,
            description=meta.get("description", ""),
            created_at=created_at,
            data_files=data_files,
            process_files=process_files,
            run_count=meta.get("run_count", 0),
            last_run=last_run,
            current_run_id=meta.get("current_run_id", ""),
            project_dir=project_dir,
        )

    @staticmethod
    def _unique_path(path: Path) -> Path:
        """生成不冲突的文件路径（同名时加序号）"""
        if not path.exists():
            return path
        safe_stem = re.sub(r'\.\.+', '', path.stem)
        safe_stem = _WINDOWS_FORBIDDEN_CHARS.sub('', safe_stem)
        safe_stem = safe_stem.strip() or 'file'
        parent = path.parent
        n = 1
        while True:
            candidate = parent / f"{safe_stem}_{n}{path.suffix}"
            if not candidate.exists():
                return candidate
            n += 1
