"""互动场景夹具：结构与契约一致（可执行剧本）。"""

from __future__ import annotations

from pathlib import Path

from hagoku.devtools.interaction_scenarios import (
    iter_scenario_files,
    load_scenario,
    validate_scenario_document,
)


def test_all_fixture_scenarios_validate() -> None:
    files = iter_scenario_files()
    assert files, "expected at least one JSON under tests/fixtures/interaction_scenarios/"
    for path in files:
        doc = load_scenario(path)
        errs = validate_scenario_document(doc, source=str(path))
        assert not errs, "\n".join(errs)


def test_full_web_pause_flow_fixture_exists() -> None:
    root = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "interaction_scenarios"
    p = root / "full_web_pause_flow.json"
    assert p.is_file()
    doc = load_scenario(p)
    assert doc.get("id") == "full_web_pause_flow"
    steps = doc.get("steps", [])
    assert isinstance(steps, list) and len(steps) >= 8
