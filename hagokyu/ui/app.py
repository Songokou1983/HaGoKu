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
    import os as _os
    import sys as _sys
    from pathlib import Path as _Path

    # 清除字节码缓存，确保每次启动都加载最新代码
    import shutil as _shutil
    _root = _Path(__file__).resolve().parent.parent  # 整个 hagokyu 包
    for _dir, _dirs, _files in _os.walk(_root):
        # 删除当前目录的 .pyc 文件
        for _f in _files:
            if _f.endswith(".pyc"):
                try:
                    _os.unlink(_os.path.join(_dir, _f))
                except OSError:
                    pass
        # 跳过 __pycache__ 子目录（用 rmtree 整体删除）
        _pq_dirs = [_d for _d in _dirs if _d == "__pycache__"]
        for _d in _pq_dirs:
            _dirs.remove(_d)
            try:
                _shutil.rmtree(_os.path.join(_dir, _d), ignore_errors=True)
            except OSError:
                pass

    # 确保 .streamlit/config.toml 存在（pip install 后可能不在用户工作目录）
    _ui_mod = _sys.modules.get("hagokyu.ui")
    _pkg_root = Path(_ui_mod.__file__).parent.parent if _ui_mod and hasattr(_ui_mod, "__file__") and _ui_mod.__file__ else _Path(__file__).parent.parent
    _config_src = _pkg_root / ".streamlit" / "config.toml"
    _config_dest = Path.home() / ".streamlit" / "config.toml"
    if not _config_dest.exists():
        _config_dest.parent.mkdir(parents=True, exist_ok=True)
        _default_config = """[theme]
primaryColor = "#38bdf8"
backgroundColor = "#0a0e17"
secondaryBackgroundColor = "#161b22"
textColor = "#e2e8f0"
font = "sans serif"

[server]
headless = true

[browser]
gatherUsageStats = false
"""
        _config_dest.write_text(_default_config)

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

    # ── 全局样式：Retro-Futuristic 终端 ────────────────────────
    st.html("""
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=VT323&display=swap" rel="stylesheet">
    <style>
    :root {
        --hagokyu-bg: #0a0e17;
        --hagokyu-surface: #0d1117;
        --hagokyu-border: #38bdf8;
        --hagokyu-accent: #00ffff;
        --hagokyu-magenta: #ff006e;
        --hagokyu-text: #c9d1d9;
        --hagokyu-text-dim: #6e7681;
        --hagokyu-green: #00ff41;
        --hagokyu-red: #ff453a;
        --hagokyu-yellow: #ffd60a;
        --hagokyu-orange: #ffb347;
        --hagokyu-mono: 'Space Mono', monospace;
        --hagokyu-display: 'VT323', monospace;
    }

    /* 整体字体 & 背景 */
    html, body, .stApp {
        background-color: var(--hagokyu-bg) !important;
        color: var(--hagokyu-text) !important;
        font-family: var(--hagokyu-mono) !important;
        font-size: 18px !important;
    }

    /* 基础文字 */
    p, span, label, .stText, .stCaption, .stMarkdown, li {
        font-size: 17px !important;
        color: var(--hagokyu-text) !important;
    }

    /* 标题层级 — VT323 标题感 */
    h1 { font-family: var(--hagokyu-display) !important; font-size: 3.2rem !important; font-weight: 400 !important; color: var(--hagokyu-accent) !important; letter-spacing: 0.05em !important; }
    h2 { font-family: var(--hagokyu-display) !important; font-size: 2.4rem !important; font-weight: 400 !important; color: #f0fdfa !important; letter-spacing: 0.04em !important; }
    h3 { font-family: var(--hagokyu-mono) !important; font-size: 1.3rem !important; font-weight: 700 !important; color: var(--hagokyu-accent) !important; text-transform: uppercase !important; letter-spacing: 0.08em !important; }
    h4 { font-size: 1.1rem !important; font-weight: 700 !important; color: var(--hagokyu-text) !important; }

    /* CRT 扫描线 — 全局 overlay */
    [data-testid="stMainBlockContainer"]::before {
        content: '';
        position: fixed;
        top: 0; left: 0; right: 0; bottom: 0;
        background: repeating-linear-gradient(
            0deg,
            transparent,
            transparent 2px,
            rgba(0, 0, 0, 0.07) 2px,
            rgba(0, 0, 0, 0.07) 4px
        );
        pointer-events: none;
        z-index: 9999;
    }

    /* 侧边栏 */
    [data-testid="stSidebar"] {
        background-color: #070b11 !important;
        border-right: 1px solid var(--hagokyu-border) !important;
    }
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {
        color: var(--hagokyu-text) !important;
    }
    [data-testid="stSidebar"] h2 {
        font-family: var(--hagokyu-display) !important;
        font-size: 2.4rem !important;
        color: var(--hagokyu-magenta) !important;
        text-shadow: 0 0 8px var(--hagokyu-magenta) !important;
    }

    /* 侧边栏导航：flat terminal 风格 */
    [data-testid="stSidebar"] .stRadio > div {
        background: transparent !important;
        border: none !important;
        border-radius: 0 !important;
        padding: 0 !important;
        gap: 0.1rem !important;
    }
    [data-testid="stSidebar"] .stRadio label {
        font-family: var(--hagokyu-mono) !important;
        font-size: 1.1rem !important;
        font-weight: 700 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.12em !important;
        padding: 0.8rem 1rem !important;
        border: 1px solid transparent !important;
        border-radius: 0 !important;
        min-height: unset !important;
        color: var(--hagokyu-text-dim) !important;
        line-height: 1 !important;
    }
    [data-testid="stSidebar"] .stRadio label:hover {
        background: transparent !important;
        color: var(--hagokyu-accent) !important;
        text-shadow: 0 0 6px var(--hagokyu-accent) !important;
    }
    [data-testid="stSidebar"] .stRadio [data-testid="stRadio"] > label:has(input:checked) {
        background: transparent !important;
        border-color: var(--hagokyu-accent) !important;
        color: var(--hagokyu-accent) !important;
        text-shadow: 0 0 8px var(--hagokyu-accent) !important;
        font-weight: 700 !important;
    }
    [data-testid="stSidebar"] .stRadio [data-testid="stRadio"] {
        margin-top: 0 !important;
    }

    /* 主内容区 */
    [data-testid="stVerticalBlock"], [data-testid="stHorizontalBlock"] {
        gap: 0.5rem !important;
    }

    /* 按钮 — flat + neon glow */
    .stButton > button {
        background: #0d1117 !important;
        border: 1px solid var(--hagokyu-accent) !important;
        color: var(--hagokyu-accent) !important;
        border-radius: 0 !important;
        font-family: var(--hagokyu-mono) !important;
        font-size: 15px !important;
        font-weight: 700 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.1em !important;
        transition: box-shadow 0.15s, color 0.15s !important;
    }
    .stButton > button:hover {
        background: #0d1117 !important;
        color: var(--hagokyu-accent) !important;
        border-color: var(--hagokyu-accent) !important;
        box-shadow: 0 0 16px rgba(0, 255, 255, 0.35), inset 0 0 8px rgba(0, 255, 255, 0.08) !important;
    }
    .stButton > button[kind="primary"] {
        background: var(--hagokyu-accent) !important;
        color: #0a0e17 !important;
        border-color: var(--hagokyu-accent) !important;
        box-shadow: 0 0 10px rgba(0, 255, 255, 0.3) !important;
    }
    .stButton > button[kind="primary"]:hover {
        background: #00ffff !important;
        box-shadow: 0 0 28px rgba(0, 255, 255, 0.6), 0 0 8px rgba(0, 255, 255, 0.4) !important;
        color: #0a0e17 !important;
    }

    /* 输入框 */
    .stTextInput > div > div > input,
    .stTextArea > div > div > textarea,
    .stNumberInput > div > div > input {
        background-color: #070b11 !important;
        border: 1px solid var(--hagokyu-border) !important;
        color: var(--hagokyu-text) !important;
        border-radius: 0 !important;
        font-family: var(--hagokyu-mono) !important;
        font-size: 16px !important;
        transition: border-color 0.15s, box-shadow 0.15s !important;
    }
    .stTextInput > div > div > input:focus,
    .stTextArea > div > div > textarea:focus,
    .stNumberInput > div > div > input:focus {
        border-color: var(--hagokyu-accent) !important;
        box-shadow: 0 0 0 1px var(--hagokyu-accent), 0 0 12px rgba(0, 255, 255, 0.15) !important;
        outline: none !important;
    }

    /* selectbox */
    .stSelectbox > div > div {
        background-color: #070b11 !important;
        border: 1px solid var(--hagokyu-border) !important;
        border-radius: 0 !important;
        color: var(--hagokyu-text) !important;
        font-family: var(--hagokyu-mono) !important;
        font-size: 16px !important;
    }
    .stSelectbox > div > div:hover {
        border-color: var(--hagokyu-accent) !important;
    }

    /* tabs */
    .stTabs [data-baseweb="tab-list"] {
        background: #070b11 !important;
        border-radius: 0 !important;
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
        font-size: 15px !important;
        font-weight: 700 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.08em !important;
        padding: 0.7rem 1.2rem !important;
    }
    .stTabs [data-baseweb="tab"]:hover {
        color: var(--hagokyu-accent) !important;
        background: transparent !important;
    }
    .stTabs [aria-selected="true"] {
        background: var(--hagokyu-bg) !important;
        color: var(--hagokyu-accent) !important;
        border-bottom: 2px solid var(--hagokyu-accent) !important;
        text-shadow: 0 0 6px var(--hagokyu-accent) !important;
    }

    /* Metric */
    [data-testid="stMetricValue"] {
        font-family: var(--hagokyu-mono) !important;
        font-size: 2rem !important;
        font-weight: 700 !important;
        color: var(--hagokyu-green) !important;
        text-shadow: 0 0 8px rgba(0, 255, 65, 0.5) !important;
    }
    [data-testid="stMetricLabel"] {
        font-family: var(--hagokyu-mono) !important;
        font-size: 13px !important;
        color: var(--hagokyu-text-dim) !important;
        text-transform: uppercase !important;
        letter-spacing: 0.1em !important;
    }

    /* Divider */
    hr {
        border-color: var(--hagokyu-border) !important;
    }

    /* Expander */
    .streamlit-expander {
        background: var(--hagokyu-surface) !important;
        border: 1px solid var(--hagokyu-border) !important;
        border-radius: 0 !important;
    }
    .streamlit-expander > summary {
        color: var(--hagokyu-text) !important;
        font-size: 16px !important;
        font-family: var(--hagokyu-mono) !important;
    }

    /* Success / Warning / Error boxes */
    .stSuccess { background-color: rgba(0, 255, 65, 0.06) !important; border-left: 2px solid var(--hagokyu-green) !important; }
    .stWarning { background-color: rgba(255, 214, 10, 0.06) !important; border-left: 2px solid var(--hagokyu-yellow) !important; }
    .stError   { background-color: rgba(255, 69, 58, 0.06) !important; border-left: 2px solid var(--hagokyu-red) !important; }
    .stInfo    { background-color: rgba(0, 255, 255, 0.04) !important; border-left: 2px solid var(--hagokyu-accent) !important; }

    /* File uploader */
    [data-testid="stFileUploadDropzone"] {
        background: #070b11 !important;
        border: 1px dashed var(--hagokyu-border) !important;
        border-radius: 0 !important;
    }
    [data-testid="stFileUploadDropzone"]:hover {
        border-color: var(--hagokyu-accent) !important;
        box-shadow: inset 0 0 12px rgba(0, 255, 255, 0.05) !important;
    }

    /* Dataframe */
    [data-testid="stDataFrame"] {
        border: 1px solid var(--hagokyu-border) !important;
        border-radius: 0 !important;
    }

    /* Progress bar — neon glow */
    .stProgress > div > div > div {
        background: var(--hagokyu-accent) !important;
        box-shadow: 0 0 8px var(--hagokyu-accent), 0 0 16px rgba(0, 255, 255, 0.3) !important;
    }

    /* Code / pre */
    code, pre, .stCodeBlock {
        font-family: var(--hagokyu-mono) !important;
        background: #070b11 !important;
        border: 1px solid var(--hagokyu-border) !important;
        border-radius: 0 !important;
        font-size: 15px !important;
    }

    /* Scrollbar */
    ::-webkit-scrollbar { width: 4px; height: 4px; }
    ::-webkit-scrollbar-track { background: var(--hagokyu-bg) !important; }
    ::-webkit-scrollbar-thumb { background: var(--hagokyu-border) !important; }
    ::-webkit-scrollbar-thumb:hover { background: var(--hagokyu-accent) !important; }

    /* Chat 消息框 — 橙色边框 */
    [data-testid="stChatMessageContent"] {
        border: 1px solid var(--hagokyu-orange) !important;
        border-radius: 0 !important;
        box-shadow: 0 0 8px rgba(255, 179, 71, 0.15) !important;
    }
    /* Chat 消息avatar */
    [data-testid="stChatMessage"] {
        border-left: 2px solid var(--hagokyu-orange) !important;
    }
    </style>
    """)

    # ── Session State 初始化 ────────────────────────────────────
    if "initialized" not in st.session_state:
        from hagokyu.config import HaGoKuConfig
        from hagokyu.storage.project_manager import ProjectManager

        config = HaGoKuConfig.load()
        st.session_state.project_manager = ProjectManager(config.output.project_dir)
        st.session_state.initialized = True
        st.session_state.current_project = None
        st.session_state.analysis_result = None
        st.session_state.analysis_events = []
        st.session_state.analysis_running = False
        st.session_state.nav_page = "projects"

    # ── 页面路由 ────────────────────────────────────────────────
    PAGES = {
        "📁 项目管理": "_pages.app_projects",
        "💬 互动分析": "_pages.app_analyze",
        "📋 报告输出": "_pages.app_report",
        "⚙️ 系统设置": "_pages.app_settings",
        "📚 知识库（RAG）": "_pages.app_knowledge",
    }

    # 侧边栏导航
    with st.sidebar:
        col_logo, col_title = st.columns([1, 4])
        with col_logo:
            st.image(LOGO_PNG, width=52)
        with col_title:
            st.markdown("""
            <div style="padding: 0.3rem 0;">
                <div style="font-family:'VT323',monospace;font-size:2.5rem;font-weight:bold;color:#ffb347;letter-spacing:0.06em;text-shadow:0 1px 0 #cc8c2c,0 2px 0 #b3772a,0 3px 0 #996624,0 4px 8px rgba(0,0,0,0.5);line-height:1;">HaGoKu</div>
                <div style="font-family:'Space Mono',monospace;font-size:1rem;color:#ffffff;letter-spacing:0.08em;margin-top:0.35rem;">让每个小模型，都能做专业级商业分析</div>
            </div>
            """, unsafe_allow_html=True)
        st.divider()

        selected_page = st.radio(
            "导航",
            options=list(PAGES.keys()),
            index=list(PAGES.keys()).index(
                next((k for k, v in PAGES.items() if "app_" + st.session_state.get("nav_page", "projects") in v),
                     "📁 项目管理")
            ),
            label_visibility="collapsed",
        )

        # 渲染项目侧边栏（仅项目管理/互动分析/报告输出页面）
        if selected_page in ("📁 项目管理", "💬 互动分析", "📋 报告输出"):
            from hagokyu.ui.components.project_sidebar import render_project_sidebar
            render_project_sidebar()

    page_module = PAGES.get(selected_page, PAGES["📁 项目管理"])
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
    elif module_name == "app_knowledge":
        from hagokyu.ui._pages import app_knowledge
        app_knowledge.render()
    else:
        from hagokyu.ui._pages import app_projects
        app_projects.render()


def main() -> None:
    """Streamlit app 入口（供 hagokyu-ui 命令调用）"""
    import os
    import subprocess
    import sys
    from pathlib import Path

    # 启动时清除 Python 字节码缓存，确保加载最新代码
    _hagokyu_root = Path(__file__).resolve().parent.parent
    for _root, _dirs, _files in os.walk(_hagokyu_root):
        for _f in _files:
            if _f.endswith(".pyc") or _f.endswith("__pycache__"):
                try:
                    os.unlink(os.path.join(_root, _f))
                except OSError:
                    pass
        for _d in _dirs:
            if _d == "__pycache__":
                try:
                    os.rmdir(os.path.join(_root, _d))
                except OSError:
                    pass

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
