"""HaGoKu Streamlit UI — 项目管理页面"""

from __future__ import annotations

import hashlib
import streamlit as st
from pathlib import Path

from hagokyu.storage.project_manager import ProjectManager


def _project_key(name: str, suffix: str) -> str:
    """生成安全的 session_state key（项目名含特殊字符时用哈希）"""
    # 中文/空格/特殊字符 → 统一用 md5 前8位哈希
    safe = hashlib.md5(name.encode()).hexdigest()[:8]
    return f"{suffix}_{safe}"


def render() -> None:
    pm: ProjectManager = st.session_state.project_manager
    projects = pm.list()

    # ── 空状态引导（无项目时显示）────────────────────────────
    if not projects:
        st.divider()
        st.info("还没有任何项目，请先创建一个项目。")
        st.caption("创建项目后，在分析页面中上传数据并开始分析。")

        # 新建项目
        st.markdown("### 📁 创建新项目")
        with st.expander("➕ 新建空白项目", expanded=True):
            name = st.text_input("项目名称", placeholder="例如: Q1渠道ROI分析")
            desc = st.text_area("描述", placeholder="简要描述这个项目...")
            custom_dir = st.checkbox("📂 自定义项目位置")
            parent_dir = None
            if custom_dir:
                parent_dir = st.text_input(
                    "项目存放目录",
                    value=str(pm.base_dir),
                    placeholder=str(pm.base_dir),
                )
            if st.button("创建项目", type="primary") and name:
                try:
                    from pathlib import Path
                    parent = Path(parent_dir) if parent_dir else None
                    pm.create(name, description=desc or "", parent_dir=parent)
                    st.success(f"✅ 项目 '{name}' 创建成功！")
                    st.session_state.current_project = name
                    st.session_state.nav_page = "analyze"
                    st.rerun()
                except FileExistsError:
                    st.error(f"项目 '{name}' 已存在")
                except Exception as e:
                    st.error(f"创建失败: {e}")

        st.divider()
        # 底部说明
        st.caption(
            "💡 也可以直接在 **分析页面** 上传数据，无需先创建项目。"
        )
        return

    # ── 有项目时的界面 ───────────────────────────────────────
    # 新建项目
    col1, col2 = st.columns([2, 1])
    with col1:
        with st.expander("➕ 新建项目", expanded=False):
            name = st.text_input("项目名称", placeholder="例如: Q1渠道ROI分析")
            desc = st.text_area("描述", placeholder="简要描述这个项目...")
            custom_dir = st.checkbox("📂 自定义项目位置")
            parent_dir = None
            if custom_dir:
                parent_dir = st.text_input(
                    "项目存放目录",
                    value=str(pm.base_dir),
                    placeholder=str(pm.base_dir),
                )
            if st.button("创建项目", type="primary") and name:
                try:
                    from pathlib import Path
                    parent = Path(parent_dir) if parent_dir else None
                    pm.create(name, description=desc or "", parent_dir=parent)
                    st.success(f"✅ 项目 '{name}' 创建成功！")
                    st.session_state.current_project = name
                    st.session_state.nav_page = "analyze"
                    st.rerun()
                except FileExistsError:
                    st.error(f"项目 '{name}' 已存在")
                except Exception as e:
                    st.error(f"创建失败: {e}")

    # 统计概览
    total_runs = sum(p.run_count for p in projects)
    total_files = sum(len(p.data_files) for p in projects)
    col1, col2, col3 = st.columns(3)
    col1.metric("项目数", len(projects))
    col2.metric("总分析次数", total_runs)
    col3.metric("总数据文件", total_files)

    st.divider()

    # 项目卡片网格
    for p in sorted(projects, key=lambda x: x.last_run or x.created_at, reverse=True):
        with st.container():
            c1, c2, c3 = st.columns([3, 1, 1])

            with c1:
                st.markdown(f"### 📁 {p.name}")
                if p.description:
                    st.caption(p.description)

                # 数据文件标签
                file_names = [f.name for f in p.data_files]
                if file_names:
                    st.write("📄 " + " | ".join(f"`{n}`" for n in file_names[:3]))
                    if len(file_names) > 3:
                        st.caption(f"...还有 {len(file_names)-3} 个文件")

            with c2:
                st.metric("运行", p.run_count)
                if p.last_run:
                    st.caption(f"最近: {p.last_run.strftime('%m-%d %H:%M')}")

            with c3:
                created = p.created_at.strftime("%Y-%m-%d")
                st.caption(f"创建于 {created}")

                # 快捷按钮
                if st.button("🚀 分析", key=_project_key(p.name, "analyze"), use_container_width=True):
                    st.session_state.current_project = p.name
                    st.session_state.nav_page = "analyze"
                    st.rerun()

                if st.button("📋 报告", key=_project_key(p.name, "rp"), use_container_width=True):
                    st.session_state.current_project = p.name
                    st.session_state.nav_page = "report"
                    st.rerun()

                if st.button("🗑️", key=_project_key(p.name, "del"), use_container_width=True):
                    st.session_state[_project_key(p.name, "confirm")] = True

                # 删除确认
                if st.session_state.get(_project_key(p.name, "confirm")):
                    st.warning(f"确定删除 '{p.name}'？")
                    c1, c2 = st.columns(2)
                    if c1.button("✅ 确认删除", key=_project_key(p.name, "yes")):
                        pm.delete(p.name)
                        st.success(f"已删除: {p.name}")
                        st.rerun()
                    if c2.button("❌ 取消", key=f"confirm_no_{p.name}"):
                        st.session_state[f"confirm_delete_{p.name}"] = False
                        st.rerun()

            st.divider()
