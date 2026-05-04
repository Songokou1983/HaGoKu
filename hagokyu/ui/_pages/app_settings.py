"""HaGoKu Streamlit UI — 设置页面"""

from __future__ import annotations

import streamlit as st

from hagokyu.config import HaGoKuConfig
from hagokyu.tools import load_plugins


def render() -> None:
    st.title("⚙️ 设置")

    config = HaGoKuConfig.load()

    # ── LLM 配置 ───────────────────────────────────────────
    st.markdown("### 🤖 LLM 配置")

    with st.form("llm_config", clear_on_submit=False):
        col1, col2 = st.columns(2)
        with col1:
            model = st.text_input(
                "模型名称",
                value=config.llm.model,
                placeholder="例如：Qwen3.6-35B-A3B",
                help="模型名称，需与 base_url 服务兼容",
            )
        with col2:
            base_url = st.text_input(
                "API 地址",
                value=config.llm.base_url,
                placeholder="http://localhost:8000/v1",
                help="OpenAI-compatible API 端点",
            )

        api_key = st.text_input(
            "API Key",
            value=config.llm.api_key,
            type="password",
            placeholder="本地模型填 none",
            help="本地模型填 none，第三方 API 填对应 Key",
        )

        col3, col4 = st.columns(2)
        with col3:
            temperature = st.slider("Temperature", 0.0, 1.0, config.llm.temperature, 0.05)
        with col4:
            max_tokens = st.number_input("Max Tokens", 512, 32768, config.llm.max_tokens, 512)

        if st.form_submit_button("💾 保存 LLM 配置", type="primary", use_container_width=True):
            config.llm.model = model
            config.llm.base_url = base_url
            config.llm.api_key = api_key
            config.llm.temperature = temperature
            config.llm.max_tokens = max_tokens
            try:
                config.save()
                st.success("✅ LLM 配置已保存（重启 UI 或重新加载页面后生效）")
            except Exception as e:
                st.error(f"❌ 保存失败: {e}")

    st.divider()

    # ── 项目文件夹 ──────────────────────────────────────────
    st.markdown("### 📂 项目文件夹")

    with st.form("project_dir_config", clear_on_submit=False):
        project_dir = st.text_input(
            "📂 项目存放路径",
            value=str(config.output.project_dir),
            placeholder=str(config.output.project_dir),
            help="项目文件的存放位置，修改后新建项目会使用新路径",
        )
        if st.form_submit_button("💾 保存路径", type="primary", use_container_width=True):
            from pathlib import Path
            path = Path(project_dir)
            try:
                path.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                st.error(f"❌ 无权限创建目录：{path}")
            except Exception as e:
                st.error(f"❌ 路径无效: {e}")
            else:
                config.output.project_dir = path
                try:
                    config.save()
                    st.success("✅ 项目文件夹路径已保存，重新加载页面后生效")
                except Exception as e:
                    st.error(f"❌ 保存失败: {e}")

    st.divider()

    # ── 关于 ────────────────────────────────────────────────
    st.markdown("""
    ### ℹ️ 关于 HaGoKu

    **HaGoKu** — 用数学的力量，挖出数据背后真正的信息。

    **设计原则：**
    - 📊 每个结论都有统计检验（p值 + 效应量 + 置信区间）
    - 💰 商业指标和统计检验融为一体
    - ⚡ 功效分析：告诉你数据够不够
    - 🔌 插件架构：新增分析方法无需改核心代码
    """)
