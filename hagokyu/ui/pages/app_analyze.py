"""HaGoKu Streamlit UI — 分析页面（含实时事件流）"""

from __future__ import annotations

import tempfile
import threading
import time
from pathlib import Path

import streamlit as st

from hagokyu.ui.components.event_log import render_event_log
from hagokyu.config import HaGoKuConfig
from hagokyu.manager.orchestrator import Orchestrator
from hagokyu.observability.events import Event
from hagokyu.storage.project_manager import ProjectManager


def _cleanup_temp_file() -> None:
    """清理上次遗留的临时上传文件"""
    path = st.session_state.pop("_temp_uploaded_path", None)
    if path and Path(path).exists():
        try:
            Path(path).unlink()
        except OSError:
            pass


def _render_data_preview(data_path: str) -> None:
    """渲染数据预览：形状 + 前5行 + 类型信息（容错读取）"""
    try:
        import pandas as pd
        suffix = Path(data_path).suffix.lower()

        # 按扩展名读取，超时/失败时 fallback 到其他格式
        df = None
        errors: list[str] = []

        if suffix == ".parquet":
            try:
                df = pd.read_parquet(data_path)
            except Exception as e:
                errors.append(f"Parquet 解析失败: {e}")
        elif suffix in (".xlsx", ".xls"):
            try:
                df = pd.read_excel(data_path, nrows=2000)
            except Exception as e:
                errors.append(f"Excel 解析失败: {e}")
        elif suffix == ".json":
            try:
                df = pd.read_json(data_path, nrows=2000)
            except Exception:
                try:
                    df = pd.read_json(data_path, lines=True, nrows=2000)
                except Exception as e2:
                    errors.append(f"JSON 解析失败: {e2}")
        else:
            # CSV：尝试多种分隔符
            for sep in [",", ";", "\t"]:
                try:
                    df = pd.read_csv(data_path, sep=sep, nrows=2000, on_bad_lines="skip")
                    break
                except Exception:
                    continue

        if df is None or df.empty:
            st.warning("⚠️ 无法预览数据：格式无法识别，请确认文件是有效的 CSV/Excel/JSON/Parquet。")
            if errors:
                for err in errors:
                    st.caption(f"  - {err}")
            return

        rows, cols = df.shape
        c1, c2, c3 = st.columns(3)
        c1.metric("行数", f"{rows:,}")
        c2.metric("列数", cols)
        c3.metric("内存", f"{df.memory_usage(deep=True).sum() / 1024:.1f} KB")

        # 数据类型
        with st.expander("📋 字段类型预览"):
            type_summary = (
                df.dtypes.rename("类型")
                .to_frame()
                .reset_index()
                .rename(columns={"index": "字段名"})
            )
            st.dataframe(type_summary, use_container_width=True, hide_index=True)

        # 前5行
        with st.expander("👁 数据预览（前5行）"):
            st.dataframe(df.head(5), use_container_width=True, hide_index=True)

    except Exception as e:
        st.warning(f"无法预览数据: {e}")


def render() -> None:
    _cleanup_temp_file()
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
    col_data, col_query = st.columns([1, 2])

    with col_data:
        st.markdown("### 1️⃣ 选择数据")

        # Tab: 上传 | 项目已有
        tab_upload, tab_project = st.tabs(["📤 上传", "📁 项目已有"])

        with tab_upload:
            # 演示数据 banner
            if demo_path:
                st.success(f"🎯 正在使用演示数据: {demo_name or Path(demo_path).name}")
                _render_data_preview(demo_path)
                data_path = demo_path
            else:
                uploaded = st.file_uploader(
                    "上传数据文件",
                    type=["csv", "xlsx", "xls", "json", "parquet"],
                    label_visibility="collapsed",
                )
                if uploaded:
                    suffix = Path(uploaded.name).suffix
                    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False, mode="wb") as f:
                        f.write(uploaded.getvalue())
                        data_path = f.name
                    # 记录路径，分析结束时自动清理
                    st.session_state._temp_uploaded_path = data_path
                    st.session_state.uploaded_name = uploaded.name
                    st.success(f"✅ 已加载: {uploaded.name}")

                    # ── 数据预览 ─────────────────────────────────
                    _render_data_preview(data_path)
                else:
                    data_path = None

        with tab_project:
            # 使用侧边栏选中的当前项目（不再重复选择器）
            current = st.session_state.get("current_project")
            if not current:
                st.info("请先在侧边栏选择一个项目")
                data_path = None
            else:
                proj_info = pm.info(current)
                if proj_info and proj_info.data_files:
                    file_options = {f.name: proj_info.project_dir / f.path for f in proj_info.data_files}
                    selected_file = st.selectbox(
                        f"📄 {current} 的数据文件",
                        options=list(file_options.keys()),
                    )
                    data_path = str(file_options[selected_file])
                    _render_data_preview(data_path)
                else:
                    st.warning(f"「{current}」暂无数据文件，请先上传")
                    data_path = None

    with col_query:
        st.markdown("### 2️⃣ 分析问题")
        # 预填演示数据推荐问题
        prefilled = demo_query or st.session_state.get("_prefilled_query", "")
        if demo_query:
            st.session_state._prefilled_query = demo_query
        query = st.text_area(
            "你想分析什么？",
            value=prefilled,
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
                query = q
                st.rerun()

    st.divider()

    # ── 开始分析按钮 ─────────────────────────────────────────
    can_run = bool(data_path and query)
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
    if not query:
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
            "query": query,
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
        _cleanup_temp_file()  # 清理临时上传文件

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
