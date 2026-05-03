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


def render() -> None:
    pm: ProjectManager = st.session_state.project_manager
    projects = pm.list()

    # ── 项目概况 ─────────────────────────────────────────────
    st.markdown("### 📊 项目概况")

    if not projects:
        st.info("还没有任何项目，请创建新项目。")
        st.caption(f"项目保存在：{pm.base_dir}")
    else:
        total_runs = sum(p.run_count for p in projects)
        total_files = sum(len(p.data_files) for p in projects)
        col1, col2, col3 = st.columns(3)
        col1.metric("项目数", len(projects))
        col2.metric("总分析次数", total_runs)
        col3.metric("总数据文件", total_files)

        # 项目列表（紧凑单行）
        sorted_projects = sorted(projects, key=lambda x: x.last_run or x.created_at, reverse=True)
        for p in sorted_projects:
            col_n, col_d, col_r, col_a = st.columns([3, 2, 1, 2])

            with col_n:
                st.markdown(f"**📁 {p.name}**")
                if p.description:
                    st.caption(p.description[:40] + ("…" if len(p.description) > 40 else ""))

            with col_d:
                files = [f.name for f in p.data_files]
                if files:
                    st.caption(f"📄 {len(files)} 个文件")

            with col_r:
                if p.last_run:
                    st.caption(p.last_run.strftime("%m-%d %H:%M"))
                else:
                    st.caption(p.created_at.strftime("创建%m-%d"))

            with col_a:
                c1, c2, c3 = st.columns(3)
                if c1.button("🚀", key=_project_key(p.name, "a"), use_container_width=True, help="分析"):
                    st.session_state.current_project = p.name
                    st.session_state.nav_page = "analyze"
                    st.rerun()
                if c2.button("📋", key=_project_key(p.name, "r"), use_container_width=True, help="报告"):
                    st.session_state.current_project = p.name
                    st.session_state.nav_page = "report"
                    st.rerun()
                if c3.button("🗑️", key=_project_key(p.name, "d"), use_container_width=True, help="删除"):
                    st.session_state[_project_key(p.name, "confirm")] = True

                if st.session_state.get(_project_key(p.name, "confirm")):
                    st.warning(f"确定删除「{p.name}」？")
                    cy, cn = st.columns(2)
                    if cy.button("✅ 确认", key=_project_key(p.name, "y")):
                        pm.delete(p.name)
                        st.rerun()
                    if cn.button("❌ 取消", key=f"cn_{p.name}"):
                        st.session_state.pop(_project_key(p.name, "confirm"), None)
                        st.rerun()

            st.divider()

    # ── 新建项目 ─────────────────────────────────────────────
    st.markdown("### ➕ 新建项目")

    name = st.text_input(
        "项目名称",
        placeholder="例如: Q1渠道ROI分析",
        label_visibility="collapsed",
    )
    desc = st.text_area(
        "项目描述（选填）",
        placeholder="简要描述这个项目...",
        label_visibility="collapsed",
    )

    folder_path = st.text_input(
        "📂 项目位置",
        value=str(pm.base_dir),
        placeholder=str(pm.base_dir),
        label_visibility="collapsed",
    )
    st.caption(f"项目将创建于：{folder_path}/{name}")

    if st.button("💾 创建项目", type="primary", use_container_width=True):
        if not name:
            st.warning("请填写项目名称")
        else:
            try:
                pm.create(name, description=desc or "", parent_dir=Path(folder_path))
                st.success(f"✅ 项目「{name}」创建成功！")
                st.session_state.current_project = name
                st.session_state.nav_page = "analyze"
                st.rerun()
            except FileExistsError:
                st.error(f"项目「{name}」已存在")
            except FileNotFoundError:
                st.error(f"路径不存在：{folder_path}")
            except Exception as e:
                st.error(f"创建失败: {e}")
