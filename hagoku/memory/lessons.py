"""② Agent 能力成长记忆 — lessons.jsonl append-only."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LESSON_RECALL_WARNING = (
    "这些是历史参考，请用 conditions_to_recheck 验证适用性；参考用不是结论。"
)

_LESSONS_PATH = Path(__file__).resolve().parent / "lessons.jsonl"


@dataclass
class Lesson:
    id: str
    timestamp: str
    project_id: str
    scenario: str
    what_worked: str
    what_failed: str
    lesson: str
    conditions_to_recheck: list[str] = field(default_factory=list)
    confidence: str = "medium"
    user_validated: bool = False
    superseded_by: str | None = None


class LessonStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or _LESSONS_PATH

    def save(
        self,
        *,
        scenario: str,
        what_worked: str,
        what_failed: str,
        lesson: str,
        conditions_to_recheck: list[str] | None = None,
        confidence: str = "medium",
        project_id: str = "",
    ) -> str:
        wf = (what_failed or "").strip()
        if not wf:
            raise ValueError("what_failed 不能为空；无失败经验请传 'none'")
        entry = Lesson(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            project_id=project_id,
            scenario=scenario.strip(),
            what_worked=what_worked.strip(),
            what_failed=wf,
            lesson=lesson.strip(),
            conditions_to_recheck=list(conditions_to_recheck or []),
            confidence=confidence,
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")
        return entry.id

    def recall(self, context_query: str, top_k: int = 3) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        q = context_query.lower()
        tokens = [t for t in q.split() if len(t) > 1]
        scored: list[tuple[int, dict[str, Any]]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith('{"_schema"'):
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("superseded_by"):
                continue
            blob = " ".join(
                str(row.get(k, "")) for k in ("scenario", "lesson", "what_worked", "what_failed")
            ).lower()
            score = sum(1 for t in tokens if t in blob) if tokens else 0
            if score > 0 or not tokens:
                scored.append((score, row))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored[:top_k]]

    def correct(self, lesson_id: str, new_lesson: str | None, reason: str) -> None:
        if not self.path.exists():
            raise ValueError(f"lesson {lesson_id} 不存在")
        lines: list[str] = []
        found = False
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.strip().startswith('{"_schema"'):
                lines.append(line)
                continue
            row = json.loads(line)
            if row.get("id") != lesson_id:
                lines.append(line)
                continue
            found = True
            if new_lesson is None:
                row["superseded_by"] = "deprecated"
            else:
                row["lesson"] = new_lesson
            row["correct_reason"] = reason
            lines.append(json.dumps(row, ensure_ascii=False))
        if not found:
            raise ValueError(f"lesson {lesson_id} 不存在")
        self.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
