"""HaGoKu Streamlit UI — 主应用入口

运行方式：
    streamlit run hagokyu/ui/app.py
    或
    python -m hagokyu.ui.app

页面结构：
    🏠 首页（项目总览）
    📊 分析（实时分析 + 事件流）
    📋 报告（查看报告 + refinement 对话）
    ⚙️ 设置（LLM 配置等）
"""

from __future__ import annotations

import streamlit as st
from pathlib import Path

# ── Logo 路径 ────────────────────────────────────────────────
_UI_DIR = Path(__file__).parent
LOGO_SVG = str(_UI_DIR / "static" / "logo.svg")
LOGO_PNG = str(_UI_DIR / "static" / "logo.png")

# ── 页面配置 ────────────────────────────────────────────────

st.set_page_config(
    page_title="HaGoKu — 数据分析平台",
    page_icon=LOGO_PNG,
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get Help": None,
        "Report a Bug": None,
        "About": """
## HaGoKu 📊

用数学的力量，挖出数据背后真正的信息。

**核心能力：**
- 📈 统计检验：t检验、ANOVA、回归、相关
- 💰 商业分析：ROI、ROAS、LTV、CAC、归因
- ⚡ 功效分析：样本量评估、效应量解读
- 🛡️ 统计护栏：每个结论都有 p值 + 效应量 + 置信区间
        """,
    },
)

# ── Session State 初始化 ────────────────────────────────────

if "initialized" not in st.session_state:
    st.session_state.initialized = True
    st.session_state.current_project = None
    st.session_state.analysis_result = None
    st.session_state.analysis_events = []
    st.session_state.analysis_running = False
    st.session_state.nav_page = "projects"

# ── 页面路由 ────────────────────────────────────────────────

# 手动页面路由（Streamlit 的 st.navigation 在较老版本不可用）
PAGES = {
    "🏠 项目": "pages.app_projects",
    "📊 分析": "pages.app_analyze",
    "📋 报告": "pages.app_report",
    "⚙️ 设置": "pages.app_settings",
}

# 侧边栏导航
with st.sidebar:
    col_logo, col_title = st.columns([1, 4])
    with col_logo:
        st.image(LOGO_PNG, width=52)
    with col_title:
        st.markdown("""
        <div style="padding: 0.3rem 0;">
            <h2 style="margin:0; color:#a78bfa;">HaGoKu</h2>
            <p style="margin:0.1rem 0; color:#888; font-size:0.8rem;">用数学的力量</p>
        </div>
        """, unsafe_allow_html=True)
    st.divider()

    selected_page = st.radio(
        "导航",
        options=list(PAGES.keys()),
        index=list(PAGES.keys()).index(
            next((k for k, v in PAGES.items() if "app_" + st.session_state.get("nav_page", "projects") in v),
                 "🏠 项目")
        ),
        label_visibility="collapsed",
    )

    st.divider()

    # 渲染项目侧边栏（仅非设置页面）
    if "settings" not in selected_page:
        from .components.project_sidebar import (
            render_project_sidebar,
            render_quick_upload,
        )
        render_project_sidebar()
        render_quick_upload()

def main() -> None:
    """Streamlit app 入口"""
    import sys
    sys.argv = ["streamlit", "run", __file__]
    try:
        from streamlit.web import cli as stcli
        sys.exit(stcli.main())
    except SystemExit:
        raise


if __name__ == "__main__":
    main()

page_module = PAGES.get(selected_page, PAGES["🏠 项目"])
module_name = page_module.split(".")[-1]

if module_name == "app_projects":
    from .pages import app_projects
    app_projects.render()
elif module_name == "app_analyze":
    from .pages import app_analyze
    app_analyze.render()
elif module_name == "app_report":
    from .pages import app_report
    app_report.render()
elif module_name == "app_settings":
    from .pages import app_settings
    app_settings.render()
else:
    from .pages import app_projects
    app_projects.render()
