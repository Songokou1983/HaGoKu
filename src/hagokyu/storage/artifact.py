"""HaGoKu 数据制品管理"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pandas as pd


@dataclass
class DataArtifact:
    """数据制品：Agent 之间传递的数据包"""

    artifact_id: str
    file_path: Path
    schema: dict[str, str] = field(default_factory=dict)  # 列名 → 语义描述
    metadata: dict = field(default_factory=dict)  # 行数、生成时间、来源 agent
    lineage: list[str] = field(default_factory=list)  # 数据血缘: ["raw" → "cleaned" → "analysis_ready"]
    cleaning_impact: dict | None = None  # 仅 Cleaner 产出时有

    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            "artifact_id": self.artifact_id,
            "file_path": str(self.file_path),
            "schema": self.schema,
            "metadata": self.metadata,
            "lineage": self.lineage,
            "cleaning_impact": self.cleaning_impact,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DataArtifact":
        """从字典反序列化"""
        return cls(
            artifact_id=data["artifact_id"],
            file_path=Path(data["file_path"]),
            schema=data.get("schema", {}),
            metadata=data.get("metadata", {}),
            lineage=data.get("lineage", []),
            cleaning_impact=data.get("cleaning_impact"),
        )

    def save_meta(self, meta_path: Path | None = None) -> Path:
        """保存元数据 JSON 到制品同目录"""
        if meta_path is None:
            meta_path = self.file_path.with_suffix(".meta.json")
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        with open(meta_path, "w") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        return meta_path

    @classmethod
    def load_meta(cls, meta_path: Path) -> "DataArtifact":
        """从元数据 JSON 加载"""
        with open(meta_path) as f:
            return cls.from_dict(json.load(f))


class ArtifactManager:
    """管理数据制品的创建、存储和检索"""

    def __init__(self, base_dir: Path) -> None:
        """
        Args:
            base_dir: 项目数据目录，如 ~/.hagokyu/projects/sales_analysis/data/
        """
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def create_artifact(
        self,
        agent: str,
        stage: str,
        df: pd.DataFrame,
        schema: dict[str, str] | None = None,
        lineage: list[str] | None = None,
        cleaning_impact: dict | None = None,
    ) -> DataArtifact:
        """
        创建一个数据制品（保存为 Parquet）

        Args:
            agent: 产出此制品的 agent 名
            stage: 阶段名 (raw / cleaned / analysis_ready / ...)
            df: 数据
            schema: 列语义描述
            lineage: 数据血缘
            cleaning_impact: 清洗影响（仅 Cleaner 产出时）
        """
        artifact_id = uuid4().hex[:8]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{stage}_{timestamp}.parquet"
        file_path = self.base_dir / filename

        # 保存 Parquet
        file_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(file_path, index=False, engine="pyarrow")

        # 构建元数据
        metadata = {
            "rows": len(df),
            "columns": list(df.columns),
            "dtypes": {col: str(dt) for col, dt in df.dtypes.items()},
            "agent": agent,
            "stage": stage,
            "created_at": datetime.now().isoformat(),
        }

        artifact = DataArtifact(
            artifact_id=artifact_id,
            file_path=file_path,
            schema=schema or {},
            metadata=metadata,
            lineage=lineage or [stage],
            cleaning_impact=cleaning_impact,
        )

        # 保存元数据
        artifact.save_meta()

        return artifact

    def load_artifact(self, artifact_path: Path) -> tuple[pd.DataFrame, DataArtifact]:
        """加载制品数据 + 元数据"""
        meta_path = artifact_path.with_suffix(".meta.json")
        artifact = DataArtifact.load_meta(meta_path) if meta_path.exists() else DataArtifact(
            artifact_id="unknown",
            file_path=artifact_path,
        )
        df = pd.read_parquet(artifact_path, engine="pyarrow")
        return df, artifact

    def load_latest(self, stage: str) -> tuple[pd.DataFrame, DataArtifact] | None:
        """加载某阶段最新的制品"""
        pattern = f"{stage}_*.parquet"
        files = sorted(self.base_dir.glob(pattern))
        if not files:
            return None
        return self.load_artifact(files[-1])

    def list_artifacts(self, stage: str | None = None) -> list[DataArtifact]:
        """列出所有制品（可选按阶段过滤）"""
        pattern = f"{stage}_*.parquet" if stage else "*.parquet"
        artifacts = []
        for parquet_path in sorted(self.base_dir.glob(pattern)):
            meta_path = parquet_path.with_suffix(".meta.json")
            if meta_path.exists():
                artifacts.append(DataArtifact.load_meta(meta_path))
            else:
                artifacts.append(DataArtifact(
                    artifact_id="unknown",
                    file_path=parquet_path,
                ))
        return artifacts

    def extend_lineage(self, parent: DataArtifact, new_stage: str) -> list[str]:
        """基于父制品扩展血缘链"""
        return parent.lineage + [new_stage]
