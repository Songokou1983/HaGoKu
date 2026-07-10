"""Pipeline 辅助（护栏、取消、指令处理）。CH-5 从 orchestrator.py 拆分。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from ...observability.events import EventType

def _check_mandatory_guardrails(self, results: list[dict[str, Any]]) -> tuple[list[dict], str]:
    """逐条检查 Analyst 结果，收集所有未通过的强制级护栏。

    与旧版 _mandatory_guardrails_block_report 的区别：
    这里只收集违规详情，不做"阻断/跳过 Reporter"的硬编码决策。
    护栏失败本质是统计问题，应由 LLM 分析原因并向用户解释风险，
    让用户选择处理方式（加警告继续/修正/跳过）。

    Returns:
        (violations, report_md) — violations 列表，每个元素包含
        {result_index, label, guardrail_results}；report_md 为违规详情
        Markdown（用于交给 LLM 分析和展示给用户）。
    """
    if not results:
        return [], ""
    violations: list[dict] = []
    sections: list[str] = []
    for i, result in enumerate(results):
        grs = self.guardrails.check(result)
        if self.guardrails.can_output(grs):
            continue
        label = str(result.get("question") or result.get("result_id") or f"结果 {i + 1}")
        violations.append({
            "result_index": i,
            "label": label,
            "guardrail_results": grs,
            "result": result,
        })
        sections.append(f"## {label}\n\n{self.guardrails.format_report(grs)}")
    if not violations:
        return [], ""
    header = (
        "# 统计护栏：强制级未通过\n\n"
        "以下分析结果未通过强制级统计护栏。**由 LLM 分析原因并向用户解释风险**，"
        "让用户选择处理方式（加警告继续 / 修正后重跑 / 跳过本次分析）。\n\n"
        "---\n\n"
    )
    return violations, header + "\n\n---\n\n".join(sections)

def _handle_mandatory_violations(
    self,
    violations: list[dict],
    results: list[dict[str, Any]],
    run_dir: Path,
) -> dict | None:
    """护栏违规后交给 LLM 解释风险，等待用户决策。

    护栏失败本质是统计问题（如无检验就下结论、多重比较未校正），
    应该由 LLM 分析违规原因并向用户解释风险，让用户选择：
    1) 加警告继续 — Reporter 正常生成，但报告中标注统计风险
    2) 修正后重跑 — 返回 Analyst 重新分析
    3) 跳过本次分析 — 仅输出护栏报告

    此方法是非阻塞的交互方法，会把 LLM 风险分析和用户决策也
    写入审计链路。

    Returns:
        None 若用户选择继续（调用方继续走 Reporter 流程）；
        或 dict(status="guardrails_blocked" 或 "guardrails_retry")。
    """
    import logging

    logger = logging.getLogger(__name__)

    # 无违规 → 直接返回 None，继续正常流程
    if not violations:
        return None

    # 1) 构建违规摘要让 LLM 分析
    violation_summary_parts = []
    for v in violations:
        r = v["result"]
        analysis_type = r.get("analysis_type", "")
        conclusion = r.get("conclusion_plain", "")
        p_value = r.get("p_value")
        effect_size = r.get("effect_size")
        violation_summary_parts.append(
            f"### {v['label']}\n"
            f"- 分析类型: {analysis_type}\n"
            f"- 问题: {r.get('question', '')}\n"
            f"- 结论: {conclusion}\n"
            f"- p 值: {p_value}\n"
            f"- 效应量: {effect_size}\n"
            f"- 护栏违规:\n{self.guardrails.format_report(v['guardrail_results'])}\n"
        )
    violation_summary = "\n\n---\n\n".join(violation_summary_parts)

    risk_prompt = (
        "你是一名统计专家。以下分析结果未通过强制级统计护栏。"
        "请用非技术语言向用户解释每个违规项的风险（如：结论可能不可靠、"
        "可能受混淆因素影响、多重比较未校正等）。\n\n"
        "对于每个违规项，给出你的建议：\n"
        "- 风险是否可接受（可以加警告后展示）\n"
        "- 是否需要修正重跑\n"
        "- 影响程度（高/中/低）\n\n"
        f"{violation_summary}"
    )

    try:
        from ...llm.client import create_raw_client

        llm_config = self.config.llm
        client = create_raw_client(llm_config)
        response = client.chat.completions.create(
            model=llm_config.model,
            # EXEMPT: 辅助 LLM — 护栏风险分析，非主对话通道
            messages=build_messages(
                query=risk_prompt,
                user_input=risk_prompt,
                system_extra="你是数据统计专家，用清晰易懂的中文解释统计风险。",
            ),
            temperature=0.0,
            max_tokens=1024,
        )
        risk_analysis = response.choices[0].message.content or ""
    # 豁免铁律 7：risk_analysis 是增值段，核心护栏报告（violation_summary）是代码产出的事实数据，不依赖 LLM
    except Exception as e:
        logger.warning(f"LLM 风险分析失败，使用默认护栏报告: {e}")
        risk_analysis = (
            "无法生成风险分析（LLM 调用失败）。请人工审核以下护栏违规详情。\n\n"
            f"{violation_summary}"
        )

    # 2) 生成完整护栏报告交给用户决策
    guardrail_report = (
        "# ⚠️ 统计护栏未通过 — 需要你的决策\n\n"
        "> 护栏失败本质是**统计问题**，不是代码 bug。"
        "以下分析结果存在统计方法风险，已在下方解释。\n\n"
        "---\n\n"
        "## 🤖 LLM 风险分析\n\n"
        f"{risk_analysis}\n\n"
        "---\n\n"
        "## 📋 违规详情\n\n"
        f"{violation_summary}\n\n"
        "---\n\n"
        "## 你的选择\n\n"
        "1. **加警告继续** — Reporter 正常生成 HTML 报告，报告中标注统计风险\n"
        "2. **修正后重跑** — 返回分析师重新分析（需指定修正项）\n"
        "3. **跳过** — 仅输出本护栏报告，不生成正式报告\n\n"
        "请回复数字 1 / 2 / 3，或直接说出你的想法。"
    )

    notice_path = run_dir / "output" / "GUARDRAILS_REVIEW.md"
    notice_path.parent.mkdir(parents=True, exist_ok=True)
    notice_path.write_text(guardrail_report, encoding="utf-8")

    self.event_bus.emit(EventType.QUALITY_CHECK, "manager", {
        "verdict": "mandatory_violations",
        "detail": f"强制级护栏未通过 {len(violations)} 项，已交 LLM 分析并等待用户决策",
        "report_path": str(notice_path),
    })

    return {
        "violations": violations,
        "risk_analysis": risk_analysis,
        "report_path": str(notice_path),
        "pending_decision": True,
    }

def _finish_run_cancelled(
    self,
    run_id: str,
    project_name: str,
    run_start: datetime,
    run_dir: Path,
) -> dict[str, Any]:
    duration_ms = int((datetime.now() - run_start).total_seconds() * 1000)
    now = datetime.now().isoformat()
    self.db.update_run(
        run_id,
        status="cancelled",
        completed_at=now,
        duration_ms=duration_ms,
    )
    self.event_bus.emit(EventType.AGENT_THINKING, "manager", {
        "thought": "分析已由用户中止。",
    })
    self.event_bus.emit(EventType.RUN_COMPLETED, "manager", {
        "duration": f"{duration_ms / 1000:.1f}s",
        "cancelled": True,
        "run_id": run_id,
        "project": project_name,
    })
    try:
        events_path = run_dir / "events.jsonl"
        self.event_bus.save_to_file(events_path)
    except Exception:
        pass
    return {
        "status": "cancelled",
        "message": "分析已中止",
        "run_id": run_id,
        "project": project_name,
        "duration_ms": duration_ms,
    }


    self,
    agent: str,
    payload: dict[str, Any],
    **kwargs: Any,
) -> dict[str, Any]:
    """不在暂停点注入任何固定/模型生成台词；仅保证 `message` 键存在（与结构化卡片分工）。"""
    del agent, kwargs  # API 兼容旧调用点，不再使用
    out = dict(payload)
    if "message" not in out or out.get("message") is None:
        out["message"] = ""
    return out


class PipelineHelpersMixin:
    """Mixin：pipeline_helpers 模块级函数注册为 Orchestrator 的方法。"""
    _check_mandatory_guardrails = _check_mandatory_guardrails
    _handle_mandatory_violations = _handle_mandatory_violations
    _finish_run_cancelled = _finish_run_cancelled
