"""HaGoKu Streamlit UI — 主应用入口

运行方式：
    streamlit run hagokyu/ui/app.py
    或
    hagokyu-ui

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
LOGO_PNG = str(_UI_DIR / "static" / "logo.png")


def run() -> None:
    """应用主体（仅在 streamlit subprocess 中调用）"""
    import sys as _sys

    # streamlit exec() 不会设置 __package__，导致相对导入失败
    _main = _sys.modules.get("__main__")
    if _main is not None and not getattr(_main, "__package__", None):
        _main.__package__ = "hagokyu.ui"

    # 确保父包在 sys.modules 中（相对导入需要）
    if "hagokyu.ui" not in _sys.modules:
        import hagokyu.ui as _ui_pkg
        _sys.modules["hagokyu.ui"] = _ui_pkg
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

    # ── 全局样式：终端科技感 ──────────────────────────────────
    st.html("""
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
    :root {
        --hagokyu-bg: #0a0e17;
        --hagokyu-surface: #161b22;
        --hagokyu-border: #30363d;
        --hagokyu-accent: #22d3ee;
        --hagokyu-accent2: #a78bfa;
        --hagokyu-text: #e2e8f0;
        --hagokyu-text-dim: #8b949e;
        --hagokyu-green: #4ade80;
        --hagokyu-red: #f87171;
        --hagokyu-yellow: #fbbf24;
        --hagokyu-font: 'Inter', system-ui, sans-serif;
        --hagokyu-mono: 'JetBrains Mono', 'Fira Code', monospace;
    }

    /* 整体字体 & 背景 */
    html, body, .stApp {
        background-color: var(--hagokyu-bg) !important;
        color: var(--hagokyu-text) !important;
        font-family: var(--hagokyu-font) !important;
        font-size: 16px !important;
    }

    /* 基础文字 */
    p, span, label, .stText, .stCaption, .stMarkdown, li {
        font-size: 15px !important;
        color: var(--hagokyu-text) !important;
    }

    /* 标题层级 */
    h1 { font-size: 2rem !important; font-weight: 700 !important; color: #f8fafc !important; }
    h2 { font-size: 1.5rem !important; font-weight: 600 !important; color: #f1f5f9 !important; }
    h3 { font-size: 1.2rem !important; font-weight: 600 !important; color: #e2e8f0 !important; }
    h4 { font-size: 1rem !important; font-weight: 600 !important; }

    /* 侧边栏 */
    [data-testid="stSidebar"] {
        background-color: #0d1117 !important;
        border-right: 1px solid var(--hagokyu-border) !important;
    }
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {
        color: var(--hagokyu-text) !important;
    }

    /* 侧边栏 radio / selectbox */
    [data-testid="stSidebar"] .stSelectbox > div > div,
    [data-testid="stSidebar"] .stRadio > div {
        background: var(--hagokyu-surface) !important;
        border: 1px solid var(--hagokyu-border) !important;
        border-radius: 8px !important;
        color: var(--hagokyu-text) !important;
    }
    [data-testid="stSidebar"] .stRadio label {
        color: var(--hagokyu-text) !important;
    }
    [data-testid="stSidebar"] .stRadio [data-testid="stRadio"] > label {
        color: var(--hagokyu-text) !important;
    }

    /* 侧边栏导航：放大间距，更易读 */
    [data-testid="stSidebar"] .stRadio > div {
        padding: 0.5rem 0.75rem !important;
        display: flex !important;
        flex-direction: column !important;
        gap: 0.25rem !important;
    }
    [data-testid="stSidebar"] .stRadio label {
        font-size: 1rem !important;
        font-weight: 500 !important;
        padding: 0.35rem 0.5rem !important;
        border-radius: 6px !important;
        min-height: unset !important;
        color: var(--hagokyu-text) !important;
    }
    [data-testid="stSidebar"] .stRadio label:hover {
        background: rgba(34, 211, 238, 0.08) !important;
        color: var(--hagokyu-accent) !important;
    }
    [data-testid="stSidebar"] .stRadio [data-testid="stRadio"] {
        margin-top: 0.15rem !important;
    }
    /* 去掉导航边框/圆角容器，改成分离式按钮风格 */
    [data-testid="stSidebar"] .stRadio > div {
        background: transparent !important;
        border: none !important;
        border-radius: 0 !important;
        padding: 0 !important;
        gap: 0.15rem !important;
    }
    [data-testid="stSidebar"] .stRadio label {
        border: 1px solid transparent !important;
        border-radius: 8px !important;
    }

    /* 主内容区卡片 */
    [data-testid="stVerticalBlock"], [data-testid="stHorizontalBlock"] {
        gap: 0.5rem !important;
    }

    /* 按钮 */
    .stButton > button {
        background: linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%) !important;
        border: 1px solid var(--hagokyu-accent) !important;
        color: var(--hagokyu-accent) !important;
        border-radius: 8px !important;
        font-family: var(--hagokyu-mono) !important;
        font-size: 14px !important;
        font-weight: 600 !important;
        transition: all 0.2s !important;
        letter-spacing: 0.02em !important;
    }
    .stButton > button:hover {
        background: linear-gradient(135deg, #1e4a7a 0%, #1a2e4a 100%) !important;
        border-color: #67e8f9 !important;
        color: #67e8f9 !important;
        box-shadow: 0 0 12px rgba(34, 211, 238, 0.25) !important;
    }
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #0e7490 0%, #155e75 100%) !important;
        border-color: var(--hagokyu-accent) !important;
        color: #f0fdfa !important;
    }
    .stButton > button[kind="primary"]:hover {
        background: linear-gradient(135deg, #0891b2 0%, #0e7490 100%) !important;
        box-shadow: 0 0 20px rgba(34, 211, 238, 0.4) !important;
    }

    /* 输入框 */
    .stTextInput > div > div > input,
    .stTextArea > div > div > textarea,
    .stNumberInput > div > div > input {
        background-color: var(--hagokyu-surface) !important;
        border: 1px solid var(--hagokyu-border) !important;
        color: var(--hagokyu-text) !important;
        border-radius: 8px !important;
        font-family: var(--hagokyu-mono) !important;
        font-size: 14px !important;
        transition: border-color 0.2s !important;
    }
    .stTextInput > div > div > input:focus,
    .stTextArea > div > div > textarea:focus,
    .stNumberInput > div > div > input:focus {
        border-color: var(--hagokyu-accent) !important;
        box-shadow: 0 0 0 2px rgba(34, 211, 238, 0.15) !important;
    }

    /* tabs */
    .stTabs [data-baseweb="tab-list"] {
        background: var(--hagokyu-surface) !important;
        border-radius: 8px 8px 0 0 !important;
        border: 1px solid var(--hagokyu-border) !important;
        border-bottom: none !important;
        gap: 0 !important;
    }
    .stTabs [data-baseweb="tab"] {
        background: transparent !important;
        color: var(--hagokyu-text-dim) !important;
        border-right: 1px solid var(--hagokyu-border) !important;
        border-radius: 0 !important;
        font-family: var(--hagokyu-mono) !important;
        font-size: 14px !important;
        font-weight: 500 !important;
        padding: 0.5rem 1rem !important;
    }
    .stTabs [data-baseweb="tab"]:hover {
        color: var(--hagokyu-accent) !important;
        background: rgba(34, 211, 238, 0.05) !important;
    }
    .stTabs [aria-selected="true"] {
        background: var(--hagokyu-bg) !important;
        color: var(--hagokyu-accent) !important;
        border-bottom: 2px solid var(--hagokyu-accent) !important;
    }

    /* Metric */
    [data-testid="stMetricValue"] {
        font-family: var(--hagokyu-mono) !important;
        font-size: 1.8rem !important;
        font-weight: 600 !important;
        color: var(--hagokyu-accent) !important;
    }
    [data-testid="stMetricLabel"] {
        font-family: var(--hagokyu-mono) !important;
        font-size: 12px !important;
        color: var(--hagokyu-text-dim) !important;
        text-transform: uppercase !important;
        letter-spacing: 0.05em !important;
    }

    /* Divider */
    hr {
        border-color: var(--hagokyu-border) !important;
    }

    /* Expander */
    .streamlit-expander {
        background: var(--hagokyu-surface) !important;
        border: 1px solid var(--hagokyu-border) !important;
        border-radius: 8px !important;
    }
    .streamlit-expander > summary {
        color: var(--hagokyu-text) !important;
        font-size: 14px !important;
    }

    /* Success / Warning / Error boxes */
    .stSuccess { background-color: rgba(74, 222, 128, 0.1) !important; border-left: 3px solid var(--hagokyu-green) !important; }
    .stWarning { background-color: rgba(251, 191, 36, 0.1) !important; border-left: 3px solid var(--hagokyu-yellow) !important; }
    .stError   { background-color: rgba(248, 113, 113, 0.1) !important; border-left: 3px solid var(--hagokyu-red) !important; }
    .stInfo    { background-color: rgba(34, 211, 238, 0.08) !important; border-left: 3px solid var(--hagokyu-accent) !important; }

    /* File uploader */
    [data-testid="stFileUploadDropzone"] {
        background: var(--hagokyu-surface) !important;
        border: 2px dashed var(--hagokyu-border) !important;
        border-radius: 12px !important;
    }
    [data-testid="stFileUploadDropzone"]:hover {
        border-color: var(--hagokyu-accent) !important;
    }

    /* Dataframe */
    [data-testid="stDataFrame"] {
        border: 1px solid var(--hagokyu-border) !important;
        border-radius: 8px !important;
    }

    /* Progress bar */
    .stProgress > div > div > div {
        background: linear-gradient(90deg, #0e7490, #22d3ee) !important;
    }

    /* Code / pre */
    code, pre, .stCodeBlock {
        font-family: var(--hagokyu-mono) !important;
        background: var(--hagokyu-surface) !important;
        border: 1px solid var(--hagokyu-border) !important;
        border-radius: 6px !important;
        font-size: 13px !important;
    }

    /* Scrollbar */
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: var(--hagokyu-bg) !important; }
    ::-webkit-scrollbar-thumb { background: var(--hagokyu-border) !important; border-radius: 3px !important; }
    ::-webkit-scrollbar-thumb:hover { background: var(--hagokyu-text-dim) !important; }
    </style>
    """)

    # ── Session State 初始化 ────────────────────────────────────
    if "initialized" not in st.session_state:
        st.session_state.initialized = True
        st.session_state.current_project = None
        st.session_state.analysis_result = None
        st.session_state.analysis_events = []
        st.session_state.analysis_running = False
        st.session_state.nav_page = "projects"

    # ── 页面路由 ────────────────────────────────────────────────
    PAGES = {
        "📁 项目管理": "_pages.app_projects",
        "📊 互动分析": "_pages.app_analyze",
        "📋 报告输出": "_pages.app_report",
        "⚙️ 系统设置": "_pages.app_settings",
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

        # 渲染项目侧边栏（仅非设置页面）
        if "settings" not in selected_page:
            from hagokyu.ui.components.project_sidebar import render_project_sidebar
            render_project_sidebar()

    page_module = PAGES.get(selected_page, PAGES["🏠 项目"])
    module_name = page_module.split(".")[-1]

    if module_name == "app_projects":
        from hagokyu.ui._pages import app_projects
        app_projects.render()
    elif module_name == "app_analyze":
        from hagokyu.ui._pages import app_analyze
        app_analyze.render()
    elif module_name == "app_report":
        from hagokyu.ui._pages import app_report
        app_report.render()
    elif module_name == "app_settings":
        from hagokyu.ui._pages import app_settings
        app_settings.render()
    else:
        from hagokyu.ui._pages import app_projects
        app_projects.render()


def main() -> None:
    """Streamlit app 入口（供 hagokyu-ui 命令调用）"""
    import os
    import subprocess
    import sys
    from pathlib import Path

    app_py = Path(__file__).resolve()

    # 已在 hagokyu subprocess 内 → 直接调用 run()，不再启动新 subprocess
    if os.environ.get("HAGOKYU_SUBPROCESS"):
        run()
        return

    os.environ["HAGOKYU_SUBPROCESS"] = "1"
    result = subprocess.run([
        sys.executable, "-m", "streamlit", "run",
        "--server.headless=true",
        "--server.port=8501",
        "hagokyu/ui/__main__.py",
    ], cwd=app_py.parent.parent.parent)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
