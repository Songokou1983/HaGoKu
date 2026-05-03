"""HaGoKu Streamlit UI — 项目侧边栏组件"""

from __future__ import annotations

import streamlit as st
from datetime import datetime
from pathlib import Path

from hagokyu.config import HaGoKuConfig
from hagokyu.storage.project_manager import ProjectManager, ProjectInfo


def init_session_state():
    """初始化 session state 中的项目管理器"""
    if "project_manager" not in st.session_state:
        config = HaGoKuConfig.load()
        st.session_state.project_manager = ProjectManager(config.output.base_dir)
    if "current_project" not in st.session_state:
        st.session_state.current_project = None


def render_project_sidebar() -> str | None:
    """
    渲染项目侧边栏

    Returns:
        当前选中的项目名，如果没有选中返回 None
    """
    init_session_state()
    pm: ProjectManager = st.session_state.project_manager

    st.sidebar.markdown("## 📁 项目管理")

    # 新建项目按钮
    with st.sidebar.expander("➕ 新建项目", expanded=False):
        new_name = st.text_input("项目名称", placeholder="例如: Q1销售分析")
        new_desc = st.text_area("描述（可选）", placeholder="简要描述这个项目...")
        if st.button("创建", use_container_width=True) and new_name:
            try:
                pm.create(new_name, description=new_desc or "")
                st.success(f"✅ 项目 '{new_name}' 创建成功")
                st.rerun()
            except FileExistsError:
                st.error(f"❌ 项目 '{new_name}' 已存在")
            except Exception as e:
                st.error(f"❌ 创建失败: {e}")

    st.sidebar.divider()

    # 项目列表
    projects = pm.list()

    if not projects:
        st.sidebar.info("暂无项目。\n点击上方「新建项目」开始。")
        return None

    # 当前项目
    current = st.session_state.get("current_project")

    # 项目选择
    project_names = [p.name for p in projects]
    if current and current not in project_names:
        current = None

    selected = st.sidebar.selectbox(
        "选择项目",
        options=project_names,
        index=project_names.index(current) if current else 0,
        label_visibility="collapsed",
    )

    st.session_state.current_project = selected

    # 显示当前项目详情
    info = pm.info(selected)
    if info:
        render_project_info(info)

    return selected


def render_project_info(info: ProjectInfo) -> None:
    """渲染单个项目的详细信息"""
    st.sidebar.markdown(f"**📊 {info.name}**")

    if info.description:
        st.sidebar.caption(info.description)

    # 统计数据
    col1, col2 = st.sidebar.columns(2)
    col1.metric("运行", info.run_count)
    col2.metric("数据", len(info.data_files))

    if info.last_run:
        st.sidebar.caption(f"最近: {info.last_run.strftime('%m-%d %H:%M')}")

    # 数据文件列表
    if info.data_files:
        with st.sidebar.expander(f"📄 数据文件 ({len(info.data_files)})"):
            for f in info.data_files[-5:]:  # 最多显示5个
                ts = f.added_at.strftime("%m-%d")
                size = f"{f.size_kb:.0f}KB" if f.size_kb > 1 else f"{f.size_kb:.1f}KB"
                st.caption(f"• {f.name} ({size}, {ts})")

    st.sidebar.divider()

    # 快捷操作
    col1, col2 = st.sidebar.columns(2)
    if col1.button("🚀 分析", use_container_width=True, type="primary"):
        st.session_state.nav_page = "analyze"
        st.rerun()
    if col2.button("📋 报告", use_container_width=True):
        st.session_state.nav_page = "report"
        st.rerun()


def render_quick_upload() -> Path | None:
    """
    渲染快速上传组件

    Returns:
        上传文件的临时路径，None 表示无上传
    """
    init_session_state()
    pm: ProjectManager = st.session_state.project_manager

    uploaded = st.sidebar.file_uploader(
        "📤 上传数据",
        type=["csv", "xlsx", "xls", "json", "parquet"],
        help="上传 CSV、Excel、JSON 或 Parquet 文件",
    )

    if uploaded:
        # 保存到临时文件
        import tempfile
        suffix = Path(uploaded.name).suffix
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False, mode="wb") as f:
            f.write(uploaded.getvalue())
            tmp_path = Path(f.name)

        st.sidebar.success(f"✅ 已加载: {uploaded.name}")

        # 可选：添加到当前项目
        current = st.session_state.get("current_project")
        if current and st.sidebar.button("📁 保存到项目"):
            try:
                pm.add_data(current, tmp_path)
                st.sidebar.success(f"✅ 已保存到项目 '{current}'")
                st.rerun()
            except Exception as e:
                st.sidebar.error(f"保存失败: {e}")

        return tmp_path

    return None
