"""HaGoKu 输出管理器"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import OutputConfig


class OutputManager:
    """管理输出路径、报告命名和归档"""

    def __init__(self, config: OutputConfig, project_name: str) -> None:
        """
        Args:
            config: 输出配置
            project_name: 项目名
        """
        self.config = config
        self.project_name = project_name
        self._project_dir = config.project_dir / project_name
        self._project_dir.mkdir(parents=True, exist_ok=True)

    @property
    def project_dir(self) -> Path:
        """项目根目录"""
        return self._project_dir

    @property
    def input_dir(self) -> Path:
        """输入数据目录"""
        d = self._project_dir / "input"
        d.mkdir(exist_ok=True)
        return d

    @property
    def process_dir(self) -> Path:
        """过程文件目录（清洗后数据、中间结果）"""
        d = self._project_dir / "process"
        d.mkdir(exist_ok=True)
        return d

    @property
    def output_dir(self) -> Path:
        """项目级输出目录（报告、可视化）"""
        d = self._project_dir / "output"
        d.mkdir(exist_ok=True)
        return d

    @property
    def data_dir(self) -> Path:
        """数据目录（向后兼容，等同于 process_dir）"""
        return self.process_dir

    def create_run_dir(self, run_id: str | None = None) -> Path:
        """
        创建运行目录结构

        Args:
            run_id: 运行 ID，不提供则自动生成（日期时间格式）

        Returns:
            运行目录路径
        """
        if run_id is None:
            run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        run_dir = self._project_dir / "runs" / run_id
        for subdir in ("results", "diagnostics", "output", "output/charts"):
            (run_dir / subdir).mkdir(parents=True, exist_ok=True)

        return run_dir

    def get_run_dir(self, run_id: str) -> Path:
        """获取运行目录"""
        return self._project_dir / "runs" / run_id

    def get_output_path(
        self,
        run_dir: Path,
        name: str | None = None,
        fmt: str = "html",
    ) -> Path:
        """
        获取报告输出路径

        Args:
            run_dir: 运行目录
            name: 自定义文件名（不含扩展名），默认用命名模板
            fmt: 输出格式 (html / pdf / docx / md)
        """
        if name is None:
            date_str = datetime.now().strftime(self.config.date_format)
            name = self.config.naming.format(
                project=self.project_name,
                date=date_str,
            )
        return run_dir / "output" / f"{name}.{fmt}"

    def save_run_meta(self, run_dir: Path, meta: dict[str, Any]) -> Path:
        """保存运行元数据"""
        path = run_dir / "run_meta.json"
        with open(path, "w") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        return path

    def load_run_meta(self, run_dir: Path) -> dict[str, Any] | None:
        """加载运行元数据"""
        path = run_dir / "run_meta.json"
        if not path.exists():
            return None
        with open(path) as f:
            return json.load(f)

    def generate_manifest(self, run_dir: Path) -> dict[str, list[dict[str, Any]]]:
        """
        生成输出清单

        Returns:
            按类别分组的文件清单
        """
        manifest: dict[str, list[dict[str, Any]]] = {
            "reports": [],
            "data": [],
            "diagnostics": [],
            "metadata": [],
        }

        def _scan(directory: Path, category: str, prefix: str = "") -> None:
            if not directory.exists():
                return
            for f in sorted(directory.iterdir()):
                if f.is_file():
                    size_kb = f.stat().st_size / 1024
                    manifest[category].append({
                        "name": f"{prefix}{f.name}" if prefix else f.name,
                        "size_kb": round(size_kb, 1),
                        "path": str(f),
                    })
                elif f.is_dir():
                    _scan(f, category, prefix=f"{f.name}/")

        _scan(run_dir / "output", "reports")
        _scan(self.data_dir, "data")
        _scan(run_dir / "diagnostics", "diagnostics")

        # 元数据文件
        for meta_file in ("run_meta.json", "events.jsonl", "context.json", "cleaning.json"):
            p = run_dir / meta_file
            if p.exists():
                manifest["metadata"].append({
                    "name": meta_file,
                    "size_kb": round(p.stat().st_size / 1024, 1),
                    "path": str(p),
                })

        return manifest

    def archive_old_runs(self) -> list[str]:
        """
        归档旧运行，保留最近 N 份

        Returns:
            被归档的运行 ID 列表
        """
        if not self.config.auto_archive:
            return []

        runs_dir = self._project_dir / "runs"
        if not runs_dir.exists():
            return []

        # 获取所有运行目录，按修改时间排序
        run_dirs = sorted(
            [d for d in runs_dir.iterdir() if d.is_dir()],
            key=lambda d: d.stat().st_mtime,
            reverse=True,
        )

        # 保留最近 N 份，其余移入 archive
        archived = []
        archive_dir = runs_dir / "archive"
        for old_dir in run_dirs[self.config.keep_latest_n:]:
            dest = archive_dir / old_dir.name
            archive_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(old_dir), str(dest))
            archived.append(old_dir.name)

        return archived

    def create_latest_symlink(self, run_dir: Path) -> None:
        """创建 latest 符号链接指向最新运行"""
        latest_path = self._project_dir / "latest"
        # 安全删除旧链接（忽略 FileNotFoundError）
        try:
            if latest_path.is_symlink() or latest_path.exists():
                latest_path.unlink()
        except FileNotFoundError:
            pass
        # 创建新链接
        latest_path.symlink_to(run_dir)

    def list_runs(self) -> list[dict[str, Any]]:
        """列出所有运行（从文件系统）"""
        runs_dir = self._project_dir / "runs"
        if not runs_dir.exists():
            return []

        runs = []
        for run_path in sorted(runs_dir.iterdir()):
            if not run_path.is_dir() or run_path.name == "archive":
                continue
            meta = self.load_run_meta(run_path)
            runs.append({
                "run_id": run_path.name,
                "path": str(run_path),
                "meta": meta,
            })
        return runs

    def get_schema_path(self) -> Path:
        """获取字段语义定义文件路径（已迁移到 MemoryManager，保留兼容）"""
        return self._project_dir / "schema.yaml"

    def get_project_output_path(
        self,
        name: str | None = None,
        fmt: str = "html",
    ) -> Path:
        """
        获取项目级输出路径（不经过 runs/ 子目录，直接放在 output/ 下）

        Args:
            name: 自定义文件名，默认用日期时间命名
            fmt: 输出格式
        """
        if name is None:
            date_str = datetime.now().strftime(self.config.date_format)
            name = self.config.naming.format(
                project=self.project_name,
                date=date_str,
            )
        return self.output_dir / f"{name}.{fmt}"
