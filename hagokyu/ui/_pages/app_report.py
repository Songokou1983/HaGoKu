"""HaGoKu Streamlit UI — 报告查看 + refinement 对话"""

from __future__ import annotations

import re
import tempfile
import threading
import time
from pathlib import Path

import streamlit as st

from hagokyu.ui.components.event_log import render_event_log
from hagokyu.ui.components.report_viewer import render_html_report, results_summary
from hagokyu.config import HaGoKuConfig
from hagokyu.manager.orchestrator import Orchestrator
from hagokyu.manager.refinement import parse_refinement
from hagokyu.observability.events import Event
from hagokyu.storage.project_manager import ProjectManager


def _refine_report_thread(
    data_path: str,
    query: str,
    project_name: str | None,
    refinement_prompt: str,
    config: HaGoKuConfig,
    result_holder: list,
    error_holder: list,
    events_holder: list,
) -> None:
    """后台线程：运行 refinement"""
    try:
        orch = Orchestrator(config)

        def on_event(event: Event) -> None:
            events_holder.append(event)

        orch.event_bus.subscribe(on_event)
        from hagokyu.observability.display import TerminalDisplay
        orch.event_bus.unsubscribe(orch.display)

        # 构建 refinement query
        intent = parse_refinement(refinement_prompt, {})

        if intent.refine_type == "exit":
            return

        # 描述调整
        descriptions = {
            "filter": f"只看「{intent.filter_value or intent.filter_column}」的数据",
            "exclude": f"排除「{intent.filter_value or intent.filter_column}」的数据",
            "switch_target": f"换成「{intent.new_target}」作为分析指标",
            "simplify": "简化报告",
            "more_detail": "详细展开报告",
            "explain": "解释结论",
        }
        adjustment = descriptions.get(intent.refine_type, refinement_prompt)
        new_query = f"{query} | 调整: {adjustment}"

        result = orch.run(
            data_path=data_path,
            query=new_query,
            project_name=project_name,
            user_mode="standard",
            resume=True,
        )
        result_holder.append(result)

    except Exception as e:
        error_holder.append(str(e))


def render() -> None:
    pm: ProjectManager = st.session_state.project_manager
    config = HaGoKuConfig.load()

    st.title("📋 分析报告")

    # ── 报告选择 ────────────────────────────────────────────
    col_report, col_chat = st.columns([2, 1])

    with col_report:
        st.markdown("### 📄 报告内容")

        # 获取可用的报告
        current_project = st.session_state.get("current_project")
        available_reports: list[tuple[str, str]] = []

        # 从 session 拿最新报告
        if st.session_state.get("last_report_path"):
            p = st.session_state.last_report_path
            if Path(p).exists():
                available_reports.append(("最新报告", p))

        # 从项目拿历史报告（支持新旧两种目录结构）
        if current_project:
            proj_dir = pm.get_project_dir(current_project)
            if proj_dir:
                runs_dir = proj_dir / "runs"
                if runs_dir.exists():
                    for run_dir in sorted(runs_dir.iterdir(), reverse=True)[:10]:
                        report_file = run_dir / "output" / "report.html"
                        if report_file.exists():
                            available_reports.append((run_dir.name, str(report_file)))

        if available_reports:
            report_options = [r[0] for r in available_reports]
            selected = st.selectbox("选择报告", options=report_options)
            report_path = dict(available_reports)[selected]

            # 渲染报告
            render_html_report(report_path, height=700)

            # 下载按钮
            with open(report_path, "r", encoding="utf-8") as f:
                st.download_button(
                    "💾 下载报告 (HTML)",
                    data=f.read(),
                    file_name=Path(report_path).name,
                    mime="text/html",
                )
        else:
            st.info("""
            暂无报告。

            请先在「📊 分析」页面运行一次分析，报告会出现在这里。
            """)

    # ── Refinement 对话 ────────────────────────────────────
    with col_chat:
        st.markdown("### 💬 调整报告")

        st.caption("支持以下调整（无需重新描述整个问题）：")
        st.markdown("""
        • **缩小范围**：只看某地区/渠道的数据
        • **换指标**：换成另一个指标重新分析
        • **简化**：生成更简洁的报告
        • **详细**：生成更详细的报告
        • **解释**：解释某个结论背后的原因
        """)

        # 初始化对话历史
        if "refinement_messages" not in st.session_state:
            st.session_state.refinement_messages = []

        # 显示对话历史
        for msg in st.session_state.refinement_messages:
            if msg["role"] == "user":
                st.chat_message("user").write(msg["content"])
            else:
                st.chat_message("assistant").write(msg["content"])

        # 输入
        if prompt := st.chat_input("调整报告..."):
            # 添加用户消息
            st.session_state.refinement_messages.append({"role": "user", "content": prompt})
            st.chat_message("user").write(prompt)

            # 解析意图
            intent = parse_refinement(prompt, {})

            if intent.refine_type in ("blocked", "unknown"):
                guidance = intent.guidance or "无法理解这个调整指令"
                st.chat_message("assistant").warning(guidance)
                st.session_state.refinement_messages.append({"role": "assistant", "content": guidance})
                return

            if intent.refine_type == "exit":
                st.chat_message("assistant").info("好的，报告保持不变。")
                st.session_state.refinement_messages.append({"role": "assistant", "content": "好的，报告保持不变。"})
                return

            # 解析成功，开始调整
            with st.chat_message("assistant"):
                with st.spinner("正在调整报告..."):
                    # 获取数据路径
                    data_path = None
                    if st.session_state.get("last_report_path"):
                        data_path = st.session_state.get("last_data_path", "")

                    if not data_path and current_project:
                        proj_info = pm.info(current_project)
                        if proj_info and proj_info.data_files:
                            latest = proj_info.latest_input
                            if latest:
                                data_path = str(latest)

                    if not data_path:
                        st.warning("无法找到对应的数据文件，请重新在分析页面运行")
                        return

                    result_holder = []
                    error_holder = []
                    events_holder = []

                    # 后台运行
                    def run():
                        _refine_report_thread(
                            data_path,
                            st.session_state.get("last_query", prompt),
                            current_project,
                            prompt,
                            config,
                            result_holder,
                            error_holder,
                            events_holder,
                        )

                    thread = threading.Thread(target=run, daemon=True)
                    thread.start()

                    # 显示进度
                    placeholder = st.empty()
                    waited = 0
                    while thread.is_alive():
                        waited += 2
                        placeholder.text(f"重新分析中... ({waited}s)")
                        time.sleep(2)

                    placeholder.empty()

                    if error_holder:
                        st.error(f"调整失败: {error_holder[0]}")
                        st.session_state.refinement_messages.append(
                            {"role": "assistant", "content": f"❌ 调整失败: {error_holder[0]}"}
                        )
                    elif result_holder:
                        result = result_holder[0]
                        if result.get("status") == "completed":
                            st.success("✅ 报告已更新！")
                            st.session_state.last_report_path = result["output_path"]
                            st.session_state.analysis_events = events_holder.copy()
                            st.session_state.refinement_messages.append(
                                {"role": "assistant", "content": f"✅ 报告已更新: {result['output_path']}"}
                            )
                            if st.button("🔄 查看新报告"):
                                st.rerun()
                        else:
                            st.error("调整未能完成")
                            st.session_state.refinement_messages.append(
                                {"role": "assistant", "content": "❌ 调整未能完成"}
                            )
                    else:
                        st.warning("调整超时，请重试")
                        st.session_state.refinement_messages.append(
                            {"role": "assistant", "content": "⚠️ 调整超时，请重试"}
                        )

        # 清空对话
        if st.session_state.get("refinement_messages"):
            if st.button("🗑️ 清空对话历史"):
                st.session_state.refinement_messages = []
                st.rerun()

    # ── 分析结果摘要 ────────────────────────────────────────
    st.divider()
    st.markdown("### 📊 分析结果摘要")

    if st.session_state.get("analysis_result"):
        result = st.session_state.analysis_result
        report_path = st.session_state.get("last_report_path")
        if report_path and Path(report_path).exists():
            st.success(f"📄 报告路径: `{report_path}`")
    else:
        st.info("暂无分析结果摘要（请先运行分析）")
