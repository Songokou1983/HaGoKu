"""HaGoKu Streamlit UI — 事件流组件"""

from __future__ import annotations

import streamlit as st
from datetime import datetime

from hagokyu.observability.events import Event, EventType

# Agent emoji + 颜色映射
AGENT_STYLE = {
    "Manager":  {"emoji": "🧠", "color": "#a78bfa"},   # 紫
    "Scout":    {"emoji": "🔍", "color": "#22d3ee"},   # 青
    "Cleaner":  {"emoji": "🧹", "color": "#fbbf24"},   # 黄
    "Analyst":  {"emoji": "📊", "color": "#60a5fa"},   # 蓝
    "Reporter": {"emoji": "📝", "color": "#34d399"},   # 绿
}


def agent_card(agent: str) -> tuple[str, str]:
    """获取 agent 的 emoji 和颜色"""
    style = AGENT_STYLE.get(agent, {"emoji": "●", "color": "#888"})
    return style["emoji"], style["color"]


def event_to_display_text(event: Event) -> str | None:
    """把事件转换为可读文本"""
    et = event.event_type
    data = event.data or {}

    if et == EventType.AGENT_STARTED:
        return f"{agent_card(event.agent)[0]} {event.agent} 开始工作..."
    if et == EventType.AGENT_COMPLETED:
        dur = data.get("duration", "")
        return f"✅ {event.agent} 完成" + (f" ({dur})" if dur else "")
    if et == EventType.AGENT_FAILED:
        return f"❌ {event.agent} 失败: {data.get('error', '未知错误')}"
    if et == EventType.AGENT_THINKING:
        thought = data.get("thought", "")
        return f"💭 {thought}" if thought else None
    if et == EventType.TOOL_CALLED:
        tool = data.get("tool", "?")
        args = data.get("args_summary", "")
        return f"🔧 {tool}" + (f"({args})" if args else "")
    if et == EventType.TOOL_RESULT:
        s = data.get("summary", "")
        return f"  → {s}" if s else None
    if et == EventType.TOOL_ERROR:
        return f"  ❌ {data.get('error', '')}"
    if et == EventType.QUALITY_CHECK:
        v = data.get("verdict", "")
        d = data.get("detail", "")
        icon = "✅" if v == "pass" else "⚠️"
        return f"🛡️ {icon} {d}"
    if et == EventType.USER_INPUT_REQUESTED:
        return f"👤 {data.get('question', '')}"
    if et == EventType.RUN_STARTED:
        return f"🚀 开始分析: {data.get('query', '')[:60]}"
    if et == EventType.RUN_COMPLETED:
        dur = data.get("duration", "")
        tokens = data.get("token_count", "")
        out = data.get("output_path", "")
        parts = [f"🎉 分析完成！"]
        if dur:
            parts.append(f"耗时 {dur}")
        if tokens:
            parts.append(f"Token {tokens}")
        if out:
            parts.append(f"报告: {out.split('/')[-1]}")
        return " | ".join(parts)
    if et == EventType.RUN_FAILED:
        return f"❌ 运行失败: {data.get('error', '')}"
    return None


def render_event_log(events: list[Event]) -> None:
    """
    渲染事件日志（时间线格式）

    使用 Streamlit 的 expander 分组显示，每个 agent 一组
    """
    if not events:
        st.info("分析尚未开始...")
        return

    # 按 agent 分组
    by_agent: dict[str, list[Event]] = {}
    for e in events:
        by_agent.setdefault(e.agent, []).append(e)

    # 时间顺序排列
    all_events = sorted(events, key=lambda e: e.timestamp)

    # 统计摘要
    col1, col2, col3, col4 = st.columns(4)
    n_thinking = sum(1 for e in all_events if e.event_type == EventType.AGENT_THINKING)
    n_tools = sum(1 for e in all_events if e.event_type == EventType.TOOL_CALLED)
    n_results = sum(1 for e in all_events if e.event_type == EventType.AGENT_COMPLETED)
    n_failed = sum(1 for e in all_events if e.event_type in (EventType.AGENT_FAILED, EventType.RUN_FAILED))

    col1.metric("思考", n_thinking)
    col2.metric("工具调用", n_tools)
    col3.metric("完成", n_results)
    col4.metric("失败", n_failed, delta_color="inverse" if n_failed else "off")

    st.divider()

    # 时间线
    for event in all_events:
        text = event_to_display_text(event)
        if not text:
            continue

        emoji, color = agent_card(event.agent)
        ts = event.timestamp.strftime("%H:%M:%S")

        # 根据事件类型选择样式
        if event.event_type == EventType.AGENT_COMPLETED:
            st.success(text)
        elif event.event_type in (EventType.AGENT_FAILED, EventType.RUN_FAILED):
            st.error(text)
        elif event.event_type == EventType.TOOL_ERROR:
            st.warning(text)
        elif event.event_type == EventType.QUALITY_CHECK:
            if event.data.get("verdict") == "pass":
                st.success(text)
            else:
                st.warning(text)
        elif event.event_type == EventType.AGENT_STARTED:
            st.info(f"{emoji} **{event.agent}** 开始工作...")
        elif event.event_type == EventType.AGENT_THINKING:
            st.caption(f"⏱ {ts} {text}")
        elif event.event_type == EventType.TOOL_CALLED:
            st.code(text, language=None)
        elif event.event_type == EventType.TOOL_RESULT:
            st.caption(f"  → {text[3:]}")
        else:
            st.caption(f"⏱ {ts} {text}")


def render_event_log_timeline(events: list[Event]) -> None:
    """
    简洁时间线格式（用于侧边栏或紧凑区域）
    """
    if not events:
        return

    timeline = []
    for event in sorted(events, key=lambda e: e.timestamp):
        text = event_to_display_text(event)
        if not text:
            continue
        emoji, color = agent_card(event.agent)
        ts = event.timestamp.strftime("%H:%M:%S")

        # 状态指示器颜色
        if event.event_type in (EventType.AGENT_FAILED, EventType.RUN_FAILED):
            status = "🔴"
        elif event.event_type == EventType.AGENT_COMPLETED:
            status = "🟢"
        elif event.event_type == EventType.QUALITY_CHECK and event.data.get("verdict") != "pass":
            status = "🟡"
        else:
            status = "⚪"

        timeline.append(f"{ts} {status} {text[:80]}")

    if timeline:
        st.text_area(
            "分析进度",
            value="\n".join(timeline[-50:]),  # 最近 50 条
            height=200,
            disabled=True,
            label_visibility="collapsed",
        )
