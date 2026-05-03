"""HaGoKu Streamlit UI — 项目管理页面"""

from __future__ import annotations

import hashlib
import streamlit as st
from pathlib import Path

from hagokyu.storage.project_manager import ProjectManager


def _project_key(name: str, suffix: str) -> str:
    """生成安全的 session_state key（项目名含特殊字符时用哈希）"""
    safe = hashlib.md5(name.encode()).hexdigest()[:8]
    return f"{suffix}_{safe}"


def _render_storage_badge(stats: dict) -> str:
    """生成存储统计徽章 HTML"""
    if not stats:
        return ""
    total = stats.get("total", {})
    parts = []
    for subdir in ("input", "process", "output", "memory"):
        s = stats.get(subdir, {})
        if s.get("count", 0) > 0:
            emoji = {"input": "📥", "process": "⚙️", "output": "📤", "memory": "🧠"}.get(subdir, "📁")
            parts.append(f"{emoji}{s['count']}份")
    if not parts:
        return "空项目"
    size_mb = total.get("size_mb", 0)
    size_str = f"({size_mb:.1f}MB)" if size_mb > 0 else ""
    return "  ".join(parts) + f"  💾{size_str}"


def _render_project_card(p, pm: ProjectManager) -> None:
    """渲染单个项目卡片"""
    # 顶部行：名称 + 操作按钮
    col_n, col_a = st.columns([4, 2])
    with col_n:
        st.markdown(f"**📁 {p.name}**")
        if p.description:
            st.caption(p.description[:50] + ("…" if len(p.description) > 50 else ""))

    with col_a:
        c1, c2, c3, c4 = st.columns(4)
        if c1.button("🚀", key=_project_key(p.name, "a"), use_container_width=True, help="分析"):
            st.session_state.current_project = p.name
            st.session_state.nav_page = "analyze"
            st.rerun()
        if c2.button("📋", key=_project_key(p.name, "r"), use_container_width=True, help="报告"):
            st.session_state.current_project = p.name
            st.session_state.nav_page = "report"
            st.rerun()
        if c3.button("📝", key=_project_key(p.name, "e"), use_container_width=True, help="编辑描述"):
            st.session_state[_project_key(p.name, "edit_desc")] = True
            st.rerun()
        if c4.button("🗑️", key=_project_key(p.name, "d"), use_container_width=True, help="删除"):
            st.session_state[_project_key(p.name, "confirm")] = True
            st.rerun()

    # 删除确认
    if st.session_state.get(_project_key(p.name, "confirm")):
        st.warning(f"确定删除「{p.name}」？此操作不可逆！")
        cy, cn = st.columns(2)
        if cy.button("✅ 确认删除", key=_project_key(p.name, "y"), type="primary"):
            pm.delete(p.name)
            st.rerun()
        if cn.button("❌ 取消", key=_project_key(p.name, "cn")):
            st.session_state.pop(_project_key(p.name, "confirm"), None)
            st.rerun()

    # 编辑描述
    if st.session_state.get(_project_key(p.name, "edit_desc")):
        new_desc = st.text_area(
            "项目描述",
            value=p.description,
            key=_project_key(p.name, "desc_input"),
            label_visibility="collapsed",
        )
        c_save, c_cancel = st.columns(2)
        if c_save.button("💾 保存", key=_project_key(p.name, "save_desc"), type="primary"):
            pm.update_description(p.name, new_desc)
            st.session_state.pop(_project_key(p.name, "edit_desc"), None)
            st.rerun()
        if c_cancel.button("取消", key=_project_key(p.name, "cancel_desc")):
            st.session_state.pop(_project_key(p.name, "edit_desc"), None)
            st.rerun()

    # 元信息行：时间 / 文件统计
    col_t, col_s = st.columns([1, 3])
    with col_t:
        if p.last_run:
            st.caption(f"🔄 最近 {p.last_run.strftime('%m-%d %H:%M')}")
        else:
            st.caption(f"📅 创建于 {p.created_at.strftime('%m-%d')}")

    with col_s:
        stats = pm.get_storage_stats(p.name)
        badge = _render_storage_badge(stats)
        if badge:
            st.caption(badge)

    # 展开详情：记忆笔记 + 数据文件列表
    with st.expander("🔽 展开详情"):
        # 记忆笔记
        notes = pm.load_memory(p.name)
        st.markdown("**🧠 项目记忆**")
        new_notes = st.text_area(
            "记忆笔记（支持 Markdown）",
            value=notes,
            height=120,
            key=_project_key(p.name, "notes_input"),
            label_visibility="collapsed",
            placeholder="记录这个项目的背景、目标、关键发现...",
        )
        if st.button("💾 保存记忆", key=_project_key(p.name, "save_notes")):
            pm.save_memory(p.name, new_notes)
            st.success("✅ 记忆已保存")
            st.rerun()

        # 数据文件列表
        if p.data_files:
            st.markdown("**📥 数据文件**")
            for f in p.data_files:
                size_str = f"{f.size_kb:.1f}KB" if f.size_kb < 1024 else f"{f.size_kb/1024:.1f}MB"
                st.markdown(f"- `{f.name}` — {size_str}，{f.added_at.strftime('%m-%d %H:%M')}")

        # 过程文件列表
        proj_info = pm.info(p.name)
        if proj_info and proj_info.process_files:
            st.markdown("**⚙️ 过程文件**")
            for f in proj_info.process_files:
                size_str = f"{f.size_kb:.1f}KB" if f.size_kb < 1024 else f"{f.size_kb/1024:.1f}MB"
                st.markdown(f"- `{f.name}` — {size_str}")

    st.divider()


def render() -> None:
    pm: ProjectManager = st.session_state.project_manager
    projects = pm.list()

    # ── 项目概况 ─────────────────────────────────────────────
    st.markdown("### 📊 项目概况")

    if not projects:
        st.info("还没有任何项目，请创建新项目。")
        st.caption(f"📂 项目保存在：{pm.base_dir}")
    else:
        total_runs = sum(p.run_count for p in projects)
        total_files = sum(len(p.data_files) for p in projects)
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("项目数", len(projects))
        col2.metric("总分析次数", total_runs)
        col3.metric("总数据文件", total_files)
        # 总存储
        total_size_mb = 0.0
        for p in projects:
            stats = pm.get_storage_stats(p.name)
            total_size_mb += stats.get("total", {}).get("size_mb", 0.0)
        col4.metric("总存储", f"{total_size_mb:.1f} MB")

        st.divider()

        # 项目卡片列表（按最近活动时间排序）
        sorted_projects = sorted(
            projects, key=lambda x: x.last_run or x.created_at, reverse=True
        )
        for p in sorted_projects:
            _render_project_card(p, pm)

    # ── 新建项目 ─────────────────────────────────────────────
    st.markdown("### ➕ 新建项目")

    name = st.text_input(
        "项目名称",
        placeholder="例如: Q1渠道ROI分析",
        label_visibility="collapsed",
    )
    desc = st.text_area(
        "项目描述（选填）",
        placeholder="简要描述这个项目：背景、目标、分析范围...",
        label_visibility="collapsed",
        height=80,
    )
    st.caption(f"📂 项目将保存至：{pm.base_dir}")

    if st.button("💾 创建项目", type="primary", use_container_width=True):
        if not name:
            st.warning("请填写项目名称")
        else:
            try:
                pm.create(name, description=desc or "")
                st.success(f"✅ 项目「{name}」创建成功！")
                st.session_state.current_project = name
                st.session_state.nav_page = "analyze"
                st.rerun()
            except FileExistsError:
                st.error(f"项目「{name}」已存在")
            except Exception as e:
                st.error(f"创建失败: {e}")
