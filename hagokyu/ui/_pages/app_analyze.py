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
    """一行 4 格进度指示器（紧凑，无多余行）"""

    stage = "idle"
    stage_pct = 0

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

    AGENTS = [
        ("scout",    "🔍 Scout"),
        ("cleaner",  "🧹 Cleaner"),
        ("analyst",  "📊 Analyst"),
        ("reporter", "📋 Reporter"),
    ]

    active_idx = next((i for i, (s, _) in enumerate(AGENTS) if s == stage), -1)
    completed_idx = len(AGENTS) - 1 if stage == "complete" else active_idx

    cols = st.columns(4)
    for i, (s, label) in enumerate(AGENTS):
        is_done = i < completed_idx
        is_active = i == active_idx and running
        border = "var(--hagokyu-accent)" if is_active else "var(--hagokyu-border)"
        bg = "rgba(34,211,238,0.12)" if is_active else "transparent"
        color = "var(--hagokyu-accent)" if is_active else ("var(--hagokyu-green)" if is_done else "var(--hagokyu-text-dim)")
        icon = "✅" if is_done else ("🔄" if is_active else "⏳")
        with cols[i]:
            st.markdown(
                f"<div style='text-align:center; padding:4px 2px; border-radius:6px; "
                f"border:1px solid {border}; background:{bg};'>"
                f"<div style='font-size:0.85rem;'>{icon}</div>"
                f"<div style='font-size:10px; color:{color}; font-weight:600;'>{label}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )


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
                    elif status == "skipped":
                        # 问题与数据无关，LLM 直接回答
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
        st.warning(f"⚠️ **LLM 服务不可用**：{result.detail}")

    # ── 布局 CSS：三层固定/滚动/固定 ────────────────────────
    st.markdown("""
    <style>
    /* Layer 1: 固定在顶部 */
    .layer-header {
        position: sticky;
        top: 0;
        z-index: 100;
        background: #0a0e17;
        padding: 0.5rem 0 0.5rem;
        border-bottom: 1px solid #30363d;
    }
    /* Layer 2: 滚动区域 */
    .layer-chat {
        height: calc(100vh - 220px);
        overflow-y: auto;
        padding: 0.5rem 0;
    }
    /* Layer 3: 固定在底部 */
    .layer-input {
        position: fixed;
        bottom: 0;
        left: 0;
        right: 0;
        z-index: 100;
        background: #0a0e17;
        padding: 0.75rem 1rem;
        border-top: 1px solid #30363d;
    }
    /* 隐藏 Streamlit 默认 chat_input 的 fixed 行为 */
    section[data-testid="stChatInput"] {
        position: relative !important;
        bottom: auto !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # ── 第一层：标题 + 选择器 + 启动按钮 + 进度条 ──────────
    st.markdown('<div class="layer-header">', unsafe_allow_html=True)

    st.markdown("## 💬 互动分析（选择项目和数据后，输入分析问题启动）")

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

    st.markdown('</div>', unsafe_allow_html=True)  # 关闭 Layer 1

    # 无项目时提示
    if not all_projects or selected == "（请先创建项目）":
        st.info("请先在「项目管理」创建项目和上传数据。")
        if st.button("➕ 去创建项目", type="primary", use_container_width=True):
            st.session_state.nav_page = "projects"
            st.rerun()
        st.stop()

    # 处理启动按钮
    if st.session_state.pop("_launch_clicked", False) and data_path:
        _start_analysis(data_path=data_path, query="", project_name=selected,
                        user_mode=config.user_mode.default_mode, config=config)
        st.rerun()

    # ── 第二层：滚动聊天区域 ──────────────────────────────
    st.markdown('<div class="layer-chat">', unsafe_allow_html=True)
    _render_chat()
    st.markdown('</div>', unsafe_allow_html=True)  # 关闭 Layer 2

    # ── 第三层：固定输入框 ────────────────────────────────
    st.markdown('<div class="layer-input">', unsafe_allow_html=True)
    if prompt := st.chat_input("输入分析问题，例如：哪个渠道 ROI 最高？", key="chat_input"):
        st.session_state.chat_messages.append({"role": "user", "content": prompt})
        if not st.session_state.get("current_data_path"):
            st.session_state.chat_messages.append({
                "role": "assistant",
                "content": "⚠️ 请先选择数据文件。",
            })
            st.rerun()
        _start_analysis(
            data_path=st.session_state.get("current_data_path"),
            query=prompt,
            project_name=selected,
            user_mode=config.user_mode.default_mode,
            config=config,
        )
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)  # 关闭 Layer 3

    # ── 轮询逻辑（不渲染 UI，只更新状态）────────────────
    if st.session_state.get("analysis_running"):
        thread = st.session_state.get("_analysis_thread")
        if thread and not thread.is_alive():
            _results = st.session_state.get("_analysis_result_h", [])
            st.session_state.analysis_result = _results[0] if _results else None
            _errors = st.session_state.get("_analysis_error_h", [])
            st.session_state.analysis_error = _errors[0] if _errors else None
            evs = st.session_state.get("_analysis_events_h", [])
            st.session_state.analysis_events = evs[-500:]
            st.session_state.analysis_running = False
            st.rerun()
        else:
            evs = st.session_state.get("_analysis_events_h", [])
            st.session_state.analysis_events = evs[-50:]
            waited = time.time() - st.session_state.get("_analysis_start", time.time())
            if waited >= 300:
                st.session_state.analysis_running = False
                st.session_state.analysis_error = "分析超时（5分钟）"
                st.rerun()
            else:
                st.rerun()

    if not running and (st.session_state.get("analysis_result") or st.session_state.get("analysis_error")):
        result = st.session_state.pop("analysis_result", None)
        error = st.session_state.pop("analysis_error", None)
        for key in (
            "_analysis_thread_started", "_analysis_thread",
            "_analysis_result_h", "_analysis_error_h",
            "_analysis_events_h", "_analysis_start",
            "analysis_data", "analysis_running",
            "analysis_events",
        ):
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
    st.session_state.analysis_events = []
    st.session_state.analysis_result = None
    st.session_state.analysis_error = None
    st.session_state._analysis_thread = thread
    st.session_state._analysis_result_h = result_holder
    st.session_state._analysis_error_h = error_holder
    st.session_state._analysis_events_h = events_holder
    st.session_state._analysis_start = time.time()
    thread.start()
