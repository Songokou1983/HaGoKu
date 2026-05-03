"""HaGoKu Streamlit UI — 项目总览页面"""

from __future__ import annotations

import hashlib
import tempfile
import streamlit as st
from datetime import datetime
from pathlib import Path

from hagokyu.storage.project_manager import ProjectManager

# 内置演示数据集（与 CLI 保持一致）
DEMO_DATASETS = {
    "ad_campaign": {
        "name": "📢 广告投放数据",
        "desc": "百度/抖音/微信 3 渠道的展示/点击/消费/收入",
        "query": "哪个广告渠道的 ROI 最高？各渠道转化率有何差异？",
        "file": "demo_ad_campaign.csv",
    },
    "conversion": {
        "name": "🔽 转化漏斗数据",
        "desc": "访问→注册→加购→下单→付款的全链路转化漏斗",
        "query": "分析各渠道的转化漏斗，哪个环节流失最严重？",
        "file": "demo_conversion.csv",
    },
    "user_cohort": {
        "name": "👤 用户队列数据",
        "desc": "用户渠道来源、消费行为、会员等级",
        "query": "各渠道用户质量和价值有什么差异？哪些是高价值用户群？",
        "file": "demo_user_cohort.csv",
    },
}


def _get_demo_path(name: str) -> Path | None:
    """解析 demo 数据集路径（包内/本地两种模式）"""
    filename = DEMO_DATASETS[name]["file"]
    # 包内
    try:
        import hagokyu
        # hagokyu.__file__ = hagokyu/__init__.py
        pkg_proj = Path(hagokyu.__file__).parent.parent  # = 项目根/
        pkg_demo = pkg_proj / "examples" / filename
        if pkg_demo.exists():
            return pkg_demo
    except Exception:
        pass
    # 本地源码（从 hagokyu/ui/pages/app_projects.py → 项目根 = 上3级 parent）
    this_file = Path(__file__)
    project_root = this_file.parent.parent.parent
    local = project_root / "examples" / filename
    if local.exists():
        return local
    return None


def _project_key(name: str, suffix: str) -> str:
    """生成安全的 session_state key（项目名含特殊字符时用哈希）"""
    # 中文/空格/特殊字符 → 统一用 md5 前8位哈希
    safe = hashlib.md5(name.encode()).hexdigest()[:8]
    return f"{suffix}_{safe}"


def _launch_demo(name: str) -> None:
    """加载演示数据并跳转到分析页面"""
    info = DEMO_DATASETS[name]
    src = _get_demo_path(name)
    if src is None:
        st.error(f"找不到演示数据: {name}")
        return

    # 复制到临时文件（analyze 页面的清理逻辑会负责删除）
    suffix = src.suffix
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(src.read_bytes())
        tmp_path = f.name

    st.session_state._demo_file = tmp_path
    st.session_state._demo_name = info["name"]
    st.session_state._demo_query = info["query"]
    st.session_state.nav_page = "analyze"
    st.rerun()


def render() -> None:
    pm: ProjectManager = st.session_state.project_manager
    projects = pm.list()

    # ── 空状态引导（无项目时显示）────────────────────────────
    if not projects:
        st.divider()

        # 演示数据区
        st.markdown("### 🚀 快速体验")
        st.caption("无需准备数据，点击即可体验完整分析流程")

        cols = st.columns(len(DEMO_DATASETS))
        for (key, info), col in zip(DEMO_DATASETS.items(), cols):
            with col:
                with st.container(border=True):
                    st.markdown(f"**{info['name']}**")
                    st.caption(info["desc"])
                    if st.button("▶ 立即体验", key=f"demo_{key}", use_container_width=True):
                        _launch_demo(key)

        st.divider()

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
                    st.rerun()
                except FileExistsError:
                    st.error(f"项目 '{name}' 已存在")
                except Exception as e:
                    st.error(f"创建失败: {e}")

    # 统计概览
    total_runs = sum(p.run_count for p in projects)
    total_files = sum(len(p.data_files) for p in projects)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("项目数", len(projects))
    col2.metric("总分析次数", total_runs)
    col3.metric("总数据文件", total_files)
    with col4:
        if st.button("🚀 体验演示数据", use_container_width=True):
            _launch_demo("ad_campaign")

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
