"""HaGoKu 项目管理器 — 立项、文件组织、生命周期"""

from __future__ import annotations

import shutil
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

# 每个项目一把锁，防止并发读写 project.yaml 造成数据损坏
_project_locks: dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()  # 保护 _project_locks 本身


def _get_project_lock(project_name: str) -> threading.Lock:
    """获取项目的锁（懒创建）"""
    with _locks_lock:
        if project_name not in _project_locks:
            _project_locks[project_name] = threading.Lock()
        return _project_locks[project_name]


@dataclass
class DataFileInfo:
    """项目内的数据文件"""
    name: str
    path: Path  # 相对于项目根目录的路径
    size_kb: float
    added_at: datetime
    source: str  # "input" | "process"


@dataclass
class ProjectInfo:
    """项目信息"""
    name: str
    description: str
    created_at: datetime
    data_files: list[DataFileInfo] = field(default_factory=list)
    process_files: list[DataFileInfo] = field(default_factory=list)
    run_count: int = 0
    last_run: datetime | None = None
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
                {
                    "name": f.name,
                    "path": str(f.path),
                    "size_kb": f.size_kb,
                    "added_at": f.added_at.isoformat(),
                    "source": f.source,
                }
                for f in self.data_files
            ],
            "process_files": [
                {
                    "name": f.name,
                    "path": str(f.path),
                    "size_kb": f.size_kb,
                    "added_at": f.added_at.isoformat(),
                    "source": f.source,
                }
                for f in self.process_files
            ],
            "run_count": self.run_count,
            "last_run": self.last_run.isoformat() if self.last_run else None,
        }


class ProjectManager:
    """项目生命周期管理

    每个项目是一个独立的工作区：
    project_dir/
    ├── project.yaml      # 元数据（description, data_files, run_count）
    ├── input/            # 原始数据文件
    │   ├── sales.csv
    │   └── users.xlsx
    ├── process/          # 清洗后数据、中间结果
    │   └── cleaned_sales.parquet
    └── output/           # 报告、可视化
        └── report.html

    用法：
    pm = ProjectManager(Path("~/.hagokyu/projects"))
    pm.create("Q1销售分析", "分析Q1各渠道ROI")
    pm.add_data("Q1销售分析", Path("/tmp/sales.csv"))
    pm.list()
    """

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        # 项目注册表：name → 目录路径（支持自定义目录的项目也能被 list/info 找到）
        self._registry_path = base_dir.parent / "project_registry.yaml"
        self._registry: dict[str, str] = {}
        self._registry_loaded = False

    def _load_registry(self) -> dict[str, str]:
        if self._registry_loaded:
            return self._registry
        self._registry_loaded = True
        if self._registry_path.exists():
            try:
                with open(self._registry_path) as f:
                    self._registry = yaml.safe_load(f) or {}
            except Exception:
                self._registry = {}
        return self._registry

    def _save_registry(self) -> None:
        self._registry_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._registry_path, "w") as f:
            yaml.safe_dump(self._registry, f, allow_unicode=True)

    # ── 项目 CRUD ──────────────────────────────────────────────

    def create(self, name: str, description: str = "", *, parent_dir: Path | None = None) -> ProjectInfo:
        """
        创建新项目（立项）

        Args:
            name: 项目名称
            description: 项目描述
            parent_dir: 项目目录的父目录（留空则使用默认的 ~/.hagokyu/projects/）

        Returns:
            ProjectInfo 对象

        Raises:
            FileExistsError: 项目已存在
        """
        base = parent_dir or self.base_dir
        base.mkdir(parents=True, exist_ok=True)
        project_dir = base / name
        if project_dir.exists():
            raise FileExistsError(f"项目 '{name}' 已存在")

        # 创建目录结构
        for subdir in ("input", "process", "output"):
            (project_dir / subdir).mkdir(parents=True, exist_ok=True)

        # 写入元数据（只调用一次 datetime.now()）
        now = datetime.now()
        meta = {
            "name": name,
            "description": description,
            "created_at": now.isoformat(),
            "run_count": 0,
            "last_run": None,
            "data_files": [],
            "process_files": [],
        }
        self._save_meta(project_dir, meta)
        # 注册项目路径（用于支持自定义目录的项目也能被 list/info 找到）
        self._load_registry()
        self._registry[name] = str(project_dir)
        self._save_registry()

        return ProjectInfo(
            name=name,
            description=description,
            created_at=now,
            data_files=[],
            process_files=[],
            run_count=0,
            last_run=None,
            project_dir=project_dir,
        )

    def list(self) -> list[ProjectInfo]:
        """列出所有项目（注册表优先，也扫描 base_dir 做向后兼容）"""
        projects: list[ProjectInfo] = []
        seen: set[str] = set()

        # 1. 注册表中的项目（支持自定义目录）
        registry = self._load_registry()
        for name, path_str in registry.items():
            project_dir = Path(path_str)
            if not project_dir.exists() or name in seen:
                continue
            try:
                info = self._load_project_info(project_dir)
                if info:
                    projects.append(info)
                    seen.add(name)
            except Exception:
                continue

        # 2. base_dir 中未注册的项目（向后兼容）
        if self.base_dir.exists():
            for project_dir in sorted(self.base_dir.iterdir()):
                if not project_dir.is_dir() or project_dir.name in seen:
                    continue
                try:
                    info = self._load_project_info(project_dir)
                    if info:
                        projects.append(info)
                        seen.add(project_dir.name)
                except Exception:
                    continue

        return sorted(projects, key=lambda p: p.last_run or p.created_at, reverse=True)

    def info(self, project: str) -> ProjectInfo | None:
        """获取项目详情"""
        # 1. 注册表中查找（支持自定义目录）
        registry = self._load_registry()
        if project in registry:
            project_dir = Path(registry[project])
            if project_dir.exists():
                return self._load_project_info(project_dir)
        # 2. base_dir 中查找（向后兼容）
        project_dir = self.base_dir / project
        if project_dir.exists():
            return self._load_project_info(project_dir)
        return None

    def delete(self, project: str) -> bool:
        """
        删除项目（整个目录）

        Args:
            project: 项目名

        Returns:
            是否成功删除
        """
        # 注册表中查找真实路径
        registry = self._load_registry()
        if project in registry:
            project_dir = Path(registry[project])
        else:
            project_dir = self.base_dir / project
        if not project_dir.exists():
            return False
        shutil.rmtree(project_dir)
        # 从注册表移除
        registry.pop(project, None)
        self._save_registry()
        return True

    def rename(self, old_name: str, new_name: str) -> bool:
        """重命名项目"""
        old_dir = self.base_dir / old_name
        new_dir = self.base_dir / new_name
        if not old_dir.exists() or new_dir.exists():
            return False
        old_dir.rename(new_dir)
        return True

    def exists(self, project: str) -> bool:
        """检查项目是否存在"""
        return (self.base_dir / project).exists()

    # ── 数据文件管理 ────────────────────────────────────────────

    def add_data(self, project: str, file_path: Path, *, copy: bool = True) -> DataFileInfo:
        """
        向项目添加数据文件

        Args:
            project: 项目名
            file_path: 数据文件路径（可以是绝对路径）
            copy: 是否复制文件到项目 input/ 目录（默认 True）

        Returns:
            DataFileInfo 对象

        Raises:
            FileNotFoundError: 项目不存在或文件不存在
        """
        project_dir = self._ensure_project(project)
        source_path = Path(file_path).resolve()

        if not source_path.exists():
            raise FileNotFoundError(f"数据文件不存在: {file_path}")

        if copy:
            dest_name = source_path.name
            dest_path = project_dir / "input" / dest_name
            # 避免文件名冲突
            dest_path = self._unique_path(dest_path)
            shutil.copy2(source_path, dest_path)
            stored_path = Path("input") / dest_path.name
        else:
            # 符号链接模式
            dest_path = project_dir / "input" / source_path.name
            dest_path = self._unique_path(dest_path)
            dest_path.symlink_to(source_path.resolve())
            stored_path = Path("input") / dest_path.name

        size_kb = source_path.stat().st_size / 1024
        info = DataFileInfo(
            name=dest_path.name,
            path=stored_path,
            size_kb=round(size_kb, 1),
            added_at=datetime.now(),
            source="input",
        )

        # 更新元数据
        meta = self._load_meta(project_dir)
        meta.setdefault("data_files", [])
        meta["data_files"].append({
            "name": info.name,
            "path": str(info.path),
            "size_kb": info.size_kb,
            "added_at": info.added_at.isoformat(),
            "source": "input",
        })
        self._save_meta(project_dir, meta)

        return info

    def add_process_file(
        self, project: str, name: str, content: bytes | None = None
    ) -> DataFileInfo:
        """
        向项目添加过程文件（如清洗后的数据）

        Args:
            project: 项目名
            name: 文件名
            content: 文件内容（可选，不传则只创建空文件占位）
        """
        project_dir = self._ensure_project(project)
        dest_path = project_dir / "process" / name
        dest_path = self._unique_path(dest_path)

        if content:
            dest_path.write_bytes(content)
        else:
            dest_path.touch()

        size_kb = dest_path.stat().st_size / 1024
        info = DataFileInfo(
            name=dest_path.name,
            path=Path("process") / dest_path.name,
            size_kb=round(size_kb, 1),
            added_at=datetime.now(),
            source="process",
        )

        meta = self._load_meta(project_dir)
        meta.setdefault("process_files", [])
        meta["process_files"].append({
            "name": info.name,
            "path": str(info.path),
            "size_kb": info.size_kb,
            "added_at": info.added_at.isoformat(),
            "source": "process",
        })
        self._save_meta(project_dir, meta)

        return info

    def remove_data(self, project: str, filename: str) -> bool:
        """从项目移除数据文件"""
        project_dir = self._ensure_project(project)
        target = project_dir / "input" / filename
        if not target.exists():
            return False
        target.unlink()

        # 更新元数据
        meta = self._load_meta(project_dir)
        meta["data_files"] = [
            f for f in meta.get("data_files", []) if f["name"] != filename
        ]
        self._save_meta(project_dir, meta)
        return True

    # ── 路径查询 ────────────────────────────────────────────────

    def get_project_dir(self, project: str) -> Path | None:
        """获取项目根目录"""
        d = self.base_dir / project
        return d if d.exists() else None

    def get_latest_data(self, project: str) -> Path | None:
        """获取项目最新添加的输入文件"""
        info = self.info(project)
        if info is None:
            return None
        return info.latest_input

    def get_data_path(self, project: str, filename: str) -> Path | None:
        """获取项目内指定数据文件的绝对路径"""
        if not self.exists(project):
            return None
        project_dir = self.base_dir / project
        data_path = project_dir / "input" / filename
        return data_path if data_path.exists() else None

    def get_process_path(self, project: str, filename: str) -> Path:
        """获取过程文件路径（项目内）"""
        project_dir = self._ensure_project(project)
        return project_dir / "process" / filename

    def get_output_path(self, project: str, filename: str = "report.html") -> Path:
        """获取输出文件路径（项目内）"""
        project_dir = self._ensure_project(project)
        return project_dir / "output" / filename

    def list_data_files(self, project: str) -> list[DataFileInfo]:
        """列出项目所有输入文件"""
        info = self.info(project)
        if info is None:
            return []
        return [f for f in info.data_files if f.source == "input"]

    # ── 运行计数 ────────────────────────────────────────────────

    def record_run(self, project: str) -> None:
        """记录一次分析运行"""
        project_dir = self._ensure_project(project)
        meta = self._load_meta(project_dir)
        meta["run_count"] = meta.get("run_count", 0) + 1
        meta["last_run"] = datetime.now().isoformat()
        self._save_meta(project_dir, meta)

    # ── 内部 ────────────────────────────────────────────────────

    def _ensure_project(self, project: str) -> Path:
        """确保项目存在，不存在则抛出"""
        project_dir = self.base_dir / project
        if not project_dir.exists():
            raise FileNotFoundError(f"项目不存在: {project}")
        return project_dir

    def _meta_path(self, project_dir: Path) -> Path:
        return project_dir / "project.yaml"

    def _load_meta(self, project_dir: Path) -> dict[str, Any]:
        """读取项目元数据（不加锁，读取旧数据可接受）"""
        meta_path = self._meta_path(project_dir)
        if meta_path.exists():
            return yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
        return {}

    def _save_meta(self, project_dir: Path, meta: dict[str, Any]) -> None:
        """原子写入 project.yaml（加锁防止并发写入损坏）"""
        lock = _get_project_lock(project_dir.name)
        with lock:
            meta_path = self._meta_path(project_dir)
            # 原子写入：先写临时文件，再 rename
            tmp_path = meta_path.with_suffix(".tmp")
            tmp_path.write_text(
                yaml.safe_dump(meta, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
            tmp_path.rename(meta_path)  # rename 是原子的

    def _load_project_info(self, project_dir: Path) -> ProjectInfo | None:
        meta = self._load_meta(project_dir)
        name = meta.get("name") or project_dir.name

        data_files = [
            DataFileInfo(
                name=f["name"],
                path=Path(f["path"]),
                size_kb=f.get("size_kb", 0),
                added_at=datetime.fromisoformat(f["added_at"]),
                source=f.get("source", "input"),
            )
            for f in meta.get("data_files", [])
            if f.get("path")
        ]

        process_files = [
            DataFileInfo(
                name=f["name"],
                path=Path(f["path"]),
                size_kb=f.get("size_kb", 0),
                added_at=datetime.fromisoformat(f["added_at"]),
                source=f.get("source", "process"),
            )
            for f in meta.get("process_files", [])
            if f.get("path")
        ]

        last_run = None
        if meta.get("last_run"):
            try:
                last_run = datetime.fromisoformat(meta["last_run"])
            except Exception:
                pass

        return ProjectInfo(
            name=name,
            description=meta.get("description", ""),
            created_at=datetime.fromisoformat(meta["created_at"])
                if meta.get("created_at")
                else datetime.now(),
            data_files=data_files,
            process_files=process_files,
            run_count=meta.get("run_count", 0),
            last_run=last_run,
            project_dir=project_dir,
        )

    def _unique_path(self, path: Path) -> Path:
        """生成不冲突的文件路径（同名时加序号）"""
        if not path.exists():
            return path
        # 清理文件名，防止路径遍历（去掉 .. 和斜杠）
        safe_stem = path.stem.replace("..", "").replace("/", "").replace("\\", "")
        parent = path.parent
        n = 1
        while True:
            # n=1 → name_1.csv；n=2 → name_2.csv；...
            candidate = parent / f"{safe_stem}_{n}{path.suffix}"
            if not candidate.exists():
                return candidate
            n += 1
