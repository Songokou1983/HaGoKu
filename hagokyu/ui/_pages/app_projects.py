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


def _pick_folder(initial: str = "") -> str | None:
    """弹出系统文件夹选择对话框，返回选中的目录路径。"""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askdirectory(initialdir=initial or None)
        root.destroy()
        return path if path else None
    except Exception:
        return None


def render() -> None:
    pm: ProjectManager = st.session_state.project_manager
    projects = pm.list()

    # ── 项目概况 ─────────────────────────────────────────────
    st.markdown("### 📊 项目概况")

    if not projects:
        st.info("还没有任何项目，请创建新项目。")
    else:
        total_runs = sum(p.run_count for p in projects)
        total_files = sum(len(p.data_files) for p in projects)
        col1, col2, col3 = st.columns(3)
        col1.metric("项目数", len(projects))
        col2.metric("总分析次数", total_runs)
        col3.metric("总数据文件", total_files)

        st.divider()

        # 项目卡片
        for p in sorted(projects, key=lambda x: x.last_run or x.created_at, reverse=True):
            with st.container():
                c1, c2, c3 = st.columns([3, 1, 1])

                with c1:
                    st.markdown(f"**📁 {p.name}**")
                    if p.description:
                        st.caption(p.description)
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

                    if st.session_state.get(_project_key(p.name, "confirm")):
                        st.warning(f"确定删除 '{p.name}'？")
                        c_yes, c_no = st.columns(2)
                        if c_yes.button("✅ 确认", key=_project_key(p.name, "yes")):
                            pm.delete(p.name)
                            st.success(f"已删除: {p.name}")
                            st.rerun()
                        if c_no.button("❌ 取消", key=f"cn_{p.name}"):
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

    # 目录选择（必填）
    default_dir = str(Path.home())
    col_dir, col_btn = st.columns([4, 1])
    with col_dir:
        parent_dir = st.text_input(
            "项目位置",
            value=st.session_state.get("_new_project_dir", default_dir),
            placeholder="选择或输入文件夹路径",
            label_visibility="collapsed",
        )
    with col_btn:
        st.markdown("")  # 对齐
        if st.button("📂 选择", use_container_width=True):
            picked = _pick_folder(parent_dir or default_dir)
            if picked:
                st.session_state._new_project_dir = picked
                st.rerun()

    desc = st.text_area(
        "项目描述（选填）",
        placeholder="简要描述这个项目...",
        label_visibility="collapsed",
    )

    if st.button("💾 创建项目", type="primary", use_container_width=True):
        if not name:
            st.warning("请填写项目名称")
        elif not parent_dir:
            st.warning("请选择项目位置")
        else:
            try:
                pm.create(name, description=desc or "", parent_dir=Path(parent_dir))
                st.success(f"✅ 项目 '{name}' 创建成功！")
                st.session_state.pop("_new_project_dir", None)
                st.session_state.current_project = name
                st.session_state.nav_page = "analyze"
                st.rerun()
            except FileExistsError:
                st.error(f"项目 '{name}' 已存在")
            except Exception as e:
                st.error(f"创建失败: {e}")
