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


def _safe_stats(pm, project: str) -> dict:
    """安全获取存储统计（pm 为 None 时返回空字典）"""
    try:
        return pm.get_storage_stats(project)
    except Exception:
        return {}


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


def _safe_pm() -> ProjectManager | None:
    """安全获取 ProjectManager（可能为 None）"""
    try:
        pm = st.session_state.get("project_manager")
        if pm is None:
            from hagokyu.config import HaGoKuConfig
            from hagokyu.storage.project_manager import ProjectManager
            pm = ProjectManager(HaGoKuConfig.load().output.project_dir)
            st.session_state.project_manager = pm
        return pm
    except Exception:
        return None


def _render_project_card(p, pm: ProjectManager | None) -> None:
    """渲染单个项目卡片，一行排列"""
    col_name, col_desc, col_time, col_a, col_b, col_c, col_d = st.columns([2, 5, 2, 1, 1, 1, 1])
    with col_name:
        st.markdown(f"<span style='font-size:17px;'>{p.name}</span>", unsafe_allow_html=True)
    with col_desc:
        st.markdown(f"<span style='font-size:15px;color:#9ca3af;'>{p.description[:60] + ('…' if p.description and len(p.description) > 60 else '')}</span>", unsafe_allow_html=True)
    with col_time:
        if p.last_run:
            st.markdown(f"<span style='font-size:14px;color:#6e7681;'>🔄 更新于 {p.last_run.strftime('%m-%d %H:%M')}</span>", unsafe_allow_html=True)
        else:
            st.markdown(f"<span style='font-size:14px;color:#6e7681;'>📅 创建于 {p.created_at.strftime('%m-%d')}</span>", unsafe_allow_html=True)
    with col_a:
        if st.button("🚀", key=_project_key(p.name, "a"), help="分析"):
            st.session_state.current_project = p.name
            st.session_state.nav_page = "analyze"
            st.rerun()
    with col_b:
        if st.button("📋", key=_project_key(p.name, "r"), help="报告"):
            st.session_state.current_project = p.name
            st.session_state.nav_page = "report"
            st.rerun()
    with col_c:
        if st.button("📝", key=_project_key(p.name, "e"), help="编辑"):
            st.session_state[_project_key(p.name, "edit_desc")] = True
            st.rerun()
    with col_d:
        if st.button("🗑️", key=_project_key(p.name, "d"), help="删除"):
            st.session_state[_project_key(p.name, "confirm")] = True
            st.rerun()

    # 删除确认
    if st.session_state.get(_project_key(p.name, "confirm")):
        st.warning(f"确定删除「{p.name}」？此操作不可逆！")
        cy, cn = st.columns(2)
        if cy.button("✅ 确认删除", key=_project_key(p.name, "y"), type="primary"):
            if pm:
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
            if pm:
                pm.update_description(p.name, new_desc)
            st.session_state.pop(_project_key(p.name, "edit_desc"), None)
            st.rerun()
        if c_cancel.button("取消", key=_project_key(p.name, "cancel_desc")):
            st.session_state.pop(_project_key(p.name, "edit_desc"), None)
            st.rerun()

    # st.divider()


def render() -> None:
    pm = _safe_pm()
    if pm is None:
        st.error("❌ 项目管理器初始化失败，请重启 UI（执行 `pip install -e .`）")
        return

    projects = pm.list()

    # ── 项目概况 ─────────────────────────────────────────────
    st.markdown("# 📊 项目概况")

    if not projects:
        st.info("还没有任何项目，请创建新项目。")
        st.caption(f"📂 项目保存在：{pm.base_dir}")
    else:
        # 表头
        h_name, h_desc, h_time, h_btn = st.columns([2, 5, 2, 4])
        with h_name:
            st.markdown("<div style='text-align:center;'>**项目名称**</div>", unsafe_allow_html=True)
        with h_desc:
            st.markdown("<div style='text-align:center;'>**项目描述**</div>", unsafe_allow_html=True)
        with h_time:
            st.markdown("<div style='text-align:center;'>**更新时间**</div>", unsafe_allow_html=True)
        with h_btn:
            st.markdown("<div style='text-align:center;'>**操作**</div>", unsafe_allow_html=True)

        st.divider()

        # 项目卡片列表（按最近活动时间排序）
        sorted_projects = sorted(
            projects, key=lambda x: x.last_run or x.created_at, reverse=True
        )
        for p in sorted_projects:
            _render_project_card(p, pm)

    # ── 新建项目 ─────────────────────────────────────────────
    st.markdown("# ➕ 新建项目")

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
