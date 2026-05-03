"""HaGoKu Streamlit UI — 分析页面（含实时事件流）"""

from __future__ import annotations

import tempfile
import threading
import time
from pathlib import Path

import streamlit as st

from hagokyu.ui.components.event_log import render_event_log
from hagokyu.ui.components.file_uploader import (
    cleanup_session_temp,
    render_upload_tab,
)
from hagokyu.config import HaGoKuConfig
from hagokyu.manager.orchestrator import Orchestrator
from hagokyu.observability.events import Event
from hagokyu.storage.project_manager import ProjectManager

# 内置演示数据集
DEMO_DATASETS = {
    "ad_campaign": {
        "name": "📢 广告投放数据",
        "query": "哪个广告渠道的 ROI 最高？各渠道转化率有何差异？",
        "file": "demo_ad_campaign.csv",
    },
    "conversion": {
        "name": "🔽 转化漏斗数据",
        "query": "分析各渠道的转化漏斗，哪个环节流失最严重？",
        "file": "demo_conversion.csv",
    },
    "user_cohort": {
        "name": "👤 用户队列数据",
        "query": "各渠道用户质量和价值有什么差异？哪些是高价值用户群？",
        "file": "demo_user_cohort.csv",
    },
}


def _get_demo_path(name: str) -> Path | None:
    """解析演示数据路径（包内/本地两种模式）"""
    filename = DEMO_DATASETS[name]["file"]
    try:
        import hagokyu
        pkg_root = Path(hagokyu.__file__).parent.parent
        path = pkg_root / "examples" / filename
        if path.exists():
            return path
    except Exception:
        pass
    # 本地源码
    local = Path(__file__).parent.parent.parent / "examples" / filename
    if local.exists():
        return local
    return None


def _launch_demo(name: str) -> None:
    """加载演示数据并跳转到分析页面"""
    info = DEMO_DATASETS[name]
    src = _get_demo_path(name)
    if src is None:
        st.error(f"找不到演示数据: {name}")
        return
    suffix = src.suffix
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(src.read_bytes())
        tmp_path = f.name
    st.session_state._demo_file = tmp_path
    st.session_state._demo_name = info["name"]
    st.session_state._demo_query = info["query"]
    st.session_state.nav_page = "analyze"
    st.rerun()


def render() -> None:
    cleanup_session_temp()
    pm: ProjectManager = st.session_state.project_manager
    config = HaGoKuConfig.load()

    # ── LLM 连接预检（会话内只检查一次）───────────────────
    llm_cache_key = "_llm_health"
    cached = st.session_state.get(llm_cache_key)
    if cached is None:
        from hagokyu.tools.health import check_llm
        result = check_llm(config)
        st.session_state[llm_cache_key] = result
    else:
        result = cached

    if not result.ok:
        st.warning(
            f"⚠️ **LLM 服务不可用**：{result.detail}\n\n"
            + "\n".join(f"• {s}" for s in result.suggestions)
            + f"\n\n💡 运行 `hagokyu doctor` 检查，或配置正确的 LLM 地址（当前: `{config.llm.base_url}`）"
        )

    st.title("📊 数据分析")

    # ── 演示数据预加载（从项目页点击演示按钮触发）──────────
    demo_path = st.session_state.pop("_demo_file", None)
    demo_name = st.session_state.pop("_demo_name", None)
    demo_query = st.session_state.pop("_demo_query", None)

    # ── 数据来源选择 ────────────────────────────────────────
    # ── 强制项目选择（必须先选项目）────────────────────────
    all_projects = [p.name for p in pm.list()]
    current_proj = st.session_state.get("current_project")
    if current_proj not in all_projects:
        current_proj = None
        st.session_state.current_project = None

    selected = st.selectbox(
        "📁 请先选择一个项目",
        options=all_projects,
        index=all_projects.index(current_proj) if current_proj in all_projects else 0,
    )
    st.session_state.current_project = selected

    if not selected:
        st.info("请先选择一个项目，或直接体验演示数据。")
        c1, c2 = st.columns(2)
        if c1.button("➕ 去创建项目", type="primary", use_container_width=True):
            st.session_state.nav_page = "projects"
            st.rerun()
        if c2.button("🚀 快速体验", use_container_width=True):
            _launch_demo("ad_campaign")
        st.stop()

    st.divider()

    col_data, col_query = st.columns([1, 2])

    with col_data:
        st.markdown("### 1️⃣ 上传数据")
        data_path = render_upload_tab(
            demo_path=demo_path,
            demo_name=demo_name,
            project_name=selected,
            pm=pm,
        )

    with col_query:
        st.markdown("### 2️⃣ 分析问题")
        # 直接用 demo_query 预填（不清 session_state，避免重复覆盖）
        query = st.text_area(
            "你想分析什么？",
            value=st.session_state.get("query_input", demo_query or ""),
            placeholder="例如：哪个渠道roi最高？\n转化漏斗分析\n两组有差异吗？\n哪些因素影响利润？",
            height=120,
            label_visibility="collapsed",
        )

        # ── 用户模式选择 ─────────────────────────────────────
        st.markdown("**报告详细度：**")
        mode_labels = {
            "quick": "⚡ 简洁（人话摘要，适合快速浏览）",
            "standard": "📋 标准（人话+数学细节）",
            "expert": "🧪 详细（完整统计证据链）",
        }
        mode_options = list(mode_labels.keys())
        default_idx = mode_options.index(config.user_mode.default_mode) \
            if config.user_mode.default_mode in mode_options else 1
        selected_mode = st.radio(
            "报告模式",
            options=mode_options,
            format_func=lambda x: mode_labels[x],
            index=default_idx,
            label_visibility="collapsed",
            horizontal=True,
        )

        # 快捷问题按钮
        st.markdown("**快捷问题：**")
        quick_questions = [
            ("📈 ROI分析", "哪个渠道roi最高"),
            ("🔬 A/B测试", "两组有差异吗"),
            ("📊 转化漏斗", "转化漏斗分析"),
            ("🔗 相关性", "收入和广告费相关吗"),
            ("📉 回归分析", "哪些因素影响利润"),
            ("💰 LTV分析", "用户值多少钱"),
        ]
        cols = st.columns(3)
        for i, (label, q) in enumerate(quick_questions):
            if cols[i % 3].button(label, use_container_width=True):
                st.session_state.query_input = q
                st.rerun()

    st.divider()

    # ── 开始分析按钮 ─────────────────────────────────────────
    query_val = st.session_state.get("query_input", "")
    can_run = bool(data_path and query_val)
    col_btn, col_status = st.columns([1, 3])

    with col_btn:
        run_clicked = st.button(
            "🚀 开始分析",
            type="primary",
            disabled=not can_run,
            use_container_width=True,
        )

    if not data_path:
        st.warning("请先选择或上传数据文件")
    if not query_val:
        st.info("请输入分析问题，或点击快捷问题")

    # ── 分析执行（非阻塞模式）─────────────────────────────────
    #
    # 设计原则：Streamlit 脚本每次 rerun 从头执行，不能用 while+sleep 阻塞事件循环。
    # 策略：线程对象存入 session_state，rerun 时检查 .is_alive() 判断状态。
    # 用户点击 → 启动线程 → 立即 rerun → 展示进度 → 完成后展示结果
    #
    MAX_WAIT = 300  # 最多等 5 分钟

    if run_clicked and data_path and query:
        # 启动分析：存入 session_state，线程持有 data_path/holders 引用
        st.session_state.analysis_data = {
            "data_path": data_path,
            "query": query_val,
            "project_name": st.session_state.get("current_project"),
            "user_mode": selected_mode,
        }
        st.session_state.analysis_result = None
        st.session_state.analysis_error = None
        st.session_state.analysis_running = True
        st.session_state.analysis_start = time.time()
        st.session_state.analysis_events = []
        st.rerun()  # 立即 rerun，不阻塞

    # 分析进行中：启动后台线程（rerun 时通过 analysis_running 标志触发）
    if st.session_state.get("analysis_running"):
        ad = st.session_state.get("analysis_data", {})
        if not st.session_state.get("_analysis_thread_started"):
            # 首次 rerun：启动线程，holders 通过闭包引用传递
            result_holder: list = []
            error_holder: list = []
            events_holder: list[Event] = []

            def run():
                try:
                    orch = Orchestrator(config)
                    def on_event(event: Event) -> None:
                        events_holder.append(event)
                    orch.event_bus.subscribe(on_event)
                    from hagokyu.observability.display import TerminalDisplay
                    orch.event_bus.unsubscribe(orch.display)
                    result = orch.run(
                        data_path=ad["data_path"],
                        query=ad["query"],
                        project_name=ad.get("project_name"),
                        user_mode=ad.get("user_mode", "standard"),
                    )
                    result_holder.append(result)
                except Exception as e:
                    error_holder.append(str(e))

            thread = threading.Thread(target=run, daemon=True)
            st.session_state._analysis_thread = thread
            st.session_state._analysis_result_h = result_holder
            st.session_state._analysis_error_h = error_holder
            st.session_state._analysis_events_h = events_holder
            st.session_state._analysis_thread_started = True
            thread.start()

        # rerun 时：检查线程是否结束，从 holders 读结果
        thread = st.session_state.get("_analysis_thread")
        if thread and not thread.is_alive():
            st.session_state.analysis_result = st.session_state.get("_analysis_result_h", [{}])[0]
            st.session_state.analysis_error = st.session_state.get("_analysis_error_h", [None])[0]
            # 最多保留最近 500 条事件，防止内存无限增长
            all_events = st.session_state.get("_analysis_events_h", [])
            st.session_state.analysis_events = all_events[-500:]
            st.session_state.analysis_running = False

        # 显示进度
        waited = time.time() - st.session_state.get("analysis_start", time.time())
        progress_pct = min(waited / 60, 0.9)
        st.progress(progress_pct, text=f"分析中... ({int(waited)}s)")

        # 实时事件流
        evs = st.session_state.get("analysis_events", [])[-50:]  # 显示最近 50 条
        if evs:
            with st.expander("📡 实时事件流", expanded=True):
                from hagokyu.ui.components.event_log import render_event_log
                render_event_log(evs[-50:])

        if waited >= MAX_WAIT:
            st.session_state.analysis_running = False
            st.session_state.analysis_error = "分析超时（5分钟），请尝试更小规模的数据"
            st.warning(st.session_state.analysis_error)
        else:
            st.info(f"分析进行中... ({int(waited)}s)")
            st.rerun()

    # 分析完成：展示结果
    if not st.session_state.get("analysis_running"):
        result = st.session_state.get("analysis_result")
        error = st.session_state.get("analysis_error")

        if error:
            st.error(f"分析出错: {error}")
        elif result:
            if result.get("status") == "completed":
                dur = result.get("duration_ms", 0) / 1000
                c1, c2 = st.columns(2)
                c1.success(f"✅ 分析完成！总耗时: {dur:.1f}s")
                c2.metric("发现结论", result.get("n_results", 0))
                if result.get("output_path"):
                    st.session_state.last_report_path = result["output_path"]
                    if st.button("📋 查看报告", type="primary"):
                        st.session_state.nav_page = "report"
                        st.rerun()
            else:
                st.error(f"分析未完成: {result.get('message', '未知错误')}")

        # 清理 session 状态
        for key in ("_analysis_thread_started", "_analysis_thread",
                    "_analysis_result_h", "_analysis_error_h",
                    "_analysis_events_h", "analysis_data",
                    "analysis_start"):
            st.session_state.pop(key, None)
        cleanup_session_temp()  # 清理临时上传文件

    # ── 实时事件流展示 ──────────────────────────────────────
    events = st.session_state.get("analysis_events", [])[-100:]  # 最多保留 100 条

    if events:
        st.divider()
        st.markdown("### 📋 分析日志")
        with st.expander("查看完整事件流", expanded=True):
            render_event_log(events)
    elif not st.session_state.get("analysis_running"):
        # 空状态：显示引导
        st.info("""
        **分析尚未开始。**

        步骤：
        1. 选择或上传数据
        2. 输入分析问题
        3. 点击「🚀 开始分析」

        HaGoKu 会自动完成：数据侦察 → 清洗 → 统计检验 → 商业指标 → 生成报告。
        每一步都有统计护栏把关。
        """)
