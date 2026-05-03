"""HaGoKu Streamlit UI — 项目侧边栏组件"""

from __future__ import annotations

import streamlit as st

from hagokyu.config import HaGoKuConfig
from hagokyu.storage.project_manager import ProjectManager


def init_session_state():
    """初始化 session state 中的项目管理器"""
    if "project_manager" not in st.session_state:
        config = HaGoKuConfig.load()
        st.session_state.project_manager = ProjectManager(config.output.base_dir)
    if "current_project" not in st.session_state:
        st.session_state.current_project = None


def render_project_sidebar() -> str | None:
    """
    侧边栏：轻量级项目切换器

    Returns:
        当前选中的项目名，没有项目则返回 None
    """
    init_session_state()
    pm: ProjectManager = st.session_state.project_manager
    projects = pm.list()

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
