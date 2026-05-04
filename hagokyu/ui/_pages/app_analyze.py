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
    # Scout 字段确认
    if "awaiting_field_confirmation" not in st.session_state:
        st.session_state.awaiting_field_confirmation = False
    if "scout_done_data" not in st.session_state:
        st.session_state.scout_done_data = None
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





def _render_agent_pipeline(events: list[Event], running: bool) -> None:
    """一行进度条 + 4 个阶段标签"""

    # 根据最后一个事件判断当前进度
    pct = 0
    stage_label = "等待开始"
    if events:
        last = events[-1]
        etype_val = getattr(last, "event_type", None)
        etype = etype_val.value if etype_val else ""

        if "complete" in etype or "finished" in etype:
            pct, stage_label = 100, "完成"
        elif "report" in etype or "generate" in etype:
            pct, stage_label = 80, "生成报告"
        elif "analysis" in etype or "regression" in etype or "ttest" in etype or "correlation" in etype:
            pct, stage_label = 60, "分析中"
        elif "clean" in etype or "outlier" in etype or "missing" in etype:
            pct, stage_label = 40, "清洗数据"
        elif "scout" in etype or "data_loaded" in etype or "fields" in etype:
            pct, stage_label = 20, "识别字段"

    labels = ["Scout", "Cleaner", "Analyst", "Reporter"]
    active_idx = min(pct // 25, 3)  # 0-19:0, 20-39:1, 40-59:2, 60-79:3
    if pct == 100:
        active_idx = 3

    cols = st.columns([2, 1, 1, 1, 1, 2])
    with cols[0]:
        st.markdown(f"<span style='color:#6e7681;font-family:Space Mono,monospace;font-size:11px;'>{stage_label}</span>", unsafe_allow_html=True)
    with cols[1]:
        st.progress(pct / 100.0)
    with cols[2]:
        for i, lbl in enumerate(labels):
            is_done = i < active_idx
            is_active = i == active_idx and running and pct < 100
            color = "#00ff41" if is_done else ("#00ffff" if is_active else "#3d4450")
            dot = "●" if is_active else ("○" if is_done else "○")
            st.markdown(f"<span style='color:{color};font-size:9px;font-family:Space Mono,monospace;'>{dot} {lbl}</span>", unsafe_allow_html=True)


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

    # 实时事件流（逐条显示，只显示新事件防重复）
    if st.session_state.get("analysis_running"):
        evs = st.session_state.get("analysis_events", [])
        shown_count = st.session_state.get("_events_shown_count", 0)
        new_evs = evs[shown_count:]
        for ev in new_evs:
            ev_str = str(getattr(ev, "event_type", ""))
            if "scout" in ev_str or "data_loaded" in ev_str or "fields" in ev_str:
                agent, color, label = "scout", AGENT_COLOR["scout"], AGENT_LABEL["scout"]
            elif "clean" in ev_str or "outlier" in ev_str or "missing" in ev_str:
                agent, color, label = "cleaner", AGENT_COLOR["cleaner"], AGENT_LABEL["cleaner"]
            elif "analysis" in ev_str or "regression" in ev_str or "ttest" in ev_str:
                agent, color, label = "analyst", AGENT_COLOR["analyst"], AGENT_LABEL["analyst"]
            elif "report" in ev_str or "generate" in ev_str:
                agent, color, label = "reporter", AGENT_COLOR["reporter"], AGENT_LABEL["reporter"]
            else:
                continue
            detail = ""
            if hasattr(ev, "data") and isinstance(ev.data, dict):
                detail = ev.data.get("thought", ev.data.get("message", ""))
            if detail:
                with st.chat_message("assistant"):
                    st.markdown(
                        f'<span style="color:{color};font-family:Space Mono,monospace;">'
                        f'**{label}:**</span> ⏳ {detail[:150]}',
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

    if _was_running:
        _poll_and_update()
        if st.session_state.get("analysis_running"):
            st.rerun()  # 仍在运行 → 继续刷新 UI
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
            if status == "scout_done":
                # Scout 完成：Scout 在 Chat 里说字段理解，设置等待用户回复
                st.session_state.awaiting = "field_confirmation"
                st.session_state.scout_done_data = _result
                msg = _scout_field_message(_result)
                st.session_state.chat_messages.append({"role": "assistant", "agent": "scout", "content": msg})
            elif status == "cleaner_strategy":
                # Cleaner 完成：Cleaner 在 Chat 里说策略，设置等待用户回复
                st.session_state.awaiting = "cleaning_confirmation"
                st.session_state.cleaning_strategy_data = _result
                msg = _cleaner_strategy_message(_result)
                st.session_state.chat_messages.append({"role": "assistant", "agent": "cleaner", "content": msg})
            elif status == "analyst_preliminary":
                # Analyst 完成：Analyst 在 Chat 里说初步发现，设置等待用户回复
                st.session_state.awaiting = "analyst_confirmation"
                st.session_state.analyst_preliminary_data = _result
                msg = _analyst_finding_message(_result)
                st.session_state.chat_messages.append({"role": "assistant", "agent": "analyst", "content": msg})
            elif status in ("completed", "skipped", "ambiguous"):
                st.session_state.awaiting = None
                st.session_state.chat_messages.append({"role": "assistant", "content": _result})
            else:
                st.session_state.awaiting = None
                st.session_state.chat_messages.append({"role": "assistant", "content": _result})

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
            current_proj = None
            st.session_state.current_project = None

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
        _start_analysis(data_path=data_path, query="", project_name=selected,
                        user_mode=config.user_mode.default_mode, config=config, phase="scout_first")
        _poll_and_update()
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

        awaiting = st.session_state.get("awaiting")
        data_path = st.session_state.get("current_data_path", "")

        # ── 阶段 1：等用户确认字段理解 ────────────────────
        if awaiting == "field_confirmation":
            scout_data = st.session_state.get("scout_done_data", {})
            text = prompt.lower().strip()
            corrections = {}

            # 检测用户是否有修正意图
            if any(k in text for k in ["不对", "错了", "不是", "改", "修正", "更正"]):
                st.session_state.chat_messages.append({
                    "role": "assistant", "agent": "scout",
                    "content": "好的，请告诉我每个字段正确的理解是什么，我会记录下来。"
                })
                st.session_state.awaiting = "field_correction"
                st.rerun()

            # 用户确认字段 → 进入清洗阶段
            # 构建 Scout 上下文
            scout_ctx = None
            if scout_data:
                try:
                    scout_ctx = DataContext.from_dict({
                        "data_path": data_path,
                        "n_rows": scout_data.get("n_rows", 0),
                        "n_cols": scout_data.get("n_cols", 0),
                        "column_semantics": [],
                        "quality_score": 0.5,
                        "column_descriptions": scout_data.get("column_descriptions", {}),
                    })
                except Exception:
                    scout_ctx = None

            st.session_state.awaiting = None
            # Scout 复述理解，然后进入清洗阶段
            st.session_state.chat_messages.append({
                "role": "assistant", "agent": "scout",
                "content": f"好的，字段理解已确认。我现在去检测数据质量，制定清洗方案，请稍候..."
            })
            _start_analysis(
                data_path=data_path,
                query=prompt,  # 用户的问题
                project_name=selected,
                user_mode=config.user_mode.default_mode,
                config=config,
                phase="cleaning_first",
                scout_context=scout_ctx,
            )
            st.rerun()

        # ── 阶段 1b：等用户修正字段 ───────────────────
        elif awaiting == "field_correction":
            st.session_state.chat_messages.append({
                "role": "assistant", "agent": "scout",
                "content": "好的，字段理解已更新。我现在开始检测数据质量，请稍候..."
            })
            scout_data = st.session_state.get("scout_done_data", {})
            scout_ctx = None
            if scout_data:
                try:
                    scout_ctx = DataContext.from_dict({
                        "data_path": data_path,
                        "n_rows": scout_data.get("n_rows", 0),
                        "n_cols": scout_data.get("n_cols", 0),
                        "column_semantics": [],
                        "quality_score": 0.5,
                        "column_descriptions": scout_data.get("column_descriptions", {}),
                    })
                except Exception:
                    scout_ctx = None
            st.session_state.awaiting = None
            _start_analysis(
                data_path=data_path,
                query=prompt,
                project_name=selected,
                user_mode=config.user_mode.default_mode,
                config=config,
                phase="cleaning_first",
                scout_context=scout_ctx,
            )
            st.rerun()

        # ── 阶段 2：等用户确认清洗策略 ────────────────
        elif awaiting == "cleaning_confirmation":
            strategy_data = st.session_state.get("cleaning_strategy_data", {})
            text = prompt.lower().strip()
            ops = strategy_data.get("operations", [])

            # 检测否定/调整意图
            if any(k in text for k in ["不对", "错了", "不改", "不洗", "跳过", "直接分析", "不需要"]):
                st.session_state.chat_messages.append({
                    "role": "assistant", "agent": "cleaner",
                    "content": "好的，跳过清洗，直接用原始数据进行分析。"
                })
                ops = []  # 空操作 = 不清洗
            else:
                st.session_state.chat_messages.append({
                    "role": "assistant", "agent": "cleaner",
                    "content": f"好的，清洗方案已确认（{len(ops)} 个操作）。我现在开始初步分析，请稍候..."
                })

            scout_data = st.session_state.get("scout_done_data", {})
            scout_ctx = None
            if scout_data:
                try:
                    scout_ctx = DataContext.from_dict({
                        "data_path": data_path,
                        "n_rows": scout_data.get("n_rows", 0),
                        "n_cols": scout_data.get("n_cols", 0),
                        "column_semantics": [],
                        "quality_score": 0.5,
                        "column_descriptions": scout_data.get("column_descriptions", {}),
                    })
                except Exception:
                    scout_ctx = None

            st.session_state.awaiting = None
            _start_analysis(
                data_path=data_path,
                query=prompt,
                project_name=selected,
                user_mode=config.user_mode.default_mode,
                config=config,
                phase="analyst_first",
                scout_context=scout_ctx,
                cleaning_operations=ops if ops else None,
            )
            st.rerun()

        # ── 阶段 3：等用户确认分析方向 ────────────────
        elif awaiting == "analyst_confirmation":
            st.session_state.chat_messages.append({
                "role": "assistant", "agent": "analyst",
                "content": "好的，分析方向已确认。我现在完善分析并生成完整报告，请稍候..."
            })
            scout_data = st.session_state.get("scout_done_data", {})
            scout_ctx = None
            if scout_data:
                try:
                    scout_ctx = DataContext.from_dict({
                        "data_path": data_path,
                        "n_rows": scout_data.get("n_rows", 0),
                        "n_cols": scout_data.get("n_cols", 0),
                        "column_semantics": [],
                        "quality_score": 0.5,
                        "column_descriptions": scout_data.get("column_descriptions", {}),
                    })
                except Exception:
                    scout_ctx = None

            st.session_state.awaiting = None
            _start_analysis(
                data_path=data_path,
                query=prompt,
                project_name=selected,
                user_mode=config.user_mode.default_mode,
                config=config,
                phase="full",
                scout_context=scout_ctx,
            )
            st.rerun()

        # ── 自由输入（未在任何等待阶段）────────────────
        else:
            # 正常对话模式：直接启动完整分析
            _start_analysis(
                data_path=data_path,
                query=prompt,
                project_name=selected,
                user_mode=config.user_mode.default_mode,
                config=config,
                phase="cleaning_first",  # 从清洗开始（Scout 缓存由 orchestrator 处理）
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
    st.session_state.analysis_events = []
    st.session_state.analysis_result = None
    st.session_state.analysis_error = None
    st.session_state._analysis_thread = thread
    st.session_state._analysis_result_h = result_holder
    st.session_state._analysis_error_h = error_holder
    st.session_state._analysis_events_h = events_holder
    st.session_state._analysis_start = time.time()
    st.session_state._events_shown_count = 0
    thread.start()
