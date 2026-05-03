"""HaGoKu Streamlit UI — 文件上传组件

提供上传数据文件、保存临时文件、数据预览等功能。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st


def save_uploaded_file(uploaded) -> str:
    """将 Streamlit 上传的文件保存到临时文件，返回文件路径。

    调用方负责在分析结束时清理临时文件（见 cleanup_temp_file）。
    """
    suffix = Path(uploaded.name).suffix
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False, mode="wb") as f:
        f.write(uploaded.getvalue())
        return f.name


def cleanup_temp_file(path: str | None = None) -> None:
    """清理单个临时上传文件路径。"""
    if path and Path(path).exists():
        try:
            Path(path).unlink()
        except OSError:
            pass


def cleanup_session_temp() -> None:
    """清理 session_state 中遗留的临时上传文件（用于页面加载时自动清理）。"""
    path = st.session_state.pop("_temp_uploaded_path", None)
    if path:
        cleanup_temp_file(path)


def render_data_preview(data_path: str) -> bool:
    """渲染数据预览：形状 + 前5行 + 字段类型。

    Returns:
        True if preview rendered successfully, False if failed.
    """
    try:
        import pandas as pd

        suffix = Path(data_path).suffix.lower()
        df = None
        errors: list[str] = []

        if suffix == ".parquet":
            try:
                df = pd.read_parquet(data_path)
            except Exception as e:
                errors.append(f"Parquet 解析失败: {e}")
        elif suffix in (".xlsx", ".xls"):
            try:
                df = pd.read_excel(data_path, nrows=2000)
            except Exception as e:
                errors.append(f"Excel 解析失败: {e}")
        elif suffix == ".json":
            try:
                df = pd.read_json(data_path, nrows=2000)
            except Exception:
                try:
                    df = pd.read_json(data_path, lines=True, nrows=2000)
                except Exception as e2:
                    errors.append(f"JSON 解析失败: {e2}")
        else:
            # CSV：尝试多种分隔符
            for sep in [",", ";", "\t"]:
                try:
                    df = pd.read_csv(data_path, sep=sep, nrows=2000, on_bad_lines="skip")
                    if df.shape[1] > 1:
                        break
                except Exception:
                    continue

        if df is None or df.empty:
            st.warning(
                "⚠️ 无法预览数据：格式无法识别，"
                "请确认文件是有效的 CSV/Excel/JSON/Parquet。"
            )
            if errors:
                for err in errors:
                    st.caption(f"  - {err}")
            return False

        rows, cols = df.shape
        c1, c2, c3 = st.columns(3)
        c1.metric("行数", f"{rows:,}")
        c2.metric("列数", cols)
        c3.metric("内存", f"{df.memory_usage(deep=True).sum() / 1024:.1f} KB")

        with st.expander("📋 字段类型预览"):
            type_summary = (
                df.dtypes.rename("类型")
                .to_frame()
                .reset_index()
                .rename(columns={"index": "字段名"})
            )
            st.dataframe(type_summary, use_container_width=True, hide_index=True)

        with st.expander("👁 数据预览（前5行）"):
            st.dataframe(df.head(5), use_container_width=True, hide_index=True)

        return True

    except Exception as e:
        st.warning(f"无法预览数据: {e}")
        return False


def render_upload_tab(
    demo_path: str | None,
    demo_name: str | None,
    project_name: str | None,
    pm,  # ProjectManager
) -> str | None:
    """渲染「上传」Tab：演示数据 / 文件上传 / 项目已有。

    Args:
        demo_path: 演示数据路径（来自 session_state._demo_file）
        demo_name: 演示数据名称（来自 session_state._demo_name）
        project_name: 当前选中的项目名（来自 session_state.current_project）

    Returns:
        选中的数据文件路径，或 None。
    """
    data_path: str | None = None

    if demo_path:
        st.success(f"🎯 演示数据: {demo_name or Path(demo_path).name}")
        render_data_preview(demo_path)
        return demo_path

    # 文件上传
    uploaded = st.file_uploader(
        "上传数据文件",
        type=["csv", "xlsx", ".xls", "json", "parquet"],
        label_visibility="collapsed",
    )
    if uploaded:
        data_path = save_uploaded_file(uploaded)
        st.session_state._temp_uploaded_path = data_path
        st.session_state.uploaded_name = uploaded.name
        st.success(f"✅ 已加载: {uploaded.name}")
        render_data_preview(data_path)

    # 项目已有文件
    if project_name:
        proj_info = pm.info(project_name)
        if proj_info and proj_info.data_files:
            file_options = {
                f.name: str(proj_info.project_dir / f.path)
                for f in proj_info.data_files
            }
            selected_file = st.selectbox(
                f"📄 {project_name} 的数据文件",
                options=list(file_options.keys()),
            )
            data_path = file_options[selected_file]
            render_data_preview(data_path)
        else:
            st.warning(f"「{project_name}」暂无数据文件，请先上传")

    return data_path
