# 命令系统 — 历史设计提案（未实现）

> **状态（2026-08-18 核对）**：本文档描述的「斜杠命令系统」（`CommandsPanel.tsx` + `hagoku/manager/command_parser.py` + `_pause_and_wait` + `_detect_user_intent_via_llm`）**当前代码中不存在**。
>
> 这是一份 2026-07-29 的设计提案，曾考虑实现但未落地。当前 HaGoKu 通过 CLI（`hagoku` / `hagoku-api`）和 Web UI（`hagoku_web/`）暴露功能，无斜杠命令面板。

---

## 背景（保留作为历史）

设计意图：通过 `/` 前缀触发命令（如 `/goal`、`/rename`、`/use`），让用户在分析过程中能快速切换目标、重命名项目等，而不离开对话。

## 提案中的关键模块（均未实现）

| 模块 | 提案位置 | 现实 |
|------|---------|------|
| 前端面板 `CommandsPanel.tsx`（457 行） | `hagoku_web/src/panels/CommandsPanel.tsx` | 不存在。`hagoku_web/src/panels/` 下只有 AnalyzePanel/DoctorPanel/EventPanel/KnowledgePanel/ProjectPanel/PromptLabPanel/ReportPanel/SettingsPanel |
| 后端解析器 `command_parser.py` | `hagoku/manager/command_parser.py` | 不存在。`hagoku/manager/` 下只有 `__init__.py`/`llm_dispatch/`/`orchestrator.py`/`payloads/`/`query_parser.py`/`refinement.py` |
| 暂停等待 `_pause_and_wait` | 集成到 WS handler 入口 | 不存在 |
| LLM 意图检测 `_detect_user_intent_via_llm` | 后端辅助函数 | 不存在 |

## 当前可用的命令替代

| 用户意图 | 当前替代路径 |
|---|---|
| 创建项目 | `hagoku project create <name>` CLI 命令 |
| 添加数据 | `hagoku project add <name> <file>` 或 Web UI ProjectPanel |
| 开始分析 | `hagoku run <data> -q "<query>"` 或 Web UI AnalyzePanel |
| 查看历史 | `hagoku history <project>` 或 Web UI ReportPanel |
| 切换预设 | Web UI PromptLabPanel（写到 `~/.hagoku/active_preset`）|
| 配置 LLM | `hagoku config` 或 Web UI SettingsPanel |
| 健康检查 | `hagoku doctor` |

---

## 为什么要标为「未实现」

- 本文档最初基于的假设（4 个 Agent + route_to + 阶段切换工具）已被 Phase D 重构推翻
- 单 `DataAnalystAgent` 自驱动后，斜杠命令的语义边界难以设计（命令触发的「阶段切换」已不存在）
- 投入产出比低：CLI + Web UI 已覆盖所有用户场景

## 若要重新启用

需要先回答三个设计问题：

1. 斜杠命令与 LLM 自然语言输入如何共存？两者都可能被理解为「重命名项目」等意图
2. 命令面板如何与现有 8 个 Web Panel 集成？占哪个位置、什么时机出现
3. 后端是用单独的命令解析器（破坏当前 WS 消息流），还是把命令解析放进 LLM 调用前的 prompt 里（增加 token 成本）

在这些问题有答案之前，**保持现状（CLI + Web UI）**。

---

**变更记录**

| 日期 | 内容 |
|------|------|
| 2026-07-29 | 初稿：设计斜杠命令面板 + 后端解析器 |
| 2026-08-18 | 核对代码，未实现。重写本文档标记状态 |