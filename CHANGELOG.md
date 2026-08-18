# Changelog

所有版本变更记录在这里。格式基于 [Keep a Changelog](https://keepachangelog.com/)。

## [v2.3.1] - 2026-08-18

### ✨ Features
- 三个分析场景预设：通用商业 / 股票技术 / 电商运营
- 12 个工具全部就绪（数据探查 / 字段管理 / 统计与清洗 / 可视化·报告·记忆）
- 三层记忆系统：跨项目方法库 + 经验库 + 项目记忆
- 桌面客户端（Electron v0.9）
- Web UI（React 19 + Vite + TypeScript）

### 🏗️ Architecture
- 单 `DataAnalystAgent` 自驱动（`run_step` 用 `while tc_list` 续轮）
- `to_messages_for_llm()` 作为 LLM 消息构造唯一入口
- 事件驱动编排（Orchestrator + EventBus + WS Handler）
- 配置中性（任何 OpenAI 兼容端点，本地或云端）

### 🔒 Quality
- 445 测试 100% 通过（含铁律合规测试 + 契约测试 + 单元测试）
- self_check.sh 10/10 守门（语法、铁律、TS、堵路、消息去重、假 response、LLM 搬运等）
- commit-msg hook 强制要求诊断证据（dump/path/gap）

### 📚 Documentation
- README（突出单 Agent + 预设 + 12 工具的核心差异化）
- PROJECT.md（设计真相来源）
- docs/CHANNEL.md（通道反模式经验录）
- docs/TOOL_DESIGN.md（工具设计三问）
- docs/decisions/（5 个 ADR）
- 90+ 内部历史归档（audits / cases / lessons / plans / prompts / superpowers）

### 🔓 License
- MIT

### ⚠️ Breaking Changes（相对历史）
- 移除所有流程控制类工具（`ask_user` / `route_to` / `submit_findings` 等）
- `Orchestrator.run()` 不再接受 `phase` 参数
- 多 Agent（Scout/Cleaner/Analyst/Reporter）合并为单 `DataAnalystAgent`

---

## 历史版本

历史 commit 散落在 `git log` 中。早期版本未单独 tag，
是从 `master` 直接看 commit 历史的连续演进。

### 演进里程碑
- **v2.3.x**：单 Agent + 12 工具 + 通道架构（2026-06-11 Phase D 收敛）
- **v2.0.x**：4 Agent 架构（Scout/Cleaner/Analyst/Reporter）
- **v1.x**：早期原型

完整 commit 历史：<https://github.com/Songokou1983/HaGoKu/commits/master>

[Unreleased]: https://github.com/Songokou1983/HaGoKu/compare/v2.3.1...HEAD
[v2.3.1]: https://github.com/Songokou1983/HaGoKu/releases/tag/v2.3.1