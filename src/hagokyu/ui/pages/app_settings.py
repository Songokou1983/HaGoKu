"""HaGoKu Streamlit UI — 设置页面"""

from __future__ import annotations

import streamlit as st

from ...config import HaGoKuConfig
from ...tools import analysis_registry, load_plugins


def render() -> None:
    st.title("⚙️ 设置")

    # ── LLM 配置 ────────────────────────────────────────────
    st.markdown("### 🤖 LLM 配置")

    config = HaGoKuConfig.load()

    with st.form("llm_config"):
        st.text_input("模型", value=config.llm.model, disabled=True,
                      help="在 config.yaml 中修改")
        st.text_input("API 地址", value=config.llm.base_url, disabled=True)
        st.text_input("API Key", value=config.llm.api_key[:8] + "..." if config.llm.api_key else "(未设置)",
                      disabled=True)

        new_temperature = st.slider("Temperature", 0.0, 1.0, config.llm.temperature, 0.05)
        new_max_tokens = st.number_input("Max Tokens", 512, 32768, config.llm.max_tokens, 512)

        if st.form_submit_button("💾 保存设置", type="primary"):
            config.llm.temperature = new_temperature
            config.llm.max_tokens = new_max_tokens
            try:
                config.save()
                st.success("✅ 设置已保存（重启 UI 后生效）")
            except Exception as e:
                st.error(f"保存失败: {e}")

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

    if st.button("💾 应用模式"):
        config.manager.mode = selected_mode
        try:
            config.save()
            st.success(f"✅ 已切换到 {mode_labels[selected_mode]}")
        except Exception as e:
            st.error(f"保存失败: {e}")

    st.divider()

    # ── 分析方法 ────────────────────────────────────────────
    st.markdown("### 📊 分析方法")

    reg = load_plugins()
    summary = reg.summary()

    col1, col2 = st.columns(2)
    col1.metric("内置方法", summary["total_methods"])
    col2.metric("可用标签", len(summary["by_tag"]))

    # 按标签分组展示
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

    from ...guardrails.statistical import StatisticalGuardrails
    g = StatisticalGuardrails()

    st.success(f"强制级规则: {len(g.mandatory_rules)} 条")
    st.warning(f"警告级规则: {len(g.warning_rules)} 条")
    st.info(f"提示级规则: {len(g.suggestion_rules)} 条")

    with st.expander("查看详细规则"):
        for rule in g.mandatory_rules:
            st.markdown(f"🚫 **{rule.rule_name}**")
            st.caption(rule.description[:100])
        for rule in g.warning_rules:
            st.markdown(f"⚠️ **{rule.rule_name}**")
            st.caption(rule.description[:100])
        for rule in g.suggestion_rules:
            st.markdown(f"💡 **{rule.rule_name}**")
            st.caption(rule.description[:100])

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
