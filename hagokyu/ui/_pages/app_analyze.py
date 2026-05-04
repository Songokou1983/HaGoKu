"""HaGoKu Streamlit UI — 分析页面"""

from __future__ import annotations

import threading
import time

import streamlit as st

from hagokyu.config import HaGoKuConfig
from hagokyu.manager.orchestrator import Orchestrator
from hagokyu.observability.events import Event
from hagokyu.storage.project_manager import ProjectManager

# ── 工具函数 ────────────────────────────────────────────

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


def _render_agent_pipeline(events: list[Event], running: bool) -> None:
    """渲染 4 个 Agent 的流水线进度"""

    stage = "idle"
    stage_detail = ""

    if events:
        last = events[-1]
        etype_val = getattr(last, "event_type", None)
        etype = etype_val.value if etype_val else ""

        msg = (last.data.get("message", "") if hasattr(last, "data") else "") or ""

        if "scout" in etype or "data_loaded" in etype or "fields" in etype:
            stage, stage_pct = "scout", 25
        elif "clean" in etype or "outlier" in etype or "missing" in etype:
            stage, stage_pct = "cleaner", 50
        elif "analysis" in etype or "regression" in etype or "ttest" in etype or "correlation" in etype:
            stage, stage_pct = "analyst", 75
        elif "report" in etype or "generate" in etype:
            stage, stage_pct = "reporter", 95
        elif "complete" in etype or "finished" in etype:
            stage, stage_pct = "complete", 100
        else:
            stage_pct = 0
            stage_detail = msg[:80] if msg else etype

        if msg and not stage_detail:
            stage_detail = msg[:80]

    AGENTS = [
        ("scout",    "🔍", "🔍 Scout 侦察"),
        ("cleaner",  "🧹", "🧹 Cleaner 清洗"),
        ("analyst",  "📊", "📊 Analyst 分析"),
        ("reporter", "📋", "📋 Reporter 报告"),
    ]

    active_idx = next((i for i, (s, _, _) in enumerate(AGENTS) if s == stage), -1)
    if stage == "complete":
        completed_idx = len(AGENTS) - 1
    else:
        completed_idx = max(active_idx, 0)

    cols = st.columns(4)
    for i, (s, emoji, label) in enumerate(AGENTS):
        is_done = i < completed_idx
        is_active = i == active_idx and running

        border_color = "var(--hagokyu-accent)" if is_active else "var(--hagokyu-border)"
        bg = "rgba(34,211,238,0.08)" if is_active else "transparent"
        text_color = "var(--hagokyu-accent)" if is_active else ("var(--hagokyu-green)" if is_done else "var(--hagokyu-text-dim)")

        with cols[i]:
            st.markdown(
                f"<div style='text-align:center; padding:10px 4px; border-radius:8px; "
                f"border:1px solid {border_color}; background:{bg};'>"
                f"<div style='font-size:1.3rem;'>{'✅' if is_done else emoji if is_active else '⏳'}</div>"
                f"<div style='font-size:11px; color:{text_color}; font-weight:600; margin-top:4px;'>{label}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

    if stage_detail:
        st.caption(f"▸ {stage_detail}")

    if running:
        pct = max(10, stage_pct)
        agent_name = AGENTS[active_idx][2] if active_idx >= 0 else ""
        st.progress(pct / 100.0, text=f"{agent_name} 工作中...")


def _render_chat() -> None:
    """渲染聊天消息历史 + 输入框"""
    messages = st.session_state.get("chat_messages", [])

    # 消息历史
    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        if role == "user":
            with st.chat_message("user"):
                st.markdown(content)
        else:
            with st.chat_message("assistant"):
                if isinstance(content, dict):
                    # 分析结果卡片
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
                    else:
                        st.error(content.get("message", "分析未完成"))
                else:
                    st.markdown(content)

    # 实时事件流（作为 assistant 消息追加显示）
    if st.session_state.get("analysis_running"):
        evs = st.session_state.get("analysis_events", [])[-20:]
        if evs:
            latest = evs[-1]
            detail = ""
            if hasattr(latest, "data"):
                detail = latest.data.get("message", str(latest.data))[:200]
            elif hasattr(latest, "event_type"):
                detail = str(latest.event_type)
            if detail:
                with st.chat_message("assistant"):
                    st.markdown(f"⏳ {detail[:150]}...")

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
        st.warning(
            f"⚠️ **LLM 服务不可用**：{result.detail}\n\n"
            + "\n".join(f"• {s}" for s in result.suggestions)
        )

    # ── 顶部：项目选择 + 数据上传 ─────────────────────────
    all_projects = [p.name for p in pm.list()]
    current_proj = st.session_state.get("current_project")
    if current_proj not in all_projects:
        current_proj = None
        st.session_state.current_project = None

    # 演示数据预加载（已移除）

    with st.container():
        col_proj, col_data, col_btn = st.columns([1, 1, 1])

        with col_proj:
            st.markdown("**📁 项目**")
            selected = st.selectbox(
                "项目",
                options=all_projects,
                index=all_projects.index(current_proj) if current_proj in all_projects else 0,
                label_visibility="collapsed",
            )
            st.session_state.current_project = selected

        with col_data:
            st.markdown("**📂 数据**")
            files = []
            if selected and pm:
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
                data_path = str(pm.get_data_path(selected, selected_file))
            else:
                data_path = None
            st.session_state.current_data_path = data_path

        with col_btn:
            has_file = bool(data_path)
            if st.button("🚀 启动分析", type="primary", use_container_width=True,
                         disabled=not has_file,
                         help="选择项目和文件后启动分析"):
                st.session_state._launch_clicked = True

    st.divider()

    # 处理启动按钮点击
    if st.session_state.pop("_launch_clicked", False) and selected and data_path:
        _start_analysis(data_path=data_path, query="", project_name=selected,
                        user_mode=config.user_mode.default_mode, config=config)
        st.rerun()

    if not selected:
        st.info("请先选择一个项目，再开始分析。")
        if st.button("➕ 去创建项目", type="primary", use_container_width=True):
            st.session_state.nav_page = "projects"
            st.rerun()
        st.stop()

    # ── 中部：Agent 流水线 + 过程日志 ─────────────────────
    running = st.session_state.get("analysis_running", False)
    events = st.session_state.get("analysis_events", [])

    with st.container():
        st.markdown("**🔄 分析流水线**")
        _render_agent_pipeline(events, running)

    # 实时事件日志（展开显示）
    if events:
        with st.expander("📡 实时过程", expanded=False):
            for ev in events[-30:]:
                ev_type = getattr(ev, "event_type", "unknown")
                msg = ""
                if hasattr(ev, "data"):
                    msg = ev.data.get("message", "") if isinstance(ev.data, dict) else str(ev.data)
                if msg:
                    st.caption(f"`{ev_type}` {msg[:120]}")
                else:
                    st.caption(f"`{ev_type}`")

    st.divider()

    # ── 底部：对话窗口 ─────────────────────────────────────
    _render_chat()


    # chat 输入框
    if prompt := st.chat_input("输入分析问题，例如：哪个渠道 ROI 最高？", key="chat_input"):
        # 用户消息追加
        st.session_state.chat_messages.append({"role": "user", "content": prompt})
        if not st.session_state.get("current_data_path"):
            st.session_state.chat_messages.append({
                "role": "assistant",
                "content": "⚠️ 请先在顶部上传或选择数据文件。",
            })
            st.rerun()

        # 启动分析
        _start_analysis(
            data_path=st.session_state.get("current_data_path"),
            query=prompt,
            project_name=selected,
            user_mode=config.user_mode.default_mode,
            config=config,
        )
        st.rerun()

    # ── 分析进行中：非阻塞轮询（每次 rerun 检查一次）────────
    if st.session_state.get("analysis_running"):
        thread = st.session_state.get("_analysis_thread")
        if thread and not thread.is_alive():
            # 线程结束：收集结果
            st.session_state.analysis_result = st.session_state.get("_analysis_result_h", [{}])[0]
            st.session_state.analysis_error = st.session_state.get("_analysis_error_h", [None])[0]
            evs = st.session_state.get("_analysis_events_h", [])
            st.session_state.analysis_events = evs[-500:]
            st.session_state.analysis_running = False
            st.rerun()
        else:
            # 线程仍在运行：同步最新事件，追加到显示队列
            evs = st.session_state.get("_analysis_events_h", [])
            st.session_state.analysis_events = evs[-50:]
            waited = time.time() - st.session_state.get("_analysis_start", time.time())
            if waited >= 300:
                st.session_state.analysis_running = False
                st.session_state.analysis_error = "分析超时（5分钟）"
                st.rerun()
            else:
                st.rerun()

    # ── 分析完成后的处理 ───────────────────────────────────
    if not running and (st.session_state.get("analysis_result") or st.session_state.get("analysis_error")):
        result = st.session_state.pop("analysis_result", None)
        error = st.session_state.pop("analysis_error", None)
        for key in ("_analysis_thread_started", "_analysis_thread",
                    "_analysis_result_h", "_analysis_error_h",
                    "_analysis_events_h", "_analysis_start",
                    "analysis_data", "analysis_running",
                    "analysis_events"):
            st.session_state.pop(key, None)
    
        if error:
            st.session_state.chat_messages.append({"role": "assistant", "content": f"❌ 分析出错：{error}"})
        elif result:
            st.session_state.chat_messages.append({"role": "assistant", "content": result})
        st.rerun()


def _start_analysis(
    data_path: str,
    query: str,
    project_name: str | None,
    user_mode: str,
    config: HaGoKuConfig,
) -> None:
    """启动后台分析线程（不阻塞，轮询靠 rerun 驱动）"""
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
            )
            result_holder.append(result)
        except Exception as e:
            error_holder.append(str(e))

    thread = threading.Thread(target=run, daemon=True)
    st.session_state.analysis_running = True
    st.session_state.analysis_start = time.time()
    st.session_state.analysis_events = []
    st.session_state.analysis_result = None
    st.session_state.analysis_error = None
    st.session_state._analysis_thread = thread
    st.session_state._analysis_result_h = result_holder
    st.session_state._analysis_error_h = error_holder
    st.session_state._analysis_events_h = events_holder
    st.session_state._analysis_start = time.time()
    thread.start()
