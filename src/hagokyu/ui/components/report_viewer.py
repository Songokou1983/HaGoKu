"""HaGoKu Streamlit UI — 报告查看器组件"""

from __future__ import annotations

from pathlib import Path

import streamlit as st


def render_html_report(html_path: str | Path, height: int = 800) -> bool:
    """
    在 Streamlit 中渲染 HTML 报告

    Args:
        html_path: HTML 文件路径
        height: 高度（像素）

    Returns:
        是否成功渲染
    """
    from pathlib import Path
    p = Path(html_path)

    if not p.exists():
        st.error(f"报告文件不存在: {html_path}")
        return False

    # 读取 HTML 内容
    html_content = p.read_text(encoding="utf-8")

    # 使用 st.html() 渲染（Streamlit 1.28+）
    try:
        st.html(f"<div style='height:{height}px;overflow-y:auto;'>{html_content}</div>")
        return True
    except Exception:
        # 降级：直接显示文件路径
        st.info(f"📄 报告已生成: `{html_path}`")
        st.text(p.read_text(encoding="utf-8")[:2000])
        return True


def report_card(result: dict) -> None:
    """
    显示单个分析结果的卡片

    Args:
        result: AnalysisResult.to_dict()
    """
    analysis_type = result.get("analysis_type", "?")
    question = result.get("question", "")
    conclusion = result.get("conclusion_plain", "")
    p_value = result.get("p_value")
    effect_size = result.get("effect_size")
    significance = result.get("significance", "")

    # 图标
    icons = {
        "regression": "📈",
        "hypothesis_test": "🔬",
        "correlation": "🔗",
        "trend_analysis": "📊",
        "hypothesis_test_mann_whitney": "🔬",
        "hypothesis_test_kruskal_wallis": "🔬",
        "interaction_analysis": "⚡",
    }
    icon = icons.get(analysis_type, "📊")

    with st.container():
        col1, col2 = st.columns([3, 1])

        with col1:
            st.markdown(f"**{icon} {question or '分析结果'}**")
            st.caption(f"类型: `{analysis_type}`")
            if conclusion:
                st.info(conclusion[:300])

        with col2:
            # 显著性指示
            if significance == "significant":
                st.success("✅ 显著")
            elif significance == "not_significant":
                st.warning("⚠️ 不显著")
            elif significance == "not_significant_after_correction":
                st.error("❌ 校正后不显著")

            if p_value is not None:
                try:
                    p_num = float(p_value)
                    st.metric("p值", f"{p_num:.4f}")
                except (ValueError, TypeError):
                    pass

            if effect_size is not None:
                try:
                    es_num = float(effect_size)
                    st.metric("效应量", f"{es_num:.3f}")
                except (ValueError, TypeError):
                    pass

        st.divider()


def results_summary(results: list[dict]) -> None:
    """显示分析结果摘要（用于报告页）"""
    if not results:
        st.info("暂无分析结果")
        return

    n_sig = sum(
        1 for r in results
        if r.get("significance") == "significant"
    )
    n_total = len(results)

    col1, col2 = st.columns(2)
    col1.metric("分析数量", n_total)
    col2.metric("显著发现", n_sig, delta_color="normal" if n_sig > 0 else "off")

    st.divider()

    # 结果卡片列表
    for i, result in enumerate(results):
        report_card(result)
