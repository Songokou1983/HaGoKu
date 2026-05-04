"""HaGoKu Streamlit UI — 知识库页面"""

from __future__ import annotations

import streamlit as st

from hagokyu.kb import get_knowledge_base, retrieve_knowledge

CATEGORY_LABELS = {
    "stats": "📊 统计分析",
    "financial": "💰 财务分析",
    "business": "📈 商业分析",
}
CATEGORY_COLORS = {
    "stats": "#f59e0b",
    "financial": "#4ade80",
    "business": "#22d3ee",
}


def render() -> None:
    st.session_state.nav_page = "knowledge"
    st.markdown("### 📚 知识库")

    kb = get_knowledge_base()
    categories = kb.categories()

    # 搜索栏
    col_search, col_btn = st.columns([1, 5])
    with col_search:
        search_query = st.text_input(
            "搜索",
            placeholder="如：ROI、t检验、A/B测试、Cohort...",
            label_visibility="collapsed",
            key="kb_main_search",
        )

    active_entry = st.session_state.get("kb_main_active_entry")

    if search_query:
        results = retrieve_knowledge(context=search_query, limit=5)
        if results:
            for r in results:
                color = CATEGORY_COLORS.get(r["category"], "#888")
                label = CATEGORY_LABELS.get(r["category"], r["category"])
                if st.button(
                    f"{label} · {r['title']} →",
                    use_container_width=True,
                    key=f"kb_sr_{r['title']}",
                ):
                    st.session_state.kb_main_active_entry = r
                    st.session_state.kb_main_search = ""
                    st.rerun()
        else:
            st.info("未找到相关内容，试试其他关键词")
        st.divider()

    # 左右布局：左侧固定 + 竖线隔开 + 右侧滚动
    col_left, col_mid, col_right = st.columns([1, 0.02, 3])

    with col_left:
        with st.container(height=600, border=False):
            st.markdown("**分类浏览**")
            for cat in categories:
                entries = kb.get_by_category(cat)
                label = CATEGORY_LABELS.get(cat, cat)
                color = CATEGORY_COLORS.get(cat, "#888")
                with st.expander(f"{label}（{len(entries)}）", expanded=True):
                    for entry in entries:
                        marker = "▸ " if active_entry and active_entry.get("title") == entry["title"] else ""
                        if st.button(
                            f"{marker}{entry['title']}",
                            use_container_width=True,
                            help=entry.get("summary", ""),
                            key=f"kb_item_{entry['title']}",
                        ):
                            full = kb.retrieve(keywords=[entry["title"]], limit=1)
                            if full:
                                st.session_state.kb_main_active_entry = full[0]
                                st.rerun()

    with col_mid:
        st.markdown(
            """<div style="border-left: 1px solid #333; height: 100%; margin: 0 8px;"></div>""",
            unsafe_allow_html=True,
        )

    with col_right:
        with st.container(height=600, border=False):
            if active_entry:
                color = CATEGORY_COLORS.get(active_entry.get("category", ""), "#888")
                label = CATEGORY_LABELS.get(active_entry.get("category", ""), "")
                st.markdown(
                    f"<span style='color:{color};font-weight:bold'>{label}</span> — "
                    f"<strong style='font-size:1.1em'>{active_entry['title']}</strong>",
                    unsafe_allow_html=True,
                )
                st.caption(active_entry.get("summary", ""))
                st.divider()

                content = active_entry.get("content", "")
                if content:
                    st.markdown(content, unsafe_allow_html=True)
                else:
                    st.caption("（无正文内容）")

                if st.button("✕ 关闭", key="kb_close_main"):
                    st.session_state.kb_main_active_entry = None
                    st.rerun()
            else:
                # 空状态引导
                st.markdown("""
                <div style="padding: 2rem; text-align: center; color: #6e7681;">
                    <div style="font-size: 3rem;">📚</div>
                    <div style="margin-top: 0.5rem;">选择左侧条目查看内容</div>
                    <div style="font-size: 0.85rem; margin-top: 0.5rem;">
                        或在上方搜索框输入关键词
                    </div>
                </div>
                """, unsafe_allow_html=True)
