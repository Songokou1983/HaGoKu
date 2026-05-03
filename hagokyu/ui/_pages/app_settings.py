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

    # ── Manager 模式 ────────────────────────────────────────
    st.markdown("### 🎛️ Manager 模式")

    mode_labels = {
        "balanced": "🔄 平衡模式（规则+AI）",
        "rule": "📋 纯规则（快速，无需 LLM）",
        "ai": "🤖 AI 优先（最智能）",
    }

    mode_desc = {
        "balanced": "规则引擎处理常见意图，AI 处理复杂场景",
        "rule": "纯规则匹配，速度快但灵活性有限",
        "ai": "优先使用 LLM 生成分析计划，最智能但最慢",
    }

    selected_mode = st.radio(
        "选择模式",
        options=["balanced", "rule", "ai"],
        format_func=lambda x: mode_labels.get(x, x),
        index=["balanced", "rule", "ai"].index(config.manager.mode),
    )

    st.info(mode_desc.get(selected_mode, ""))

    if st.button("💾 应用模式", use_container_width=True):
        config.manager.mode = selected_mode
        try:
            config.save()
            st.success(f"✅ 已切换到 {mode_labels[selected_mode]}")
        except Exception as e:
            st.error(f"❌ 保存失败: {e}")

    st.divider()

    # ── 分析方法 ────────────────────────────────────────────
    st.markdown("### 📊 分析方法")

    reg = load_plugins()
    summary = reg.summary()

    col1, col2 = st.columns(2)
    col1.metric("内置方法", summary["total_methods"])
    col2.metric("可用标签", len(summary["by_tag"]))

    by_tag = summary["by_tag"]
    tag_labels = {
        "statistical": "📈 统计方法",
        "business": "💰 商业方法",
        "financial": "💵 财务分析",
        "comparison": "🔬 对比分析",
        "regression": "📉 回归分析",
        "correlation": "🔗 相关分析",
        "causal": "⚡ 因果推断",
        "user": "👤 用户分析",
        "growth": "📈 增长分析",
        "attribution": "🎯 归因分析",
        "funnel": "🔽 漏斗分析",
        "advertising": "📢 广告分析",
    }

    for tag, count in sorted(by_tag.items(), key=lambda x: x[1], reverse=True):
        label = tag_labels.get(tag, f"  [{tag}]")
        with st.expander(f"{label} ({count})"):
            methods = [m for m in reg.list_all() if tag in m.tags]
            for m in methods:
                st.markdown(f"• **{m.name}**")
                if m.description:
                    st.caption(m.description[:80])

    st.divider()

    # ── 统计护栏 ────────────────────────────────────────────
    st.markdown("### 🛡️ 统计护栏")

    from hagokyu.guardrails.statistical import StatisticalGuardrails
    g = StatisticalGuardrails()

    st.success(f"强制级规则: {len(g.mandatory_rules)} 条")
    st.warning(f"警告级规则: {len(g.warning_rules)} 条")
    st.info(f"提示级规则: {len(g.suggestion_rules)} 条")

    def _rule_desc(rule) -> str:
        """取 description 属性，无则回退到类 docstring"""
        desc = getattr(rule, "description", None)
        if desc:
            return desc[:100]
        # 回退到类 docstring 第一行
        doc = getattr(type(rule), "__doc__", None) or ""
        return doc.strip().split("\n")[0][:100]

    with st.expander("查看详细规则"):
        for rule in g.mandatory_rules:
            st.markdown(f"🚫 **{rule.rule_name}**")
            st.caption(_rule_desc(rule))
        for rule in g.warning_rules:
            st.markdown(f"⚠️ **{rule.rule_name}**")
            st.caption(_rule_desc(rule))
        for rule in g.suggestion_rules:
            st.markdown(f"💡 **{rule.rule_name}**")
            st.caption(_rule_desc(rule))

    st.divider()

    # ── 关于 ────────────────────────────────────────────────
    st.markdown("""
    ### ℹ️ 关于 HaGoKu

    **HaGoKu** — 用数学的力量，挖出数据背后真正的信息。

    **设计原则：**
    - 📊 每个结论都有统计检验（p值 + 效应量 + 置信区间）
    - 💰 商业指标和统计检验融为一体
    - ⚡ 功效分析：告诉你数据够不够
    - 🛡️ 统计护栏：自动拦截不严谨的结论
    - 🔌 插件架构：新增分析方法无需改核心代码
    """)
