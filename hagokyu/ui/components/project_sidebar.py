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
    侧边栏：轻量级项目切换器（仅下拉选择器）

    详情（指标、文件列表、操作按钮）统一放在各页面主内容区，
    避免侧边栏和主内容重复。

    Returns:
        当前选中的项目名，没有项目则返回 None
    """
    init_session_state()
    pm: ProjectManager = st.session_state.project_manager
    projects = pm.list()

    # 项目下拉选择
    project_names = [p.name for p in projects]
    current = st.session_state.get("current_project")

    if current and current not in project_names:
        current = None
        st.session_state.current_project = None

    if not project_names:
        st.sidebar.info("暂无项目")
        return None

    selected = st.sidebar.selectbox(
        "📁 项目",
        options=project_names,
        index=project_names.index(current) if current else 0,
        label_visibility="collapsed",
    )
    st.session_state.current_project = selected
    return selected


def render_quick_upload() -> Path | None:
    """
    侧边栏底部：快速上传（始终可用，不依赖当前项目）

    Returns:
        上传文件的临时路径，None 表示无上传
    """
    st.sidebar.divider()

    init_session_state()
    pm: ProjectManager = st.session_state.project_manager

    uploaded = st.sidebar.file_uploader(
        "📤 上传数据",
        type=["csv", "xlsx", "xls", "json", "parquet"],
        help="CSV、Excel、JSON、Parquet",
        label_visibility="collapsed",
    )

    if not uploaded:
        return None

    import tempfile
    suffix = Path(uploaded.name).suffix
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False, mode="wb") as f:
        f.write(uploaded.getvalue())
        tmp_path = Path(f.name)

    st.sidebar.success(f"✅ {uploaded.name}")

    current = st.session_state.get("current_project")
    if current and st.sidebar.button("📁 保存到项目"):
        try:
            pm.add_data(current, tmp_path)
            st.sidebar.success(f"已保存到「{current}」")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"保存失败: {e}")

    return tmp_path
