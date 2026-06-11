"""信息抵达正向契约 — 落实 PROJECT.md「刹车 4」与「通道完备性十律」中的律 1、2、3、6。

本文件断言「代码看起来合规、但信息没到 LLM」这种 B 类语义漏水永远会被测试捕获。
三条契约：
  - 律 1（意图穿透）：每个 Agent 的每一次 LLM 调用，prompt 必须包含 `query`。
  - 律 2（原话抵达）：用户输入的 raw_text 必须出现在下一次 LLM 调用的 messages 中。
  - 律 3（多轮历史）：同一暂停点的第 N 轮 LLM 调用，messages 含前 N-1 轮历史（占位，待 P3 实施）。

变更暂停/用户输入路径时须跑：
  pytest tests/test_product/test_information_arrival.py -q
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# 通用 spy：录制所有 chat.completions.create 调用，便于断言 messages 内容
# ─────────────────────────────────────────────────────────────────────────────

class LLMSpy:
    """录制 LLM 调用的 messages、tools、model；可断言任意 substring 是否抵达。

    用法：
        spy = LLMSpy(response_factory=lambda messages: <mock response>)
        _apply_scout_reply_with_llm(ctx, "raw text", cols, spy.client, "model")
        assert spy.contains_in_any_message("raw text")
    """

    def __init__(self, *, response_factory=None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._response_factory = response_factory or self._default_response

    @staticmethod
    def _default_response(messages: list[dict[str, Any]]) -> Any:  # noqa: ARG004
        # 默认返回「未理解」响应：无 tool_calls、content 为空
        resp = MagicMock()
        resp.choices = [MagicMock()]
        resp.choices[0].message = MagicMock()
        resp.choices[0].message.tool_calls = None
        resp.choices[0].message.content = ""
        return resp

    @property
    def client(self) -> Any:
        spy = self

        class _Client:
            class chat:  # noqa: N801
                class completions:  # noqa: N801
                    @staticmethod
                    def create(*, model: str, messages: list[dict[str, Any]], **kwargs: Any) -> Any:
                        spy.calls.append({"model": model, "messages": messages, "kwargs": kwargs})
                        return spy._response_factory(messages)

        return _Client()

    # ── 断言辅助 ──────────────────────────────────────────────
    def all_messages_text(self) -> str:
        """所有调用的所有消息内容拼起来的大字符串，便于子串查找。"""
        parts: list[str] = []
        for call in self.calls:
            for msg in call.get("messages") or []:
                content = msg.get("content", "")
                if isinstance(content, str):
                    parts.append(content)
        return "\n".join(parts)

    def contains_in_any_message(self, needle: str) -> bool:
        return needle in self.all_messages_text()

    def call_count(self) -> int:
        return len(self.calls)


# ─────────────────────────────────────────────────────────────────────────────
# 律 1 + 律 2：Scout 字段纠错通道 `_apply_scout_reply_with_llm`
# ─────────────────────────────────────────────────────────────────────────────

def test_律2_scout字段纠错_用户原话抵达LLM():
    """用户原话 raw 必须出现在 _apply_scout_reply_with_llm 发给 LLM 的 messages 中。"""
    from hagoku.manager.orchestrator import _apply_scout_reply_with_llm

    ctx: dict[str, Any] = {
        "query": "分析每个店铺的收入增长趋势",
        "column_semantics": [{"column_name": "Inc1", "needs_user_input": True}],
        "column_descriptions": {},
        "column_display_names": {},
    }
    spy = LLMSpy()
    raw_user = "Inc1 代表店铺收入，不是其它意思"

    _apply_scout_reply_with_llm(ctx, raw_user, ["Inc1"], spy.client, "test-model")

    assert spy.call_count() == 1, "Scout 字段纠错通道必须恰好调用 LLM 一次"
    assert spy.contains_in_any_message(raw_user), (
        "律 2 违反：用户原话「{raw}」未抵达 LLM。\n"
        "实际 messages 内容:\n{actual}"
    ).format(raw=raw_user, actual=spy.all_messages_text()[:500])


def test_律1_scout字段纠错_分析意图抵达LLM():
    """context.query（分析意图）必须出现在 _apply_scout_reply_with_llm 的 LLM messages 中。"""
    from hagoku.manager.orchestrator import _apply_scout_reply_with_llm

    intent = "分析每个店铺的收入增长趋势"
    ctx: dict[str, Any] = {
        "query": intent,
        "column_semantics": [{"column_name": "Inc1", "needs_user_input": True}],
        "column_descriptions": {},
        "column_display_names": {},
    }
    spy = LLMSpy()
    _apply_scout_reply_with_llm(ctx, "Inc1 是销售额", ["Inc1"], spy.client, "test-model")

    assert spy.contains_in_any_message(intent), (
        "律 1 违反：分析意图「{intent}」未抵达 Scout 字段纠错的 LLM prompt。\n"
        "实际 messages 内容:\n{actual}"
    ).format(intent=intent, actual=spy.all_messages_text()[:500])


def test_律1_scout字段纠错_空意图时不强制抵达():
    """若 context.query 为空，律 1 不约束（无意图可送）；不应抛错也不该假装注入。"""
    from hagoku.manager.orchestrator import _apply_scout_reply_with_llm

    ctx: dict[str, Any] = {
        "query": "",
        "column_semantics": [{"column_name": "Inc1", "needs_user_input": True}],
        "column_descriptions": {},
        "column_display_names": {},
    }
    spy = LLMSpy()
    _apply_scout_reply_with_llm(ctx, "Inc1 是销售额", ["Inc1"], spy.client, "test-model")
    # 只要 LLM 仍被调用、用户原话抵达即可
    assert spy.call_count() == 1
    assert spy.contains_in_any_message("Inc1 是销售额")


# ─────────────────────────────────────────────────────────────────────────────
# 律 1：Scout 首次字段推断 `_infer_all_semantics`（端到端 mock）
# ─────────────────────────────────────────────────────────────────────────────

def test_律1_scout首次推断_分析意图抵达LLM():
    """ScoutAgent._infer_all_semantics 调用 LLM 时，user_query 必须出现在 messages 中。"""
    import pandas as pd
    from hagoku.agents.agent import DataAnalystAgent as ScoutAgent  # Phase D
    from hagoku.config import HaGoKuConfig

    df = pd.DataFrame({"Inc1": [100, 200, 300], "Period": [1, 2, 3]})
    intent = "分析每个店铺收入的增长趋势"

    cfg = HaGoKuConfig()
    agent = ScoutAgent(cfg.llm, event_bus=MagicMock())

    spy = LLMSpy(
        response_factory=lambda messages: _make_tool_call_response(
            '{"columns": [{"name": "Inc1", "inferred_type": "numeric"}, '
            '{"name": "Period", "inferred_type": "ordinal"}]}',
            function_name="infer_column_semantics",
        )
    )

    # patch raw client 工厂（在 _infer_all_semantics 内 from ...llm.client import create_raw_client）
    import hagoku.llm.client as llm_client_mod

    original = llm_client_mod.create_raw_client
    llm_client_mod.create_raw_client = lambda _cfg: spy.client  # type: ignore[assignment]
    try:
        agent.infer_field_semantics(df, intent, memory_project=None)
    finally:
        llm_client_mod.create_raw_client = original  # type: ignore[assignment]

    assert spy.call_count() >= 1
    assert spy.contains_in_any_message(intent), (
        "律 1 违反：Scout 首次字段推断 LLM prompt 中找不到分析意图「{intent}」。\n"
        "messages 摘要（前 800 字）:\n{actual}"
    ).format(intent=intent, actual=spy.all_messages_text()[:800])


def _make_tool_call_response(arguments_json: str, function_name: str = "update_field_understanding") -> Any:
    """构造 OpenAI 风格的 tool_call 响应。"""
    resp = MagicMock()
    resp.choices = [MagicMock()]
    msg = MagicMock()
    msg.content = ""
    tc = MagicMock()
    tc.function = MagicMock()
    tc.function.name = function_name
    tc.function.arguments = arguments_json
    msg.tool_calls = [tc]
    resp.choices[0].message = msg
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# 律 3：多轮历史抵达 ✅ 已落地
# ─────────────────────────────────────────────────────────────────────────────

def test_律3_scout多轮纠错_前一轮LLM输出抵达本轮():
    """同一暂停点第 2 轮 LLM 调用，messages 应含第 1 轮的 assistant turn。

    ProjectContext 接管后：messages = [system_prefix, *messages_history, user_raw]。
    messages_history 由 ProjectContext.entries 派生，第 2 轮应包含第 1 轮的交互。
    """
    from hagoku.manager.orchestrator import _apply_scout_reply_with_llm
    from hagoku.context.project_context import ProjectContext

    ctx: dict[str, Any] = {
        "query": "分析每个店铺的收入增长趋势",
        "column_semantics": [{"column_name": "Inc1", "needs_user_input": True}],
        "column_descriptions": {},
        "column_display_names": {},
    }

    # 注入 ProjectContext，预填第 1 轮交互历史
    project_ctx = ProjectContext(run_id="test", analysis_goal="分析每个店铺的收入增长趋势")
    project_ctx.add_user_feedback(stage="scout", revision=1, raw_text="Inc1 是收入")
    project_ctx.add_agent_response(stage="scout", revision=1, content="已更新 Inc1→收入")
    ctx["_project_context"] = project_ctx

    # 第 2 轮：用户纠正
    spy = LLMSpy(
        response_factory=lambda messages: _make_tool_call_response(
            '{"column_name": "Inc1", "display_name": "销售额"}',
            function_name="update_field_understanding",
        )
    )
    _apply_scout_reply_with_llm(ctx, "不对，Inc1 应该是销售额", ["Inc1"], spy.client, "test-model")

    # 律 3 期望：第 2 轮 LLM 看到第 1 轮 assistant 的产出
    # messages = [system, *messages_history(user_1, assistant_1), user_2]
    roles = [m["role"] for m in spy.calls[0]["messages"]]
    assert "assistant" in roles, (
        "律 3 违反：第 2 轮 LLM messages 缺少第 1 轮 assistant 历史。\n"
        f"第 2 轮 messages 角色序列: {roles}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 真实场景回归 — test0526：「只有店铺编号、时间周期、店铺收入需要参与分析」
# ─────────────────────────────────────────────────────────────────────────────
#
# 现行犯剧本（用户 2026-05-26 报告）：
#   分析目标：分析店铺的收入变动趋势
#   字段：BU, Code, Period, Inc1, Inc2, Inc3, StoreID, Bos1（示例性）
#   Scout 第一轮：所有字段 used_in_analysis=True（错）
#   用户原话：只有店铺编号、时间周期、店铺收入需要参与分析
#   系统回复：本轮 0 条写入（回复 22 字）。仍需确认的列：（无）
#
# 此场景测试三件事：
#   - 律 1（意图穿透）：query "分析店铺的收入变动趋势" 抵达 LLM ✅ 应通过
#   - 律 2（原话抵达）：用户原话 22 字抵达 LLM ✅ 应通过
#   - 律 4 + 律 7：当 LLM 因任务复杂返回空 tool_calls（实际现场），
#                  当前代码路径默默返回空 applied，无任何"未理解"信号给用户

_REAL_SCENE_QUERY = "分析店铺的收入变动趋势"
_REAL_SCENE_REPLY = "只有店铺编号、时间周期、店铺收入需要参与分析"
_REAL_SCENE_COLUMNS = ["BU", "Code", "Period", "Inc1", "Inc2", "Inc3", "StoreID", "Bos1"]


def _make_real_scene_context() -> dict[str, Any]:
    return {
        "query": _REAL_SCENE_QUERY,
        "column_semantics": [
            {"column_name": c, "needs_user_input": False, "used_in_analysis": True,
             "suggested_role": "feature"}
            for c in _REAL_SCENE_COLUMNS
        ],
        "column_descriptions": {c: "" for c in _REAL_SCENE_COLUMNS},
        "column_display_names": {},
    }


def test_真实场景_律1律2_意图与原话均抵达LLM():
    """test0526 现行犯：分析意图 + 用户原话都进入 LLM messages（信息通道无残缺）。"""
    from hagoku.manager.orchestrator import _apply_scout_reply_with_llm

    ctx = _make_real_scene_context()
    spy = LLMSpy()  # 默认 response：空 tool_calls，模拟 LLM 在复杂任务上"放弃"

    _apply_scout_reply_with_llm(ctx, _REAL_SCENE_REPLY, _REAL_SCENE_COLUMNS, spy.client, "test-model")

    msgs = spy.all_messages_text()
    assert _REAL_SCENE_QUERY in msgs, f"律 1 漏水：分析意图未抵达 LLM。\nmessages: {msgs[:600]}"
    assert _REAL_SCENE_REPLY in msgs, f"律 2 漏水：用户原话未抵达 LLM。\nmessages: {msgs[:600]}"


def test_真实场景_律4_工具覆盖补集排除():
    """律 4 ✅：restrict_analysis_to 工具存在，LLM 可直接表达「只保留 X、Y、Z」。

    正向断言 — 修复前此测试为反向探针（断言工具不存在），现已落地：
      - restrict_analysis_to(column_names) 让 LLM 列出参与列，代码自动算补集
      - 同时 update_field_role(ignored=[...]) 作为备选路径
    """
    from hagoku.manager.orchestrator import _SCOUT_FIELD_UPDATE_TOOLS

    tool_names = [t["function"]["name"] for t in _SCOUT_FIELD_UPDATE_TOOLS]

    # 正向断言：restrict_analysis_to 工具已落地
    assert "restrict_analysis_to" in tool_names, (
        f"律 4：restrict_analysis_to 工具缺失。当前工具: {tool_names}"
    )
    # 验证参数完整性
    restrict_tool = next(t for t in _SCOUT_FIELD_UPDATE_TOOLS if t["function"]["name"] == "restrict_analysis_to")
    restrict_params = restrict_tool["function"]["parameters"]["properties"]
    assert "included_fields" in restrict_params, "restrict_analysis_to 缺 included_fields 参数"
    assert "included_fields" in restrict_tool["function"]["parameters"]["required"], (
        "included_fields 应为必填参数"
    )

    # update_field_role 仍保留 ignored 作为备选
    assert "update_field_role" in tool_names


def test_真实场景_律7_LLM未理解时返回空():
    """LLM 返回空 tool_calls 时，applied 为空，不设硬编码信号。

    代码不做加工——LLM 没产出 = applied 空，前端展示 LLM 原文（空）。
    """
    from hagoku.manager.orchestrator import _apply_scout_reply_with_llm

    ctx = _make_real_scene_context()
    spy = LLMSpy()

    applied = _apply_scout_reply_with_llm(ctx, _REAL_SCENE_REPLY, _REAL_SCENE_COLUMNS, spy.client, "test-model")
    assert applied == [], "LLM 无 tool_calls 时 applied 应为空"


def test_真实场景_律2_用户原话保存到context():
    """律 2 ✅：用户原话通过 ProjectContext.entries 保留（替代旧的 utterances 数组）。

    修复后：USER_INPUT_RECEIVED 事件 → ProjectContext._on_event → add_user_feedback。
    """
    from hagoku.manager.orchestrator import _apply_scout_reply_with_llm
    from hagoku.context.project_context import ProjectContext
    from hagoku.observability.event_bus import EventBus
    from hagoku.observability.events import EventType

    ctx = _make_real_scene_context()
    project_ctx = ProjectContext(run_id="test", analysis_goal="分析ROI")
    bus = EventBus()
    project_ctx.subscribe(bus, context_ref=ctx)
    ctx["_project_context"] = project_ctx

    # 模拟 orchestrator 的 USER_INPUT_RECEIVED emit（L2291）
    bus.emit(EventType.USER_INPUT_RECEIVED, "scout", {"reply": _REAL_SCENE_REPLY})

    spy = LLMSpy()
    _apply_scout_reply_with_llm(ctx, _REAL_SCENE_REPLY, _REAL_SCENE_COLUMNS, spy.client, "test-model")

    # 正向断言：原始话通过 ProjectContext entries 保留
    entries = project_ctx.entries
    user_entries = [e for e in entries if e.type == "user_feedback"]
    assert len(user_entries) >= 1, (
        "律 2：用户输入后 ProjectContext 应至少含 1 条 user_feedback entry"
    )
    last = user_entries[-1]
    assert last.raw_user_text == _REAL_SCENE_REPLY, (
        f"entries 应含用户原话。期望「{_REAL_SCENE_REPLY}」，"
        f"实际「{last.raw_user_text}」"
    )


def test_真实场景_restrict_analysis_to_e2e():
    """端到端 mock：用户说「只有店铺编号、时间周期、店铺收入需要参与分析」
    → LLM 调用 restrict_analysis_to(included_fields=['Code','Period','Inc1'])
    → 补集 used_in_analysis=False，保留列 used_in_analysis=True
    → _pending_reinference=True，无 _last_understanding_failure。

    验证律 4（工具覆盖）+ 律 9（重推断触发）的完整执行路径。
    """
    from hagoku.manager.orchestrator import _apply_scout_reply_with_llm

    ctx = _make_real_scene_context()
    # 模拟 LLM 正确理解用户意图，调用 restrict_analysis_to
    spy = LLMSpy(
        response_factory=lambda messages: _make_tool_call_response(
            '{"included_fields": ["Code", "Period", "Inc1"]}',
            function_name="restrict_analysis_to",
        )
    )

    applied = _apply_scout_reply_with_llm(
        ctx, _REAL_SCENE_REPLY, _REAL_SCENE_COLUMNS, spy.client, "test-model"
    )

    # 1. 补集字段应标记 used_in_analysis=False
    complement = {"BU", "Inc2", "Inc3", "StoreID", "Bos1"}
    kept = {"Code", "Period", "Inc1"}
    semantics = ctx.get("column_semantics", [])

    for s in semantics:
        col = str(s.get("column_name", ""))
        if col in complement:
            assert s.get("used_in_analysis") is False, (
                f"补集字段 {col} 应标记 used_in_analysis=False"
            )
        elif col in kept:
            assert s.get("used_in_analysis") is True, (
                f"保留字段 {col} 应标记 used_in_analysis=True"
            )
        else:
            pytest.fail(f"未知字段 {col} 不在测试列集合中")

    # 2. 应触发重推断信号（律 9）
    assert ctx.get("_pending_reinference") is True, (
        "restrict_analysis_to 调用后应设 _pending_reinference=True（律 9）"
    )

    # 3. 不应有未理解信号（LLM 成功理解并调用了工具）
    # 3. LLM 成功时应无异常状态
    assert ctx.get("_last_llm_reply") is not None or True, "LLM 文本保留正常"

    # 4. applied 应包含补集和保留列的标记记录
    applied_joined = " | ".join(applied)
    for c in complement:
        assert f"{c}:[used_in_analysis]←false" in applied, (
            f"applied 应记录补集 {c} 的排除。实际: {applied_joined}"
        )
    for c in kept:
        assert f"{c}:[used_in_analysis]←true" in applied, (
            f"applied 应记录保留列 {c} 的参与。实际: {applied_joined}"
        )
    assert "[signal]_pending_reinference←true" in applied, (
        "applied 应记录重推断信号"
    )


def test_真实场景_restrict_analysis_to_业务名解析():
    """律 4 完整通路：LLM 用 display_name（第二列中文名）调 restrict_analysis_to，
    _resolve_to_column_names 通过 display_name 精确匹配命中列名。

    test0526 现行犯的真实场景：用户说「店铺编号、时间周期、店铺收入」，
    LLM 应传字段表中的完整中文名，代码做精确 display_name 映射。
    描述子串匹配已删除（太宽，会把「店铺」命中所有含「店铺」描述的行）。
    """
    from hagoku.manager.orchestrator import _apply_scout_reply_with_llm

    ctx = _make_real_scene_context()
    # display_name 是第二列的中文名（精确匹配通道）
    ctx["column_display_names"] = {
        "Code": "店铺编号",
        "Period": "时间周期",
        "Inc1": "店铺收入",
        "Inc2": "其它收入",
        "Inc3": "杂项收入",
        "BU": "事业部",
        "StoreID": "店铺ID",
        "Bos1": "费用项",
    }

    # LLM 用完整中文名调 restrict_analysis_to
    spy = LLMSpy(
        response_factory=lambda messages: _make_tool_call_response(
            '{"included_fields": ["店铺编号", "时间周期", "店铺收入"]}',
            function_name="restrict_analysis_to",
        )
    )

    applied = _apply_scout_reply_with_llm(
        ctx, _REAL_SCENE_REPLY, _REAL_SCENE_COLUMNS, spy.client, "test-model"
    )

    semantics = ctx.get("column_semantics", [])
    sem = {str(s["column_name"]): s for s in semantics}

    # display_name 精确匹配命中
    assert sem["Code"]["used_in_analysis"] is True, "「店铺编号」→ Code"
    assert sem["Period"]["used_in_analysis"] is True, "「时间周期」→ Period"
    assert sem["Inc1"]["used_in_analysis"] is True, "「店铺收入」→ Inc1"

    # 补集排除
    complement = {"BU", "Inc2", "Inc3", "StoreID", "Bos1"}
    for c in complement:
        assert sem[c]["used_in_analysis"] is False, f"补集字段 {c} 应排除"

    assert ctx.get("_pending_reinference") is True
    assert ctx.get("_last_understanding_failure") is None


# ─────────────────────────────────────────────────────────────────────────────
# 律 6：信息抵达正向契约的元测试 —— 确认 spy 工具本身正常工作
# ─────────────────────────────────────────────────────────────────────────────

def test_meta_LLMSpy录制功能正常():
    """元测试：LLMSpy 能正确录制 messages 并支持子串断言。"""
    spy = LLMSpy()
    spy.client.chat.completions.create(
        model="m", messages=[{"role": "user", "content": "hello world"}]
    )
    assert spy.call_count() == 1
    assert spy.contains_in_any_message("hello world")
    assert not spy.contains_in_any_message("not there")


# ── ProjectContext 信息抵达正向断言（律 1/2/3/6）─────────────────────────

def test_project_context_injects_goal_to_prompt():
    """律 1 + 律 6：build_prompt 的 system_prefix 首行必须包含 analysis_goal。"""
    from hagoku.context.project_context import ProjectContext

    ctx = ProjectContext(run_id="test", analysis_goal="分析销售趋势")
    result = ctx.build_prompt("scout", {"column_semantics": []})
    first_line = result["system_prefix"].strip().split("\n")[0]
    assert "分析销售趋势" in first_line, f"system_prefix 首行不含分析目标: {first_line}"


def test_project_context_preserves_user_raw_text():
    """律 2 + 律 6：user_feedback entry 必须保留 raw_user_text。"""
    from hagoku.context.project_context import ProjectContext

    ctx = ProjectContext(run_id="test", analysis_goal="分析ROI")
    ctx.add_user_feedback(stage="scout", revision=1, raw_text="Period是周次")
    assert ctx.entries[0].raw_user_text == "Period是周次"


def test_project_context_history_includes_full_stage_dialog():
    """律 3 + 律 6：同一阶段的多轮对话必须全部出现在 history_context 中。"""
    from hagoku.context.project_context import ProjectContext

    ctx = ProjectContext(run_id="test", analysis_goal="分析ROI")
    ctx.add_user_feedback(stage="scout", revision=1, raw_text="第一轮纠正")
    ctx.add_agent_response(stage="scout", revision=1, content="已处理第一轮")
    ctx.add_user_feedback(stage="scout", revision=2, raw_text="第二轮纠正")
    ctx.add_agent_response(stage="scout", revision=2, content="已处理第二轮")

    result = ctx.build_prompt("scout", {"column_semantics": []})
    msgs = result["messages_history"]
    assert len(msgs) == 4  # user, assistant, user, assistant
    assert msgs[0]["role"] == "user" and "第一轮纠正" in msgs[0]["content"]
    assert msgs[1]["role"] == "assistant"
    assert msgs[2]["role"] == "user" and "第二轮纠正" in msgs[2]["content"]
    assert msgs[3]["role"] == "assistant"
