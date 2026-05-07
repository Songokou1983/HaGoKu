"""HaGoKu Streamlit UI — 分析页面"""

from __future__ import annotations

import threading
import time
from typing import Any

import streamlit as st

from hagokyu.config import HaGoKuConfig
from hagokyu.manager.orchestrator import Orchestrator
from hagokyu.observability.events import Event
from hagokyu.storage.project_manager import ProjectManager
from hagokyu.agents.scout import DataContext

# ── 工具函数 ────────────────────────────────────────────

def _poll_and_update() -> None:
    """立即从后台线程拉取最新 events 并更新 session_state（不触发 rerun）"""
    evs = st.session_state.get("_analysis_events_h", [])
    st.session_state.analysis_events = list(evs)
    thread = st.session_state.get("_analysis_thread")
    if thread and not thread.is_alive():
        _results = st.session_state.get("_analysis_result_h", [])
        _errors = st.session_state.get("_analysis_error_h", [])
        st.session_state.analysis_result = _results[0] if _results else None
        st.session_state.analysis_error = _errors[0] if _errors else None
        st.session_state.analysis_running = False
        st.session_state._just_finished = True  # 标记：刚结束，本 render 继续显示 thinking panel
    else:
        waited = time.time() - st.session_state.get("_analysis_start", time.time())
        if waited >= 300:
            st.session_state.analysis_running = False
            st.session_state.analysis_error = "分析超时（5分钟）"

def _init_chat_state() -> None:
    """初始化对话状态"""
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []
    if "analysis_running" not in st.session_state:
        st.session_state.analysis_running = False
    if "analysis_events" not in st.session_state:
        st.session_state.analysis_events = []
    if "analysis_result" not in st.session_state:
        st.session_state.analysis_result = None
    if "analysis_error" not in st.session_state:
        st.session_state.analysis_error = None
    if "current_data_path" not in st.session_state:
        st.session_state.current_data_path = None
    if "_events_shown_count" not in st.session_state:
        st.session_state._events_shown_count = 0
    if "_just_finished" not in st.session_state:
        st.session_state._just_finished = False
    # Scout 字段确认
    if "awaiting_field_confirmation" not in st.session_state:
        st.session_state.awaiting_field_confirmation = False
    if "scout_done_data" not in st.session_state:
        st.session_state.scout_done_data = None
    if "scout_confirm_data" not in st.session_state:
        st.session_state.scout_confirm_data = None
    if "awaiting_scout_next_step" not in st.session_state:
        st.session_state.awaiting_scout_next_step = False
    if "scout_next_step_data" not in st.session_state:
        st.session_state.scout_next_step_data = None
    # Cleaner 策略确认
    if "awaiting_cleaning_confirmation" not in st.session_state:
        st.session_state.awaiting_cleaning_confirmation = False
    if "cleaning_strategy_data" not in st.session_state:
        st.session_state.cleaning_strategy_data = None
    # Analyst 方向确认
    if "awaiting_analyst_confirmation" not in st.session_state:
        st.session_state.awaiting_analyst_confirmation = False
    if "analyst_preliminary_data" not in st.session_state:
        st.session_state.analyst_preliminary_data = None
    # 缓存的字段修正（用户确认后保存，供后续阶段使用）
    if "cached_field_corrections" not in st.session_state:
        st.session_state.cached_field_corrections = {}
    # 用户确认的清洗操作
    if "confirmed_cleaning_operations" not in st.session_state:
        st.session_state.confirmed_cleaning_operations = None
    # 用户输入的查询（保存后在后续阶段使用）
    if "current_query" not in st.session_state:
        st.session_state.current_query = ""


# ── Chat 消息生成器（纯对话，无卡片） ────────────────────────────

AGENT_COLOR = {
    "scout":    "#22d3ee",
    "cleaner":  "#4ade80",
    "analyst":  "#f59e0b",
    "reporter": "#a78bfa",
}
AGENT_LABEL = {
    "scout":    "🔍 Scout",
    "cleaner":  "🧹 Cleaner",
    "analyst":  "📊 Analyst",
    "reporter": "📋 Reporter",
}

# 字段中文名称映射（常见英文缩写 → 中文）
FIELD_CHINESE_NAMES = {
    # 常见收入/财务
    "Inc": "收入", "Revenue": "收入", "Sales": "销售额", "Amount": "金额",
    "Cost": "成本", "Profit": "利润", "Margin": "利润率",
    # 常见维度
    "Date": "日期", "Time": "时间", "Period": "期间", "Year": "年份", "Month": "月份",
    "Channel": "渠道", "Region": "区域", "Country": "国家", "City": "城市",
    "BU": "业务单元", "Dept": "部门", "Team": "团队",
    # 常见指标
    "Count": "数量", "Num": "数量", "Total": "合计", "Avg": "均值",
    "Rate": "比率", "Ratio": "比率", "Percentage": "百分比",
    # 常见ID
    "ID": "编号", "Code": "编码", "Name": "名称", "Type": "类型",
    # 布尔
    "Is": "是否", "Has": "是否有", "Flag": "标记",
}
# 通用中文名称推断：从英文字段名提取有意义的中文
def _infer_chinese_name(field: str) -> str:
    """从英文字段名推断中文名称"""
    # 精确匹配
    for eng, chi in FIELD_CHINESE_NAMES.items():
        if field.lower() == eng.lower():
            return chi
    # 前缀匹配（如 Inc1 → 收入）
    for eng, chi in FIELD_CHINESE_NAMES.items():
        if field.lower().startswith(eng.lower()):
            return chi
    # 去除常见后缀（1, 2, _new, _old 等）
    import re
    base = re.sub(r'[\d_]+$', '', field)
    for eng, chi in FIELD_CHINESE_NAMES.items():
        if base.lower() == eng.lower():
            return chi
    # 全大写转首字母大写（无匹配时）
    return field


def _scout_field_message(scout_data: dict) -> str:
    """生成 Scout 的字段理解消息"""
    n_rows = scout_data.get("n_rows", 0)
    n_cols = scout_data.get("n_cols", 0)
    cols = scout_data.get("columns", [])
    uncertain = set(scout_data.get("uncertain_columns", []))
    descs = scout_data.get("column_descriptions", {})

    lines = [f"我对这份数据（{n_rows} 行 × {n_cols} 列）的字段理解如下：", ""]
    shown = cols[:15]
    for col in shown:
        desc = descs.get(col, f"{col}")
        marker = "⚠️ " if col in uncertain else "• "
        lines.append(f"{marker}**{col}**：{desc}")
    if len(cols) > 15:
        lines.append(f"... 还有 {len(cols) - 15} 个字段省略")
    lines.extend(["", "这些理解对吗？如果有误请告诉我，我会修正。"])
    return "\n".join(lines)


def _cleaner_strategy_message(strategy_data: dict) -> str:
    """生成 Cleaner 的策略确认消息"""
    operations = strategy_data.get("operations", [])
    quality = strategy_data.get("data_quality", "unknown")
    quality_labels = {"good": "数据质量良好", "medium": "数据质量一般", "poor": "数据质量问题较多"}

    lines = [f"数据质量：{quality_labels.get(quality, quality)}"]
    if not operations:
        lines.append("未检测到需要清洗的问题，数据可以直接分析。")
        lines.append("你觉得需要做什么特殊处理吗？")
        return "\n".join(lines)

    lines.append(f"我计划执行 {len(operations)} 个清洗操作：")
    for op in operations[:8]:
        col = op.get("column", "")
        reason = op.get("reason", "")
        lines.append(f"• **{col}**：{reason[:60]}{'...' if len(reason) > 60 else ''}")
    if len(operations) > 8:
        lines.append(f"... 还有 {len(operations) - 8} 个操作")
    lines.extend(["", "这个清洗方案可以吗？或者你想调整某个处理方式？"])
    return "\n".join(lines)


def _analyst_finding_message(prelim_data: dict) -> str:
    """生成 Analyst 的初步发现消息"""
    findings = prelim_data.get("preliminary_findings", [])
    suggested = prelim_data.get("suggested_focus", "")
    power_warnings = prelim_data.get("power_warnings", [])[:2]

    lines = []
    if power_warnings:
        lines.append(f"⚡ {power_warnings[0]}")
        lines.append("")
    if not findings:
        lines.append("初步分析没有发现明显的统计规律。")
    else:
        lines.append(f"初步找到了 {len(findings)} 个分析方向：")
        for f in findings[:5]:
            sig = "✅ 显著" if f.get("significance") == "significant" else "⚪ 不显著"
            q = f.get("question", "")
            p = f.get("p_value")
            p_str = f"（p={p:.4f}）" if p is not None else ""
            lines.append(f"• {sig} {p_str}：{q}")
    if suggested:
        lines.extend(["", f"💡 {suggested}"])
    lines.extend(["", "你想重点关注哪个方向？或者有其他想看的维度？"])
    return "\n".join(lines)





def _render_thinking_panel() -> None:
    """实时 Thinking 面板：显示模型信息 + 思考时间 + 工具调用流 + 进度"""
    from hagokyu.config import HaGoKuConfig
    config = HaGoKuConfig.load()

    evs = st.session_state.get("analysis_events", [])
    elapsed = time.time() - st.session_state.get("_analysis_start", time.time())
    elapsed_str = f"{int(elapsed)}"

    # CSS for pulsing dot
    st.html(f"""
    <style>
    @keyframes pulse-dot {{
        0%, 100% {{ opacity: 1; transform: scale(1); }}
        50% {{ opacity: 0.4; transform: scale(0.85); }}
    }}
    .thinking-dot {{
        display: inline-block;
        width: 8px; height: 8px;
        background: #38bdf8;
        border-radius: 50%;
        margin-right: 6px;
        animation: pulse-dot 1.2s ease-in-out infinite;
        box-shadow: 0 0 6px #38bdf8;
    }}
    .thinking-panel {{
        background: #0d1117;
        border: 1px solid #38bdf8;
        border-radius: 4px;
        padding: 12px 16px;
        margin: 8px 0;
        font-family: 'Space Mono', monospace;
    }}
    .thinking-header {{
        display: flex;
        align-items: center;
        gap: 16px;
        margin-bottom: 10px;
        color: #c9d1d9;
        font-size: 12px;
    }}
    .thinking-timer {{
        color: #38bdf8;
        font-weight: 700;
        font-size: 13px;
    }}
    .tool-line {{
        color: #6e7681;
        font-size: 12px;
        padding: 2px 0;
        border-left: 2px solid #21262d;
        padding-left: 8px;
        margin: 3px 0 3px 8px;
    }}
    .tool-line.tool-call {{
        color: #f0e68c;
        border-left-color: #f0e68c;
    }}
    .tool-line.tool-result {{
        color: #4ade80;
        border-left-color: #4ade80;
    }}
    .tool-line.agent-thinking {{
        color: #38bdf8;
        border-left-color: #38bdf8;
    }}
    .thinking-end {{
        clear: both;
    }}
    </style>
    """)

    # 计算当前阶段
    current_agent = "Scout"
    tool_calls = []
    latest_thought = ""  # 最新的思考内容
    for ev in reversed(evs):
        ev_type = str(getattr(ev, "event_type", ""))
        agent = getattr(ev, "agent", "") or ""
        data = getattr(ev, "data", {}) or {}
        if "tool_called" in ev_type.lower():
            tool_calls.append(("call", data.get("tool", ""), data.get("args_summary", "")))
        elif "tool_result" in ev_type.lower():
            tool_calls.append(("result", data.get("summary", "")))
        elif "thinking" in ev_type.lower() and not latest_thought:
            # 保留最新的思考内容
            thought = data.get("thought", "")
            if thought:
                latest_thought = thought
        if agent.lower() in ("scout", "cleaner", "analyst", "reporter"):
            current_agent = agent.capitalize()
            break

    # 显示面板
    st.markdown(f"""
    <div class="thinking-panel">
        <div class="thinking-header">
            <span style="color:#6e7681;">模型：</span>
            <span style="color:#c9d1d9;">{config.llm.model}</span>
            <span style="color:#6e7681; margin-left:8px;">状态：</span>
            <span class="thinking-timer"><span class="thinking-dot"></span>思考 {elapsed_str} 秒</span>
            <span style="color:#6e7681; margin-left:8px;">当前：</span>
            <span style="color:#38bdf8;">{current_agent}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 显示当前思考内容（Agent正在想什么）
    if latest_thought:
        st.markdown(f"""
        <div class="tool-line agent-thinking">💭 {latest_thought}</div>
        """, unsafe_allow_html=True)

    # 显示最近的工具调用（最多显示最后3个）
    if tool_calls:
        for tc in tool_calls[-3:]:
            if tc[0] == "call":
                st.markdown(f"""
                <div class="tool-line tool-call">🔧 {tc[1]}（{tc[2]}）</div>
                """, unsafe_allow_html=True)
            else:
                result = tc[1][:80] + "..." if len(tc[1]) > 80 else tc[1]
                st.markdown(f"""
                <div class="tool-line tool-result">  → {result}</div>
                """, unsafe_allow_html=True)

    # 进度条
    _render_agent_pipeline(evs, True)


def _render_agent_pipeline(events: list[Event], running: bool) -> None:
    """横向进度条 + 4 个阶段标签（占满一行）"""

    # 根据最后一个事件判断当前进度
    pct = 0
    stage_label = "等待开始"
    # 当前阶段索引（用于判断哪些阶段已完成）
    # scout_first: Scout完成后=阶段0，此时应显示 Scout=✓, 其余=○
    # cleaning_first: Cleaner完成后=阶段1，应显示 Scout=✓, Cleaner=✓, 其余=○
    # analyst_first: Analyst完成后=阶段2，应显示 Scout=✓, Cleaner=✓, Analyst=✓, Reporter=○
    # full: Reporter完成后=阶段3，全部=✓
    current_stage = 0  # 当前活动阶段（0-3）
    if events:
        last = events[-1]
        etype_val = getattr(last, "event_type", None)
        etype = etype_val.value if etype_val else ""
        agent_name = getattr(last, "agent", "") or ""

        if "complete" in etype or "finished" in etype:
            # 根据 agent 名判断是哪个阶段完成
            if agent_name == "Reporter":
                current_stage = 3
                pct, stage_label = 100, "完成"
            elif agent_name == "Analyst":
                current_stage = 2
                pct, stage_label = 75, "分析完成"
            elif agent_name == "Cleaner":
                current_stage = 1
                pct, stage_label = 50, "清洗完成"
            elif agent_name == "Scout":
                current_stage = 0
                pct, stage_label = 25, "字段识别完成"
            else:
                # 默认：认为是完整流程结束
                current_stage = 3
                pct, stage_label = 100, "完成"
        elif "report" in etype or "generate" in etype:
            pct, stage_label = 85, "生成报告"
            current_stage = 3
        elif "analysis" in etype or "regression" in etype or "ttest" in etype or "correlation" in etype:
            pct, stage_label = 55, "分析数据"
            current_stage = 2
        elif "clean" in etype or "outlier" in etype or "missing" in etype:
            pct, stage_label = 35, "清洗数据"
            current_stage = 1
        elif "scout" in etype or "data_loaded" in etype or "fields" in etype:
            pct, stage_label = 15, "识别字段"
            current_stage = 0

    labels = ["Scout", "Cleaner", "Analyst", "Reporter"]
    active_idx = current_stage  # 当前活动阶段（正在跑的那个）
    if pct == 100:
        active_idx = 3

    # 横向进度条（填满整行，用 CSS 实现）
    filled = pct
    unfilled = 100 - pct

    bar_html = f"""
    <div style='display:flex;align-items:center;gap:0;width:100%;height:8px;border-radius:4px;overflow:hidden;background:#21262d;'>
        <div style='width:{filled}%;height:100%;background:linear-gradient(90deg,#00ffff,#00ff41);border-radius:4px 0 0 4px;transition:width 0.3s;'></div>
        <div style='width:{unfilled}%;height:100%;'></div>
    </div>
    """
    st.markdown(bar_html, unsafe_allow_html=True)

    # 4 个阶段标签（横向排列，填满整行）
    cols = st.columns(4)
    for i, (lbl, col) in enumerate(zip(labels, cols)):
        is_done = i < active_idx
        is_active = i == active_idx and running and pct < 100
        color = "#00ff41" if is_done else ("#00ffff" if is_active else "#3d4450")
        dot = "●" if is_active else "○"
        text = f"{dot} {lbl}"
        if is_done:
            text = f"✓ {lbl}"
        col.markdown(
            f"<span style='color:{color};font-family:Space Mono,monospace;font-size:11px;'>{text}</span>",
            unsafe_allow_html=True,
        )


def _render_chat() -> None:
    """渲染聊天消息历史"""
    messages = st.session_state.get("chat_messages", [])

    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        agent = msg.get("agent", "")  # scout/cleaner/analyst/reporter

        if role == "user":
            with st.chat_message("user"):
                st.markdown(content)
        else:
            with st.chat_message("assistant"):
                if isinstance(content, dict):
                    # 分析结果字典
                    status = content.get("status", "")
                    if status == "completed":
                        dur = content.get("duration_ms", 0) / 1000
                        n_results = content.get("n_results", 0)
                        output_path = content.get("output_path", "")
                        st.success(f"✅ 分析完成（{dur:.1f}s），发现 {n_results} 个结论")
                        if output_path:
                            if st.button("📋 查看完整报告", key="view_report_btn"):
                                st.session_state.last_report_path = output_path
                                st.session_state.nav_page = "report"
                                st.rerun()
                    elif status == "skipped":
                        llm_resp = content.get("llm_response", "")
                        if llm_resp:
                            st.info(f"🤖 {llm_resp}")
                        else:
                            st.info("这个问题和当前数据集无关，无法通过分析回答。")
                    elif status == "ambiguous":
                        st.warning(f"❓ {content.get('llm_response', '需要更多信息才能判断')}")
                    else:
                        st.error(content.get("message", "分析未完成"))
                else:
                    # 检查是否有表格数据
                    table_data = msg.get("table_data")
                    if table_data:
                        # 渲染表格 + 引导文字
                        if agent and agent in AGENT_COLOR:
                            color = AGENT_COLOR[agent]
                            label = AGENT_LABEL[agent]
                            st.markdown(
                                f'<span style="color:{color};font-family:Space Mono,monospace;">'
                                f'**{label}：**</span> {content}',
                                unsafe_allow_html=True,
                            )
                        else:
                            st.markdown(content)
                        # 渲染表格
                        import pandas as pd
                        headers = table_data.get("headers", [])
                        rows = table_data.get("rows", [])
                        uncertain = set(table_data.get("uncertain", []))
                        if headers and rows:
                            df = pd.DataFrame(rows, columns=headers)
                            # 高亮 uncertain 行
                            def _highlight_uncertain(row):
                                if uncertain and row.iloc[0] in uncertain:
                                    return ["background-color: rgba(255,200,0,0.15)"] * len(row)
                                return [""] * len(row)
                            st.dataframe(
                                df.style.apply(_highlight_uncertain, axis=1),
                                hide_index=True,
                                use_container_width=True,
                            )
                            if uncertain:
                                st.caption(f"⚠️ {len(uncertain)} 个字段需要你确认")
                        st.caption("⚠️ 标记的字段需要你确认。如不重要，输入「确认」继续即可；如有误请告诉我。")
                    else:
                        # 普通文本消息：Agent 有角色时加颜色标签
                        if agent and agent in AGENT_COLOR:
                            color = AGENT_COLOR[agent]
                            label = AGENT_LABEL[agent]
                            st.markdown(
                                f'<span style="color:{color};font-family:Space Mono,monospace;">'
                                f'**{label}：**</span> {content}',
                                unsafe_allow_html=True,
                            )
                        else:
                            st.markdown(content)

    # 实时事件流（只显示有意义的进度，隐藏内部噪音）
    evs = st.session_state.get("analysis_events", [])
    shown_count = st.session_state.get("_events_shown_count", 0)
    new_evs = evs[shown_count:]
    if new_evs:
        # 过滤：只保留对用户有意义的事件
        # 隐藏：工具调用(tool_called)、工具结果(tool_result)、内部状态日志
        skip_keywords = [
            "正在加载数据", "加载成功", "生成数据画像", "质量=",
            "正在识别数据字段", "理解你的问题", "识别", "需确认",
            "检测数据质量", "生成清洗策略", "初步分析",
            "tool_called", "tool_result",
        ]
        meaningful_evs = []
        for ev in new_evs:
            ev_str = str(getattr(ev, "event_type", "")).lower()
            ev_data = getattr(ev, "data", {}) or {}
            thought = ev_data.get("thought", "")
            result_summary = ev_data.get("result_summary", "")
            # 跳过工具调用、工具结果、Agent启动
            if "tool_called" in ev_str or "tool_result" in ev_str:
                continue
            if ev_str.endswith(".started") or "start" in ev_str:
                continue
            # 跳过包含内部噪音关键词的 thinking
            if "thinking" in ev_str and thought:
                if any(kw in thought for kw in skip_keywords):
                    continue
            meaningful_evs.append(ev)

        if meaningful_evs:
            with st.chat_message("assistant"):
                for ev in meaningful_evs:
                    ev_str = str(getattr(ev, "event_type", ""))
                    agent_name = getattr(ev, "agent", "") or ""

                    if agent_name.lower() in ("scout",):
                        color, label = AGENT_COLOR["scout"], AGENT_LABEL["scout"]
                    elif agent_name.lower() in ("cleaner",):
                        color, label = AGENT_COLOR["cleaner"], AGENT_LABEL["cleaner"]
                    elif agent_name.lower() in ("analyst",):
                        color, label = AGENT_COLOR["analyst"], AGENT_LABEL["analyst"]
                    elif agent_name.lower() in ("reporter",):
                        color, label = AGENT_COLOR["reporter"], AGENT_LABEL["reporter"]
                    elif agent_name.lower() in ("manager",):
                        color, label = "#a78bfa", "🧠 Manager"
                    else:
                        color, label = "#6e7681", f"🔧 {agent_name}"

                    ev_data = getattr(ev, "data", {}) or {}
                    if "thinking" in ev_str.lower():
                        thought = ev_data.get("thought", "")
                        if thought:
                            st.markdown(
                                f'<span style="color:{color};font-family:JetBrains Mono,monospace;font-size:16px;">'
                                f'**{label}** 💭 {thought[:150]}</span>',
                                unsafe_allow_html=True,
                            )
                    elif "complete" in ev_str.lower() or "finished" in ev_str.lower():
                        summary = ev_data.get("result_summary", ev_data.get("message", ""))
                        if summary:
                            st.markdown(
                                f'<span style="color:#4ade80;font-family:JetBrains Mono,monospace;font-size:16px;">'
                                f'✓ {label}: {summary[:80]}</span>',
                                unsafe_allow_html=True,
                            )
                    elif "error" in ev_str.lower():
                        err = ev_data.get("error", ev_data.get("message", "未知错误"))
                        st.markdown(
                            f'<span style="color:#f87171;font-family:JetBrains Mono,monospace;font-size:16px;">'
                            f'❌ {err[:80]}</span>',
                            unsafe_allow_html=True,
                        )
                    else:
                        summary = ev_data.get("thought", ev_data.get("message", ev_data.get("result_summary", "")))
                        if summary:
                            st.markdown(
                                f'<span style="color:{color};font-family:JetBrains Mono,monospace;font-size:16px;">'
                                f'{label}: {summary[:80]}</span>',
                                unsafe_allow_html=True,
                            )
        st.session_state._events_shown_count = len(evs)

    # 错误消息
    error = st.session_state.get("analysis_error")
    if error:
        with st.chat_message("assistant"):
            st.error(f"❌ {error}")


# ── 主渲染函数 ──────────────────────────────────────────

def _safe_pm() -> ProjectManager | None:
    """安全获取 ProjectManager（lazy 初始化，pm 可能为 None）"""
    try:
        pm = st.session_state.get("project_manager")
        if pm is None:
            pm = ProjectManager(HaGoKuConfig.load().output.project_dir)
            st.session_state.project_manager = pm
        return pm
    except Exception:
        return None


def render() -> None:
    _init_chat_state()
    pm = _safe_pm()
    config = HaGoKuConfig.load()

    # 每次 render 都检查后台线程状态（不只是启动时）
    if st.session_state.get("analysis_running"):
        _poll_and_update()

    # LLM 预检
    llm_cache = "_llm_health"
    if llm_cache not in st.session_state:
        from hagokyu.tools.health import check_llm
        result = check_llm(config)
        st.session_state[llm_cache] = result
    else:
        result = st.session_state[llm_cache]

    if not result.ok:
        st.warning(f"⚠️ **LLM 服务不可用**：{result.detail}")

    # ── CSS：三层布局 ──────────────────────────────────────
    st.html("""
    <style>
    /* 全局字体加大 */
    body, .stApp, section[data-testid="stMainBlockContainer"] {
        font-size: 20px !important;
    }
    section[data-testid="stMainBlockContainer"] .stText, section[data-testid="stMainBlockContainer"] p {
        font-size: 20px !important;
        line-height: 1.6 !important;
    }
    section[data-testid="stMainBlockContainer"] .stMarkdown {
        font-size: 20px !important;
    }
    section[data-testid="stMainBlockContainer"] label, section[data-testid="stMainBlockContainer"] .stSelectbox label,
    section[data-testid="stMainBlockContainer"] .stTextInput label {
        font-size: 18px !important;
    }
    /* 按钮：不要纯色填充，改成微透明底+细边框，参照终端/VS Code 风格 */
    /* 主按钮：低饱和青色底 + 淡边框，白色文字 */
    .stButton > button {
        background: rgba(8, 145, 178, 0.18) !important;
        color: #7dd3fc !important;
        border: 1px solid rgba(8, 145, 178, 0.55) !important;
        border-radius: 6px !important;
        font-weight: 600 !important;
        letter-spacing: 0.03em !important;
        box-shadow: none !important;
        font-size: 18px !important;
    }
    .stButton > button:hover {
        background: rgba(8, 145, 178, 0.30) !important;
        border-color: rgba(8, 145, 178, 0.9) !important;
        box-shadow: none !important;
    }
    /* 取消 Streamlit 默认按钮颜色覆盖 */
    .stButton > button:focus:not(:active) {
        background: rgba(8, 145, 178, 0.18) !important;
    }
    /* Layer 1: st.container(key="layer1") → 固定在顶部 */
    section[data-testid="stMainBlockContainer"] > div[data-testid="stVerticalBlock"]:first-child {
        position: sticky !important;
        top: 0 !important;
        z-index: 100 !important;
        background: #0a0e17 !important;
        border-bottom: 1px solid #21262d !important;
        padding-bottom: 0.5rem !important;
    }
    /* Layer 2: st.container(key="layer2") → 内容滚动 */
    section[data-testid="stMainBlockContainer"] > div[data-testid="stVerticalBlock"]:nth-child(2) {
        overflow-y: auto !important;
        max-height: calc(100vh - 190px) !important;
    }
    /* 分析页标题：VT323 display 字体 */
    section[data-testid="stMainBlockContainer"] h2 {
        font-family: 'VT323', monospace !important;
        font-size: 1.6rem !important;
        color: #00ffff !important;
        letter-spacing: 0.05em !important;
        text-shadow: 0 0 8px rgba(0,255,255,0.5) !important;
        margin-bottom: 0.5rem !important;
    }
    </style>
    """)

    # ── 轮询 + 分析完成处理（在 UI 渲染之前）────────────────
    _was_running = st.session_state.get("analysis_running", False)
    _has_result = st.session_state.get("analysis_result") or st.session_state.get("analysis_error")
    # 确保 selected 和 data_path 在任何代码路径都能访问
    selected = st.session_state.get("current_project", "")
    data_path = st.session_state.get("current_data_path", "")

    if _was_running:
        _poll_and_update()
        if st.session_state.get("analysis_running"):
            # 线程仍在运行 → rerun 继续刷新，下一次 render 会显示聊天事件
            st.rerun()
        # 刚结束：保留 events 让进度条显示 complete 阶段，再清理
    elif _has_result:
        # 分析结束 → 显示结果（不清理 events，进度条显示完成状态）
        _result = st.session_state.pop("analysis_result", None)
        _error = st.session_state.pop("analysis_error", None)
        for key in (
            "_analysis_thread", "_analysis_result_h", "_analysis_error_h",
            "_analysis_events_h", "_analysis_start", "analysis_data",
        ):
            st.session_state.pop(key, None)
        # analysis_events 保留，显示完成状态
        if _error:
            st.session_state.chat_messages.append({"role": "assistant", "content": f"❌ 分析出错：{_error}"})
        elif _result:
            status = _result.get("status", "") if isinstance(_result, dict) else ""
            if status == "scout_confirm":
                # Scout 暂停，等用户确认字段含义
                st.session_state.scout_confirm_data = _result
                st.session_state.awaiting_field_confirmation = True
                # 显示 Scout LLM 生成的消息
                message = _result.get("message", "")
                if message:
                    st.session_state.chat_messages.append({
                        "role": "assistant",
                        "agent": "scout",
                        "content": message,
                    })
                # 显示待确认的字段列表
                pending_items = _result.get("pending_items", [])
                if pending_items:
                    field_lines = ["**待确认的字段：**"]
                    for item in pending_items:
                        col = item.get("column", "")
                        desc = item.get("description", "")
                        field_lines.append(f"- **{col}**：{desc}")
                    st.session_state.chat_messages.append({
                        "role": "assistant",
                        "content": "\n".join(field_lines),
                    })
                st.rerun()
            elif status == "scout_done":
                # Scout 完成（legacy路径），显示 LLM 消息并进入清洗
                st.session_state.scout_done_data = _result
                scout_data = _result
                scout_ctx = None
                if scout_data:
                    try:
                        scout_ctx = DataContext.from_dict({
                            "data_path": st.session_state.get("current_data_path", ""),
                            "n_rows": scout_data.get("n_rows", 0),
                            "n_cols": scout_data.get("n_cols", 0),
                            "column_semantics": scout_data.get("column_semantics", []),
                            "quality_score": 0.5,
                            "column_descriptions": scout_data.get("column_descriptions", {}),
                        })
                    except Exception:
                        pass
                # 使用 LLM 生成的消息
                llm_message = _result.get("message", "数据理解完成，正在进入清洗阶段...")
                st.session_state.chat_messages.append({
                    "role": "assistant", "agent": "scout",
                    "content": llm_message,
                })
                _start_analysis(
                    data_path=st.session_state.get("current_data_path", ""),
                    query=st.session_state.get("current_query", ""),
                    project_name=st.session_state.current_project,
                    user_mode=config.user_mode.default_mode,
                    config=config,
                    phase="cleaning_first",
                    scout_context=scout_ctx,
                )
                st.rerun()
            elif status == "scout_next_step":
                # Scout 暂停在 next_step，等用户选择动作
                st.session_state.scout_next_step_data = _result
                st.session_state.awaiting_scout_next_step = True
                # 显示 Scout LLM 生成的消息
                message = _result.get("message", "")
                if message:
                    st.session_state.chat_messages.append({
                        "role": "assistant",
                        "agent": "scout",
                        "content": message,
                    })
                # 显示可选动作
                actions = _result.get("actions", [])
                if actions:
                    st.session_state.chat_messages.append({
                        "role": "assistant",
                        "content": f"**可选操作**：{', '.join(actions)}",
                    })
                st.rerun()
            elif status == "cleaner_strategy":
                # Cleaner 暂停，等用户确认清洗策略
                st.session_state.cleaning_strategy_data = _result
                st.session_state.awaiting_cleaning_confirmation = True
                # 显示清洗策略消息（来自 orchestrator 构造的消息）
                msg = _result.get("message", "数据清洗策略已生成，请确认。")
                st.session_state.chat_messages.append({
                    "role": "assistant",
                    "agent": "cleaner",
                    "content": msg,
                })
                st.rerun()
            elif status == "analyst_preliminary":
                st.session_state.analyst_preliminary_data = _result
                st.session_state.awaiting_analyst_confirmation = True
                msg = _result.get("message", "初步分析已完成，请确认分析方向。")
                st.session_state.chat_messages.append({"role": "assistant", "agent": "analyst", "content": msg})
            elif status in ("completed", "skipped", "ambiguous"):
                st.session_state.awaiting = None
                msg = _result.get("message") or _result.get("llm_response") or "处理完成。"
                st.session_state.chat_messages.append({"role": "assistant", "content": msg})
            else:
                st.session_state.awaiting = None
                msg = _result.get("message") or f"未知状态: {status}"
                st.session_state.chat_messages.append({"role": "assistant", "content": msg})

    # ── 第一层（固定）：标题 + 选择器 + 进度条 ──────────
    with st.container(key="layer1"):
        st.markdown("### 💬 互动分析")

        all_projects: list[str] = []
        if pm:
            try:
                all_projects = [p.name for p in pm.list()]
            except Exception:
                all_projects = []
        current_proj = st.session_state.get("current_project")
        if current_proj not in all_projects:
            # 尝试找第一个有数据文件的项目，避免默认选到空项目（如 "runs"）
            first_with_data = None
            if pm:
                for pname in all_projects:
                    try:
                        info = pm.info(pname)
                        if info and info.data_files:
                            first_with_data = pname
                            break
                    except Exception:
                        pass
            current_proj = first_with_data if first_with_data else all_projects[0] if all_projects else None
            st.session_state.current_project = current_proj

        col_proj, col_data, col_btn = st.columns([1, 1, 1])

        with col_proj:
            st.markdown("**📁 项目**")
            selected = st.selectbox(
                "项目",
                options=all_projects if all_projects else ["（请先创建项目）"],
                index=all_projects.index(current_proj) if current_proj in all_projects else 0,
                label_visibility="collapsed",
                disabled=not all_projects,
            )
            st.session_state.current_project = selected

        with col_data:
            st.markdown("**📂 数据**")
            files: list[str] = []
            data_path: str | None = None
            if selected and pm and selected != "（请先创建项目）":
                try:
                    info = pm.info(selected)
                    if info and info.data_files:
                        files = [f.name for f in info.data_files]
                except Exception:
                    pass
            selected_file = st.selectbox(
                "选择数据文件",
                files if files else ["（无）"],
                label_visibility="collapsed",
            )
            if selected_file and selected_file != "（无）" and pm:
                try:
                    data_path = str(pm.get_data_path(selected, selected_file))
                except Exception:
                    data_path = None
            st.session_state.current_data_path = data_path

        with col_btn:
            st.markdown("&nbsp;")
            has_file = bool(data_path)
            if st.button("🚀 启动分析", type="primary", use_container_width=True,
                         disabled=not has_file, help="选择项目和文件后启动"):
                st.session_state._launch_clicked = True

        # 进度条（第三行）
        running = st.session_state.get("analysis_running", False)
        events = st.session_state.get("analysis_events", [])
        _render_agent_pipeline(events, running)

    # 无项目时提示
    if not all_projects or selected == "（请先创建项目）":
        st.info("请先在「项目管理」创建项目和上传数据。")
        if st.button("➕ 去创建项目", type="primary", use_container_width=True):
            st.session_state.nav_page = "projects"
            st.rerun()
        st.stop()

    # 处理启动按钮：只跑 Scout，等用户输入问题
    if st.session_state.pop("_launch_clicked", False) and data_path:
        st.session_state.analysis_running = True
        st.session_state._analysis_start = time.time()
        st.session_state.analysis_events = []
        st.session_state._events_shown_count = 0
        _start_analysis(data_path=data_path, query="", project_name=selected,
                        user_mode=config.user_mode.default_mode, config=config, phase="scout_first")
        st.rerun()

    # ── 第二层（滚动）：聊天记录 ─────────────────────────
    with st.container(key="layer2"):
        _render_chat()


    # ── 第三层（固定）：输入框 ──────────────────────────
    if prompt := st.chat_input(key="chat_input"):
        st.session_state.chat_messages.append({"role": "user", "content": prompt})

        if not st.session_state.get("current_data_path"):
            st.session_state.chat_messages.append({
                "role": "assistant",
                "content": "⚠️ 请先选择数据文件。",
            })
            st.rerun()

        # Scout 字段确认模式：等用户确认/修正字段
        if st.session_state.get("awaiting_field_confirmation"):
            scout_confirm_data = st.session_state.get("scout_confirm_data", {})
            pending_items = scout_confirm_data.get("pending_items", [])

            # 解析用户输入
            confirmed = {}
            corrected = {}
            comments = {}

            prompt_lower = prompt.strip()
            if prompt_lower == "确认" or prompt_lower == "ok" or prompt_lower == "yes":
                # 用户确认所有字段
                for item in pending_items:
                    col = item.get("column", "")
                    desc = item.get("description", "")
                    if col:
                        confirmed[col] = desc
            else:
                # 解析 "column=description" 或 "column: description" 格式的修正
                import re
                # 匹配 field=value 或 field: value 格式
                pattern = r'([^=:]+)[:=]\s*(.+)'
                for match in re.finditer(pattern, prompt):
                    col = match.group(1).strip()
                    desc = match.group(2).strip()
                    if col and desc:
                        corrected[col] = desc

            # 调用 Orchestrator 继续 Scout 对话
            st.session_state.analysis_running = True
            st.session_state.analysis_events = []
            st.session_state._events_shown_count = 0
            st.session_state.awaiting_field_confirmation = False

            # 从 scout_confirm_data 中提取 context
            scout_data = scout_confirm_data.get("data", {})
            column_semantics = scout_data.get("column_semantics", [])
            column_descriptions = scout_data.get("column_descriptions", {})

            # 重建 Scout 可用的 context
            scout_context = {
                "data_path": st.session_state.get("current_data_path", ""),
                "n_rows": scout_confirm_data.get("data", {}).get("n_rows", 0),
                "n_cols": scout_confirm_data.get("data", {}).get("n_cols", 0),
                "column_semantics": column_semantics,
                "quality_score": scout_data.get("quality_score", 0.5),
                "missing_summary": {},
                "warnings": scout_data.get("warnings", []),
                "column_descriptions": column_descriptions,
            }

            # 构建 continue 调用的输入
            continue_input = {
                "agent": "scout",
                "phase": "confirm_fields",
                "data_path": st.session_state.get("current_data_path", ""),
                "query": scout_confirm_data.get("message", ""),
                "context": scout_context,
                "confirmed": confirmed,
                "corrected": corrected,
                "comments": comments,
            }

            def _do_respond():
                orch = Orchestrator(config)
                result = orch.respond(
                    user_input=continue_input,
                    project_name=st.session_state.current_project,
                )
                st.session_state._analysis_result_h = [result]
                st.session_state.analysis_running = False

            threading.Thread(target=_do_respond, daemon=True).start()
            st.rerun()
            return

        # Cleaner 策略确认模式
        if st.session_state.get("awaiting_cleaning_confirmation"):
            cleaning_data = st.session_state.get("cleaning_strategy_data", {})
            ops = cleaning_data.get("operations", [])
            confirmed_ops = cleaning_data.get("operations", [])

            prompt_lower = prompt.strip().lower()
            if prompt_lower == "确认" or prompt_lower == "ok" or prompt_lower == "yes":
                # 用户确认所有操作
                confirmed_ops = ops
            elif prompt_lower.startswith("跳过") or prompt_lower == "skip":
                # 用户跳过清洗
                confirmed_ops = []

            st.session_state.confirmed_cleaning_operations = confirmed_ops if confirmed_ops else None
            st.session_state.awaiting_cleaning_confirmation = False

            # 继续进入分析阶段
            scout_data = st.session_state.get("scout_done_data", {})
            scout_ctx = None
            if scout_data:
                try:
                    scout_ctx = DataContext.from_dict({
                        "data_path": st.session_state.get("current_data_path", ""),
                        "n_rows": scout_data.get("n_rows", 0),
                        "n_cols": scout_data.get("n_cols", 0),
                        "column_semantics": scout_data.get("column_semantics", []),
                        "quality_score": 0.5,
                        "column_descriptions": scout_data.get("column_descriptions", {}),
                    })
                except Exception:
                    pass

            st.session_state.analysis_running = True
            st.session_state.analysis_events = []
            st.session_state._events_shown_count = 0

            def _do_clean_then_analyse():
                result = _run_cleaning_and_analyst(
                    data_path=st.session_state.get("current_data_path", ""),
                    query=st.session_state.get("current_query", ""),
                    project_name=st.session_state.current_project,
                    user_mode=config.user_mode.default_mode,
                    config=config,
                    scout_context=scout_ctx,
                    cleaning_operations=st.session_state.confirmed_cleaning_operations,
                )
                st.session_state._analysis_result_h = [result]
                st.session_state.analysis_running = False

            threading.Thread(target=_do_clean_then_analyse, daemon=True).start()
            st.rerun()
            return

        # Analyst 初步发现确认模式
        if st.session_state.get("awaiting_analyst_confirmation"):
            prelim_data = st.session_state.get("analyst_preliminary_data", {})
            st.session_state.awaiting_analyst_confirmation = False

            # 用户确认了分析方向，继续运行完整分析
            scout_data = st.session_state.get("scout_done_data", {})
            scout_ctx = None
            if scout_data:
                try:
                    scout_ctx = DataContext.from_dict({
                        "data_path": st.session_state.get("current_data_path", ""),
                        "n_rows": scout_data.get("n_rows", 0),
                        "n_cols": scout_data.get("n_cols", 0),
                        "column_semantics": scout_data.get("column_semantics", []),
                        "quality_score": 0.5,
                        "column_descriptions": scout_data.get("column_descriptions", {}),
                    })
                except Exception:
                    pass

            st.session_state.analysis_running = True
            st.session_state.analysis_events = []
            st.session_state._events_shown_count = 0

            def _do_full_analysis():
                result = _start_full_pipeline(
                    data_path=st.session_state.get("current_data_path", ""),
                    query=st.session_state.get("current_query", ""),
                    project_name=st.session_state.current_project,
                    user_mode=config.user_mode.default_mode,
                    config=config,
                    scout_context=scout_ctx,
                    cleaning_operations=st.session_state.confirmed_cleaning_operations,
                )
                st.session_state._analysis_result_h = [result]
                st.session_state.analysis_running = False

            threading.Thread(target=_do_full_analysis, daemon=True).start()
            st.rerun()
            return

        # Scout next_step 确认模式
        if st.session_state.get("awaiting_scout_next_step"):
            next_step_data = st.session_state.get("scout_next_step_data", {})
            actions = next_step_data.get("actions", [])
            st.session_state.awaiting_scout_next_step = False

            prompt_lower = prompt.strip().lower()
            # 匹配用户选择的动作
            chosen_action = None
            for action in actions:
                if action in prompt or action.replace(" ", "") in prompt.replace(" ", ""):
                    chosen_action = action
                    break

            if not chosen_action:
                # 默认选择第一个动作
                chosen_action = actions[0] if actions else "进入清洗"

            # 从 next_step_data 中提取 context
            scout_data = next_step_data.get("data", {}).get("context", {})
            column_semantics = scout_data.get("column_semantics", [])
            column_descriptions = scout_data.get("column_descriptions", {})

            # 重建 Scout context
            scout_context = {
                "data_path": st.session_state.get("current_data_path", ""),
                "n_rows": next_step_data.get("data", {}).get("n_rows", 0),
                "n_cols": next_step_data.get("data", {}).get("n_cols", 0),
                "column_semantics": column_semantics,
                "quality_score": scout_data.get("quality_score", 0.5),
                "missing_summary": {},
                "warnings": scout_data.get("warnings", []),
                "column_descriptions": column_descriptions,
            }

            st.session_state.analysis_running = True
            st.session_state.analysis_events = []
            st.session_state._events_shown_count = 0

            def _do_scout_next():
                orch = Orchestrator(config)
                result = orch.respond(
                    user_input={
                        "agent": "scout",
                        "phase": "next_step",
                        "action": chosen_action,
                        "data": next_step_data.get("data", {}),
                    },
                    project_name=st.session_state.current_project,
                )
                st.session_state._analysis_result_h = [result]
                st.session_state.analysis_running = False

            threading.Thread(target=_do_scout_next, daemon=True).start()
            st.rerun()
            return

        # 全部交给 Scout 对话：Scout 是活的，自己决定什么时候问用户、什么时候继续
        # 不再是状态机驱动，而是 Scout Agent 自主对话
        if st.session_state.get("analysis_running"):
            # 分析进行中，不接受新输入
            st.session_state.chat_messages.append({
                "role": "assistant",
                "content": "⏳ 分析进行中，请稍候..."
            })
            st.rerun()
            return

        # 分析完成或空闲时，用户可以自由输入
        # 保存用户输入作为查询，然后启动完整 pipeline
        st.session_state.current_query = prompt
        _start_analysis(
            data_path=st.session_state.get("current_data_path", ""),
            query=prompt,
            project_name=selected,
            user_mode=config.user_mode.default_mode,
            config=config,
            phase="full",  # 直接跑完整 pipeline，不分段确认
        )
        st.rerun()


def _start_analysis(
    data_path: str,
    query: str,
    project_name: str | None,
    user_mode: str,
    config: HaGoKuConfig,
    phase: str = "full",
    scout_context: "DataContext | None" = None,
    cleaning_operations: list[dict[str, Any]] | None = None,
) -> None:
    """启动后台分析线程（不阻塞，轮询靠 rerun 驱动）

    phase="scout_first": 只跑 Scout，跑完等用户输入问题
    phase="cleaning_first": Scout（缓存）+ Cleaner（strategy_only），返回清洗策略
    phase="analyst_first": Scout（缓存）+ Cleaner（已确认）+ Analyst（preliminary）
    phase="full": 跑完整 pipeline
    """
    result_holder: list = []
    error_holder: list = []
    events_holder: list[Event] = []

    def run():
        try:
            orch = Orchestrator(config)

            def on_event(event: Event) -> None:
                # 只写线程安全的 list，不碰 st.session_state（会失败）
                events_holder.append(event)

            orch.event_bus.subscribe(on_event)
            try:
                from hagokyu.observability.display import TerminalDisplay
                orch.event_bus.unsubscribe(orch.display)
            except Exception:
                pass

            result = orch.run(
                data_path=data_path,
                query=query,
                project_name=project_name,
                user_mode=user_mode,
                phase=phase,
                scout_context=scout_context,
                cleaning_operations=cleaning_operations,
            )
            result_holder.append(result)
        except Exception as e:
            error_holder.append(str(e))

    thread = threading.Thread(target=run, daemon=True)
    st.session_state.analysis_running = True
    st.session_state.analysis_events = events_holder  # 复用线程的 list，append 直接生效
    st.session_state.analysis_result = None
    st.session_state.analysis_error = None
    st.session_state._analysis_thread = thread
    st.session_state._analysis_result_h = result_holder
    st.session_state._analysis_error_h = error_holder
    st.session_state._analysis_events_h = events_holder
    st.session_state._analysis_start = time.time()
    st.session_state._events_shown_count = 0
    thread.start()


def _run_cleaning_and_analyst(
    data_path: str,
    query: str,
    project_name: str | None,
    user_mode: str,
    config: HaGoKuConfig,
    scout_context: "DataContext | None" = None,
    cleaning_operations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """运行 Cleaner（已确认策略）+ Analyst（初步发现），返回 analyst_preliminary"""
    result_holder: list = []
    error_holder: list = []

    try:
        orch = Orchestrator(config)

        def on_event(event: Event) -> None:
            events = st.session_state.get("analysis_events", [])
            events.append(event)
            st.session_state.analysis_events = events

        orch.event_bus.subscribe(on_event)

        result = orch.run(
            data_path=data_path,
            query=query,
            project_name=project_name,
            user_mode=user_mode,
            phase="analyst_first",
            scout_context=scout_context,
            cleaning_operations=cleaning_operations,
        )
        result_holder.append(result)
    except Exception as e:
        error_holder.append(str(e))

    if error_holder:
        return {"status": "error", "message": error_holder[0]}
    return result_holder[0] if result_holder else {"status": "error", "message": "未知错误"}


def _start_full_pipeline(
    data_path: str,
    query: str,
    project_name: str | None,
    user_mode: str,
    config: HaGoKuConfig,
    scout_context: "DataContext | None" = None,
    cleaning_operations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """运行完整 pipeline（Scout + Cleaner + Analyst + Reporter），返回最终结果"""
    result_holder: list = []
    error_holder: list = []

    try:
        orch = Orchestrator(config)

        def on_event(event: Event) -> None:
            events = st.session_state.get("analysis_events", [])
            events.append(event)
            st.session_state.analysis_events = events

        orch.event_bus.subscribe(on_event)

        result = orch.run(
            data_path=data_path,
            query=query,
            project_name=project_name,
            user_mode=user_mode,
            phase="full",
            scout_context=scout_context,
            cleaning_operations=cleaning_operations,
        )
        result_holder.append(result)
    except Exception as e:
        error_holder.append(str(e))

    if error_holder:
        return {"status": "error", "message": error_holder[0]}
    return result_holder[0] if result_holder else {"status": "error", "message": "未知错误"}
