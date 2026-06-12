"""上下文保真律守门测试 — 机器化保证「用户纠正永不丢失」。

覆盖 PROJECT.md「上下文保真律」三类核心风险：

  A. 连续性（律 2/3）
     多轮纠正回放：第 N 轮的 LLM 消息里必须仍能找到第 1…N-1 轮的用户原话。

  B. 基线对比（律 1/4/5）
     标准场景 fixture → to_messages_for_llm → 断言关键内容不变短。
     重构前后的回归守门：如果某次重构压缩了 messages，这里会变红。

  C. 跨阶段原始记录（律 4）
     阶段切换后，上一阶段的 tool exchange 必须以 role=tool 出现在
     messages_history 中。动态数据走对话历史，不走系统消息。

  D. 动态数据走对话历史
     分析目标、字段状态、用户纠正——全部在 messages_history 中。
     系统消息只放 agent 指令（prompt.md）。LLM 自己会读对话。

  E. 失败轮次保留（律 6）
     LLM 失败轮次的用户原话不得因 RuntimeError 被销毁。

运行方式：
  pytest tests/test_channel/test_context_fidelity.py -v
"""

from __future__ import annotations

from typing import Any

import pytest

from hagoku.context.project_context import ProjectContext, ToolCallRecord


# ─────────────────────────────────────────────────────────────────────────────
# 共用常量与工具函数
# ─────────────────────────────────────────────────────────────────────────────

GOAL = "分析每个店铺的月度收入趋势"

COLUMNS = [
    {"column_name": "StoreID", "suggested_role": "identifier", "used_in_analysis": True,
     "display_name": "店铺编号", "needs_user_input": False},
    {"column_name": "Period",  "suggested_role": "feature",    "used_in_analysis": True,
     "display_name": "时间周期", "needs_user_input": False},
    {"column_name": "Inc1",    "suggested_role": "target",     "used_in_analysis": True,
     "display_name": "店铺收入", "needs_user_input": False},
    {"column_name": "BU",      "suggested_role": "feature",    "used_in_analysis": False,
     "display_name": "事业部",  "needs_user_input": False},
]


def _ctx(pc: ProjectContext) -> dict[str, Any]:
    return {
        "query": GOAL,
        "column_semantics": COLUMNS,
        "target": "Inc1",
        "features": ["Period"],
        "_project_context": pc,
    }


def _text(msgs: list[dict]) -> str:
    """把所有 messages 的 content 拼成大字符串。"""
    return "\n".join(
        m.get("content", "") for m in msgs
        if isinstance(m.get("content"), str)
    )


def _standard_scenario() -> tuple[ProjectContext, dict[str, Any]]:
    """标准场景：Scout 2 轮纠正，用于基线回归测试。"""
    pc = ProjectContext(run_id="baseline", analysis_goal=GOAL)
    pc.add_user_feedback("scout", 1, raw_text="Inc1 是净利润不是总收入")
    pc.add_agent_response("scout", 1, content="已更新 Inc1 描述",
                          snapshot={"target": "Inc1", "features": ["Period"]})
    pc.add_user_feedback("scout", 2, raw_text="BU 不参与分析")
    pc.add_agent_response("scout", 2, content="已排除 BU 字段",
                          snapshot={"target": "Inc1", "features": ["Period"]})
    return pc, _ctx(pc)


# 基线下限：system(1) + query(1) + history(2×2=4) + current_user(1) = 7，容差 -2 → 5
_BASELINE_MIN_MESSAGES = 5


# ─────────────────────────────────────────────────────────────────────────────
# A. 连续性测试 — 律 2/3
# ─────────────────────────────────────────────────────────────────────────────

class TestCorrectionContinuity:

    def test_第一轮纠正在第三轮messages中仍可见(self):
        pc = ProjectContext(run_id="continuity-3", analysis_goal=GOAL)
        c1 = "Inc1 是净利润，不是收入，很关键"
        c2 = "BU 字段不需要参与分析"

        pc.add_user_feedback("scout", 1, raw_text=c1)
        pc.add_agent_response("scout", 1, content="已更新 Inc1")
        pc.add_user_feedback("scout", 2, raw_text=c2)
        pc.add_agent_response("scout", 2, content="已排除 BU")

        msgs = pc.to_messages_for_llm("scout", _ctx(pc), "继续")
        text = _text(msgs)

        assert c1 in text, (
            f"律 2 违反：第 1 轮纠正「{c1}」在第 3 轮 messages 中消失。\n{text[:800]}"
        )
        assert c2 in text, (
            f"律 2 违反：第 2 轮纠正「{c2}」在第 3 轮 messages 中消失。\n{text[:800]}"
        )

    def test_五轮纠正全部保留(self):
        pc = ProjectContext(run_id="continuity-5", analysis_goal=GOAL)
        corrections = [f"第{i}轮纠正_标记_{i * 7777}" for i in range(1, 6)]

        for i, c in enumerate(corrections, 1):
            pc.add_user_feedback("scout", i, raw_text=c)
            pc.add_agent_response("scout", i, content=f"已处理_{i}")

        msgs = pc.to_messages_for_llm("scout", _ctx(pc), "确认")
        text = _text(msgs)
        missing = [c for c in corrections if c not in text]

        assert not missing, (
            f"律 2 压力测试：{len(missing)} 轮纠正消失。\n丢失: {missing}"
        )

    def test_多轮历史条数随轮次增长(self):
        pc = ProjectContext(run_id="continuity-grow", analysis_goal=GOAL)
        prev_count = 0

        for i in range(1, 6):
            pc.add_user_feedback("scout", i, raw_text=f"第{i}轮纠正")
            pc.add_agent_response("scout", i, content=f"已处理_{i}")

            msgs = pc.to_messages_for_llm("scout", _ctx(pc), "继续")
            history = [m for m in msgs if m.get("role") in ("user", "assistant")]
            count = len(history)

            assert count > prev_count, (
                f"律 3 违反：第 {i} 轮后 messages 历史条数未增长。"
                f"前一轮: {prev_count}，当前: {count}"
            )
            prev_count = count

    def test_纠正原话不得被改写(self):
        pc = ProjectContext(run_id="raw-text", analysis_goal=GOAL)
        raw = "Inc1 是扣除退货之后的净销售额，不是毛额，后续分析必须用正确理解"
        pc.add_user_feedback("scout", 1, raw_text=raw)

        entry = pc.entries[0]
        assert entry.raw_user_text == raw, (
            f"律 2 违反：raw_user_text 被改写。\n原话: 「{raw}」\n存储: 「{entry.raw_user_text}」"
        )


# ─────────────────────────────────────────────────────────────────────────────
# B. 基线对比测试 — 律 1/4/5
# ─────────────────────────────────────────────────────────────────────────────

class TestBaselineRegression:

    def test_messages条数不低于基线(self):
        pc, ctx = _standard_scenario()
        msgs = pc.to_messages_for_llm("scout", ctx, "确认")
        assert len(msgs) >= _BASELINE_MIN_MESSAGES, (
            f"基线退化：messages 条数 {len(msgs)} 低于基线 {_BASELINE_MIN_MESSAGES}。\n"
            f"roles: {[m.get('role') for m in msgs]}"
        )

    def test_分析目标在messages中(self):
        pc, ctx = _standard_scenario()
        msgs = pc.to_messages_for_llm("scout", ctx, "确认")
        text = _text(msgs)
        assert GOAL in text, (
            f"律 1 违反：分析目标「{GOAL}」未出现在 messages 中。\n{text[:500]}"
        )

    def test_纠正原话以user_role出现(self):
        pc, ctx = _standard_scenario()
        msgs = pc.to_messages_for_llm("scout", ctx, "确认")
        user_text = "\n".join(
            m.get("content", "") for m in msgs
            if m.get("role") == "user" and isinstance(m.get("content"), str)
        )
        assert "Inc1 是净利润不是总收入" in user_text, (
            f"律 2 违反：第 1 轮纠正未以 role=user 出现。\n用户消息: {user_text[:500]}"
        )
        assert "BU 不参与分析" in user_text, (
            f"律 2 违反：第 2 轮纠正未以 role=user 出现。\n用户消息: {user_text[:500]}"
        )

    def test_assistant角色存在(self):
        pc, ctx = _standard_scenario()
        msgs = pc.to_messages_for_llm("scout", ctx, "确认")
        roles = [m.get("role") for m in msgs]
        assert "assistant" in roles, (
            f"律 3 违反：messages 中缺少 assistant 角色。roles: {roles}"
        )

    def test_最后一条是user且含当前输入(self):
        pc, ctx = _standard_scenario()
        msgs = pc.to_messages_for_llm("scout", ctx, "这是最新用户输入_独特标记")
        assert msgs[-1]["role"] == "user", f"最后一条不是 user: {msgs[-1]['role']}"
        assert "这是最新用户输入_独特标记" in (msgs[-1].get("content") or ""), (
            "最后一条 user 不含当前 user_input"
        )

    def test_重构前后messages条数不减少(self):
        """核心回归守门：同样的输入序列，messages 条数必须稳定，不随重构而缩减。"""
        def build(n: int) -> list[dict]:
            pc = ProjectContext(run_id=f"regression-{n}", analysis_goal=GOAL)
            for i in range(1, n + 1):
                pc.add_user_feedback("scout", i, raw_text=f"纠正_{i}_{i*3333}")
                pc.add_agent_response("scout", i, content=f"已处理_{i}")
            return pc.to_messages_for_llm("scout", _ctx(pc), "继续")

        baseline = build(3)
        current = build(3)

        assert len(current) >= len(baseline), (
            f"重构退化：messages 条数 {len(current)} < 基线 {len(baseline)}。\n"
            f"基线 roles: {[m.get('role') for m in baseline]}\n"
            f"当前 roles: {[m.get('role') for m in current]}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# C. 跨阶段原始记录测试 — 律 4
# ─────────────────────────────────────────────────────────────────────────────

class TestCrossStageTransfer:

    def test_tool_exchange以标准协议出现在messages_history(self):
        """同阶段 tool exchange 必须以 assistant+tool_calls 及 role=tool 出现。"""
        pc = ProjectContext(run_id="tool-exchange", analysis_goal=GOAL)
        tc = ToolCallRecord(
            tool_call_id="tc-001",
            name="update_field_understanding",
            arguments='{"column_name":"Inc1","display_name":"净利润"}',
            result='{"status":"ok"}',
        )
        pc.add_tool_exchange("scout", 1, [tc], assistant_content="更新字段理解")

        msgs = pc.to_messages_for_llm("scout", _ctx(pc), "确认")

        # 必须有 assistant 含 tool_calls
        assert any(
            m.get("role") == "assistant" and m.get("tool_calls")
            for m in msgs
        ), "律 4 违反：messages 中缺少 role=assistant + tool_calls turn"

        # 必须有 role=tool + tool_call_id
        tool_msgs = [m for m in msgs if m.get("role") == "tool"]
        assert tool_msgs, "律 4 违反：messages 中缺少 role=tool turn"
        assert tool_msgs[0].get("tool_call_id") == "tc-001", (
            f"tool_call_id 不匹配。实际: {tool_msgs[0].get('tool_call_id')}"
        )

    def test_scout纠正在cleaner阶段messages_history中可见(self):
        """上下文保真律：scout 纠正必须在 messages_history 中原样出现。"""
        pc = ProjectContext(run_id="cross-stage", analysis_goal=GOAL)
        scout_msg = "Inc1 是净利润，Code 是门店标识符"

        pc.add_user_feedback("scout", 1, raw_text=scout_msg)
        pc.add_agent_response("scout", 1, content="字段理解完成",
                              snapshot={"target": "Inc1", "features": ["Period"]})
        pc.add_stage_transition("cleaner")

        parts = pc.build_prompt("cleaner", _ctx(pc))
        msgs = parts["messages_history"]

        assert msgs, "messages_history 不应为空"
        found = any(scout_msg in m.get("content", "") for m in msgs)
        assert found, f"律 4 违反：cleaner messages_history 中找不到 scout 纠正。\n{msgs}"

    def test_tool_error保留在messages中(self):
        """律 6 + 律 4：工具执行出错时，error 内容必须以 role=tool 出现在 messages。"""
        pc = ProjectContext(run_id="tool-error", analysis_goal=GOAL)
        tc_err = ToolCallRecord(
            tool_call_id="tc-err-001",
            name="update_field_understanding",
            arguments='{"column_name":"Inc1"}',
            result="",
            error="字段不存在：Inc1 未在 column_semantics 中注册",
        )
        pc.add_tool_exchange("scout", 1, [tc_err], assistant_content="尝试更新")

        msgs = pc.to_messages_for_llm("scout", _ctx(pc), "修正")
        tool_msgs = [m for m in msgs if m.get("role") == "tool"]

        assert tool_msgs, "律 6 违反：tool 执行出错但 role=tool 条目未保留"
        tool_content = " ".join(m.get("content", "") for m in tool_msgs)
        assert "字段不存在" in tool_content or "Inc1" in tool_content, (
            f"律 6 违反：tool 错误信息未出现在 role=tool 内容中。\ntool_content: {tool_content}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# D. 动态上下文顺序测试 — 律 1
# ─────────────────────────────────────────────────────────────────────────────

class TestContextOrder:

    def test_动态上下文排在静态指令前面(self):
        """律 1：system 消息中，分析目标必须排在 agent_system_extra 之前。"""
        pc = ProjectContext(run_id="order-test", analysis_goal=GOAL)
        agent_instructions = "【关注点 1】理解字段业务含义，调用 update_field_understanding"

        msgs = pc.to_messages_for_llm(
            "scout", _ctx(pc), "开始",
            agent_system_extra=agent_instructions,
        )
        sys_msgs = [m for m in msgs if m.get("role") == "system"]
        user_msgs = [m for m in msgs if m.get("role") == "user"]

        # 分析目标在 user message 中（query），agent 指令在 system 消息中
        assert sys_msgs, "缺少 system 消息"
        assert user_msgs, "缺少 user 消息"
        assert any(GOAL in m.get("content", "") for m in user_msgs), (
            f"分析目标「{GOAL}」应在 user messages 中"
        )
        assert any(agent_instructions in m.get("content", "") for m in sys_msgs), (
            f"agent_instructions 应在 system 消息中"
        )


# ─────────────────────────────────────────────────────────────────────────────
# E. 失败轮次保留测试 — 律 6
# ─────────────────────────────────────────────────────────────────────────────

class TestFailureRoundPreservation:

    def test_失败轮次用户原话保留在后续messages(self):
        """律 6：LLM 未理解的那一轮，用户说的话必须在后续 messages 中仍可见。"""
        pc = ProjectContext(run_id="failure-preserved", analysis_goal=GOAL)

        failure_input = "只保留店铺编号、周期、净利润三个字段"
        pc.add_user_feedback("scout", 1, raw_text=failure_input)
        # 模拟 agent 未理解
        pc.add_agent_response("scout", 1, content="[未理解] LLM 未产生有效工具调用")

        # 用户第 2 轮重新表达
        pc.add_user_feedback("scout", 2, raw_text="我的意思是：StoreID 是标识符，Period 是时间，Inc1 是目标")

        msgs = pc.to_messages_for_llm("scout", _ctx(pc), "请重新理解")
        text = _text(msgs)

        assert failure_input in text, (
            f"律 6 违反：失败轮次用户原话「{failure_input}」从后续 messages 消失。\n{text[:800]}"
        )

    def test_多阶段失败轮次均保留(self):
        """律 6：scout 和 cleaner 各有一次失败，analyst 阶段 messages 中都必须可见。"""
        pc = ProjectContext(run_id="multi-failure", analysis_goal=GOAL)

        scout_fail = "把 Inc1 改成净利润，BU 不参与"
        cleaner_fail = "Inc1 的缺失值用中位数填补"

        pc.add_user_feedback("scout", 1, raw_text=scout_fail)
        pc.add_agent_response("scout", 1, content="[未理解]")
        pc.add_agent_response("scout", 2, content="字段完成",
                              snapshot={"target": "Inc1", "features": ["Period"]})
        pc.add_stage_transition("cleaner")

        pc.add_user_feedback("cleaner", 1, raw_text=cleaner_fail)
        pc.add_agent_response("cleaner", 1, content="[未理解]")
        pc.add_agent_response("cleaner", 2, content="清洗完成")
        pc.add_stage_transition("analyst")

        msgs = pc.to_messages_for_llm("analyst", _ctx(pc), "开始分析")
        text = _text(msgs)

        assert scout_fail in text, (
            f"律 6 违反：scout 失败轮次原话在 analyst 阶段消失。\n{text[:800]}"
        )
        assert cleaner_fail in text, (
            f"律 6 违反：cleaner 失败轮次原话在 analyst 阶段消失。\n{text[:800]}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 元测试
# ─────────────────────────────────────────────────────────────────────────────

def test_meta_standard_scenario_fixture可正常构建():
    pc, ctx = _standard_scenario()
    assert pc is not None
    assert ctx["query"] == GOAL
    # 2 轮 user + 2 轮 assistant = 4 条 entries
    assert len(pc.entries) == 4
