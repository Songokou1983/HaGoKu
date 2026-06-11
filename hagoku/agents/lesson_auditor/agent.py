"""LessonAuditor — ② 层成长记忆质量审计 Agent（Phase E CO-M3.1）

用 Meta LLM 审 lessons.jsonl：重复检测、矛盾识别、低质量标记、趋势月报。
只输出建议，不修改 lesson 内容（brief §3.4）。
"""

from __future__ import annotations

import json as _json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hagoku.llm.client import create_meta_client
from hagoku.channel import build_messages
from hagoku.memory.lessons import LESSON_RECALL_WARNING, LessonStore

logger = logging.getLogger("hagoku.lesson_auditor")

AUDIT_DIR = Path.home() / ".hagoku" / "audits"
_LESSONS_PATH = Path(__file__).resolve().parent.parent.parent / "memory" / "lessons.jsonl"


@dataclass
class LessonAuditReport:
    report_type: str  # "quality" / "monthly"
    timestamp: str
    total_lessons: int
    duplicates: list[dict[str, Any]] = field(default_factory=list)
    contradictions: list[dict[str, Any]] = field(default_factory=list)
    low_confidence: list[dict[str, Any]] = field(default_factory=list)
    trend_summary: str = ""


class LessonAuditor:
    """② 层审计 Agent。不修改 lesson，只生成 audit 建议。"""

    def __init__(self) -> None:
        self.store = LessonStore()
        self._prompt_path = Path(__file__).parent / "prompt.md"

    @property
    def prompt(self) -> str:
        if self._prompt_path.exists():
            return self._prompt_path.read_text(encoding="utf-8")
        return ""

    def _load_lessons(self) -> list[dict]:
        if not _LESSONS_PATH.exists():
            return []
        lessons = []
        for line in _LESSONS_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith('{"_schema"'):
                continue
            try:
                lessons.append(_json.loads(line))
            except _json.JSONDecodeError:
                pass
        return lessons

    def review_batch(self, lesson_ids: list[str] | None = None) -> LessonAuditReport:
        lessons = self._load_lessons()
        if lesson_ids:
            lessons = [l for l in lessons if l.get("id") in lesson_ids]
        report = LessonAuditReport(
            report_type="quality",
            timestamp=datetime.now(timezone.utc).isoformat(),
            total_lessons=len(lessons),
        )
        report.duplicates = self._compute_duplicates(lessons)
        report.contradictions = self._compute_contradictions(lessons)
        report.low_confidence = [
            l for l in lessons
            if l.get("confidence") == "high" and l.get("what_failed") in ("none", "", None)
        ]
        return report

    def monthly_report(self) -> LessonAuditReport:
        lessons = self._load_lessons()
        now = datetime.now(timezone.utc)
        month_ago = now.replace(day=1).isoformat()[:7]
        recent = [l for l in lessons if l.get("timestamp", "")[:7] >= month_ago]
        report = self.review_batch()
        report.report_type = "monthly"
        report.trend_summary = f"本月新增 {len(recent)} 条 lesson，总 {len(lessons)} 条"
        # LLM 审核（可选，meta_llm 不可用时跳过）
        try:
            report.trend_summary = self._llm_audit(recent, lessons) or report.trend_summary
        except Exception as e:
            logger.warning("LLM audit skipped: %s", e)
        return report

    def _llm_audit(self, recent: list[dict], all_lessons: list[dict]) -> str | None:
        prompt = self.prompt
        if not prompt:
            return None
        from hagoku.config import HaGoKuConfig
        cfg = HaGoKuConfig.load()
        client = create_meta_client(cfg)
        if client is None:
            raise RuntimeError("LessonAuditor: Meta LLM 不可达，请配置 meta_llm")
        payload = {
            "recent": recent[:20],
            "total_count": len(all_lessons),
            "duplicates": len(self._compute_duplicates(all_lessons)),
        }
        messages = build_messages(
            query="lesson audit",
            user_input=_json.dumps(payload, ensure_ascii=False, default=str),
            system_extra=prompt,
        )
        model = cfg.meta_llm.model or cfg.llm.model
        resp = client.chat.completions.create(
            model=model, messages=messages, temperature=0.0, max_tokens=1024,
        )
        return (resp.choices[0].message.content or "").strip()

    def _compute_duplicates(self, lessons: list[dict]) -> list[dict]:
        seen: dict[tuple, list[dict]] = {}
        for l in lessons:
            key = (l.get("scenario", "").strip().lower(), l.get("lesson", "").strip().lower())
            seen.setdefault(key, []).append(l)
        return [{"key": k, "count": len(v), "ids": [x["id"] for x in v]} for k, v in seen.items() if len(v) > 1]

    def _compute_contradictions(self, lessons: list[dict]) -> list[dict]:
        conflicts = []
        for i, a in enumerate(lessons):
            for b in lessons[i + 1:]:
                if a.get("scenario") == b.get("scenario"):
                    wa = a.get("what_worked", "").strip()
                    wb = b.get("what_worked", "").strip()
                    if wa and wb and wa != wb:
                        conflicts.append({"a_id": a["id"], "b_id": b["id"], "scenario": a["scenario"], "a_worked": wa, "b_worked": wb})
        return conflicts[:20]

    def write_report(self, report: LessonAuditReport) -> Path:
        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        ts = report.timestamp[:19].replace(":", "").replace("-", "")
        filename = f"lesson_audit_{ts}.md" if report.report_type == "quality" else f"monthly_trend_{report.timestamp[:7]}.md"
        path = AUDIT_DIR / filename
        lines = [
            f"# Lesson Audit — {report.report_type}",
            f"Time: {report.timestamp[:19]}",
            f"Total lessons: {report.total_lessons}",
            "",
        ]
        if report.duplicates:
            lines.append("## Duplicates")
            for d in report.duplicates:
                lines.append(f"- {d['key']}: {d['count']} 条 (ids: {d['ids'][:3]})")
        if report.contradictions:
            lines.append("## Contradictions")
            for c in report.contradictions:
                lines.append(f"- [{c['a_id']}] {c['a_worked']} vs [{c['b_id']}] {c['b_worked']} (scenario: {c['scenario']})")
        if report.low_confidence:
            lines.append("## Low Confidence")
            for lc in report.low_confidence[:10]:
                lines.append(f"- {lc.get('id','?')}: {lc.get('scenario','')}")
        if report.trend_summary:
            lines.append(f"\n## Trend\n{report.trend_summary}")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path


# ── 触发器 ──

def on_lesson_written(lesson_count: int) -> None:
    """每写入 10 条 lesson 自动触发一次质量审。"""
    if lesson_count % 10 == 0:
        auditor = LessonAuditor()
        report = auditor.review_batch()
        path = auditor.write_report(report)
        logger.info("Auto audit: %s (%d lessons)", path, report.total_lessons)


def run_monthly_audit() -> Path:
    auditor = LessonAuditor()
    report = auditor.monthly_report()
    return auditor.write_report(report)


def run_ad_hoc_audit() -> Path:
    auditor = LessonAuditor()
    report = auditor.review_batch()
    return auditor.write_report(report)
