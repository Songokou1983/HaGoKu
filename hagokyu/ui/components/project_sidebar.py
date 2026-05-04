"""HaGoKu Streamlit UI — 项目侧边栏组件"""

from __future__ import annotations

import streamlit as st

from hagokyu.config import HaGoKuConfig


def init_session_state():
    """初始化 session state 中的项目管理器"""
    if "project_manager" not in st.session_state:
        from hagokyu.storage.project_manager import ProjectManager
        config = HaGoKuConfig.load()
        st.session_state.project_manager = ProjectManager(config.output.project_dir)
    if "current_project" not in st.session_state:
        st.session_state.current_project = None


def render_project_sidebar() -> str | None:
    """侧边栏：仅初始化 session state，不显示任何内容"""
    init_session_state()
    return st.session_state.get("current_project")
