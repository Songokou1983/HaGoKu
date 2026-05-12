# 与 hagoku_web/src/utils/wsGuardrails.ts 保持逻辑一致；任一修改请同步另一方。

from __future__ import annotations


def run_id_from_output_path(output_path: str | None) -> str | None:
    if not output_path:
        return None
    normalized = output_path.replace("\\", "/")
    marker = "/runs/"
    idx = normalized.rfind(marker)
    if idx == -1:
        return None
    rest = normalized[idx + len(marker) :]
    seg = rest.split("/")[0]
    return seg or None


def guardrails_run_completed_info(
    event_type: str,
    data: dict | None,
) -> tuple[bool, str | None]:
    inner = data or {}
    if event_type != "run_completed" or inner.get("guardrails_blocked") is not True:
        return False, None
    rid = inner.get("run_id")
    explicit = rid if isinstance(rid, str) else None
    op = inner.get("output_path")
    out = op if isinstance(op, str) else None
    run_id = explicit or run_id_from_output_path(out)
    return True, run_id


def is_reporter_skipped_completion(event_type: str, agent: str, data: dict | None) -> bool:
    if "report" not in agent.lower():
        return False
    if event_type != "agent_completed":
        return False
    inner = data or {}
    return inner.get("skipped") is True


class TestRunIdFromOutputPath:
    def test_posix(self):
        assert (
            run_id_from_output_path(
                "/home/u/.hagoku/projects/p1/runs/20260514_ab12/output/GUARDRAILS_BLOCKED.md",
            )
            == "20260514_ab12"
        )

    def test_windows_style(self):
        assert (
            run_id_from_output_path(
                r"C:\Users\u\.hagoku\projects\p1\runs\20260514_x\output\GUARDRAILS_BLOCKED.md",
            )
            == "20260514_x"
        )

    def test_missing(self):
        assert run_id_from_output_path(None) is None
        assert run_id_from_output_path("/data/output/report.html") is None


class TestGuardrailsRunCompletedInfo:
    def test_blocked_with_run_id(self):
        blocked, rid = guardrails_run_completed_info(
            "run_completed",
            {
                "guardrails_blocked": True,
                "run_id": "rid1",
                "project": "p1",
                "output_path": "/x.md",
            },
        )
        assert blocked and rid == "rid1"

    def test_fallback_output_path(self):
        blocked, rid = guardrails_run_completed_info(
            "run_completed",
            {
                "guardrails_blocked": True,
                "output_path": "/proj/runs/fallback_id/output/GUARDRAILS_BLOCKED.md",
            },
        )
        assert blocked and rid == "fallback_id"

    def test_normal_completion(self):
        blocked, _ = guardrails_run_completed_info(
            "run_completed",
            {"output_path": "/r.html", "run_id": "a"},
        )
        assert not blocked


class TestReporterSkipped:
    def test_true(self):
        assert is_reporter_skipped_completion(
            "agent_completed",
            "reporter",
            {"skipped": True},
        )

    def test_false(self):
        assert not is_reporter_skipped_completion("agent_completed", "reporter", {})
