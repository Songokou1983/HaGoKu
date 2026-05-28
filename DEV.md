# HaGoKu Studio — 开发快速上手

> 详细设计文档见 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)。
> 排错指南见 [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)。
> 项目规范见 [PROJECT.md](PROJECT.md)。

## 环境搭建

```bash
git clone <repo-url> && cd <repo-root>

# 虚拟环境
python3 -m venv .venv && source .venv/bin/activate

# 安装
pip install -e ".[dev]"

# 配置 LLM（唯一生效路径：~/.hagoku/.env）
mkdir -p ~/.hagoku && cp .env.example ~/.hagoku/.env
# 编辑 ~/.hagoku/.env 填入 API 地址和密钥

# 验证
pytest tests/ -q
```

> **前置条件**: Python 3.10+

## 日常命令

> 完整测试命令和调试指南 → [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md#测试与质量)

```bash
# 代码质量
ruff check hagoku/                 # lint
mypy hagoku/                       # 类型检查

# ⚠️ 铁律 3：每次代码改动后必须跑过这三组，任一变红 = 改坏了
.venv/bin/python -m pytest tests/test_doctrine_compliance.py -q      # 零硬编码守门
.venv/bin/python -m pytest tests/test_product/test_information_arrival.py -q  # 信息抵达契约
.venv/bin/python -m pytest --tb=short -q                             # 全套回归

# 启动后端 API（FastAPI + WebSocket）
hagoku-api   # http://localhost:8000

# 启动前端开发服务器（React + Vite；仅本地需要时）
cd hagoku_web && npm run dev   # 终端会打印实际地址，常见为 http://localhost:5173
```

## 本地 UI 快照（`UI_CHANGELOG_backup_*`）

改 UI / 编排前若用 `cp … UI_CHANGELOG_backup_时间戳_原文件名` 留底，这些文件已被 **`.gitignore`** 忽略，**不要** `git add`。正式历史以 **Git 提交**为准。

```bash
# 仅列出（默认 dry-run）
python3 scripts/clean_ui_changelog_backups.py

# 只列出「超过 30 天未修改」的快照（仍不删除）
python3 scripts/clean_ui_changelog_backups.py --older-than 30

# 删除上面筛出的文件（先 dry-run 再执行）
python3 scripts/clean_ui_changelog_backups.py --older-than 30 --apply
```

脚本会跳过 `.git`、`.venv`、`node_modules` 等目录；删除前务必确认列表无误。

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `HAGOKYU_LLM_BASE_URL` | LLM API 地址（OpenAI 兼容；勿与 `hagoku-api` 端口 8000 混淆） | `http://localhost:8080/v1` |
| `HAGOKYU_LLM_API_KEY` | LLM API 密钥 | — |
| `HAGOKYU_LLM_MODEL` | 模型名称（默认，所有 Agent 共用） | `Qwen3.6-35B-A3B` |
| `HAGOKYU_LLM_MODEL_DEEP` | 深度推理模型（Analyst、仲裁器） | 同 `HAGOKYU_LLM_MODEL` |
| `HAGOKYU_LLM_MODEL_QUICK` | 快速模型（Scout、Reporter、反思） | 同 `HAGOKYU_LLM_MODEL` |
| `HAGOKYU_WORK_DIR` | 工作目录 | `~/.hagoku` |
| `HAGOKYU_PROJECT_DIR` | 项目根目录（可选，覆盖默认 `~/.hagoku/projects`）；改后重启 `hagoku-api`；不设时报告用浏览器另存为即可带走 | — |
| `HAGOKYU_EMBEDDING_BASE_URL` | Embedding API 地址 | `https://api.openai-proxy.org/v1` |
| `HAGOKYU_EMBEDDING_API_KEY` | Embedding API 密钥 | — |
| `HAGOKYU_EMBEDDING_MODEL` | Embedding 模型 | `text-embedding-3-small` |
| `HAGOKU_API_RELOAD` | `python -m hagoku.api.server` 是否启用 uvicorn **热重载**（`yes`/`1`/`true`）；默认关闭，避免监视子进程带来的偶发僵死 | 关闭 |
| `HAGOKU_WS_SEND_TIMEOUT` | WebSocket 向单个客户端 `send_json` 的超时秒数（防止慢连接拖死整条 HTTP 事件循环） | `5` |

### LLM 前置健康检查

pipeline 启动前执行 `health.check_llm_health()`（`hagoku/tools/health.py`），5 项检查：

| # | 检查项 | 失败级别 |
|---|--------|---------|
| 1 | HTTP 可达性 (`GET /models`) | **阻塞** |
| 2 | 模型存在 (`model`/`model_quick`/`model_deep` 在列表中) | **阻塞** |
| 3 | Chat completion 可用性 (发 `"ping"` 验证返回) | **阻塞** |
| 4 | Token 速率 (< 5 tok/s → 警告) | 警告 |
| 5 | JSON mode 可用性 | 警告 |

LLM 不可用 → pipeline 不启动，前端显示明确错误。不存在硬编码兜底。

## 架构净化（P0，2026-05-20 完成）

代码层角色限定为：**serialize → validate → transport**。所有语义判断由 LLM 完成。

| 组件 | 旧行为（已移除） | 新行为 |
|------|-----------------|--------|
| `query_parser.py` | 关键词硬匹配（`"分析"→descriptive` 等） | LLM structured output |
| `scout/agent.py` | `maxv > q75v * 10` 硬编码分布阈值 | LLM shape analysis |
| `orchestrator.py` | `_parse_llm_field_desc_line()` 正则解析 | 已删除 |
| `scout/agent.py` | `_format_sample_preview()` 截断格式化 | Scout 只传原始值 |
| `orchestrator.py` | Plan 构建 `match action_type` 映射表 | `_call_llm_for_plan()` |
| `orchestrator.py` | `llm_lines` 硬编码阶段消息 | `_generate_phase_message()` |

> 完整审查 → [docs/AGENT_HARDCODED_REVIEW.md](docs/AGENT_HARDCODED_REVIEW.md)。删除的常量在 `hagoku/agents/constants.py`。

## 提交规范

> 完整规范 → [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md#不要做的清单)

## 文件索引

| 文档 | 用途 | 受众 |
|------|------|------|
| [PROJECT.md](PROJECT.md) | 项目灵魂、架构原则、唯一真相源 | 所有人 |
| [README.md](README.md) | 用户手册（安装、命令、快速开始） | 用户 |
| [CLAUDE.md](CLAUDE.md) | AI 编码助手上下文 | Claude Code |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | 详细设计手册（架构/看板/向量/审查） | 开发者 |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | 常见问题排查 | 开发者 |
| [DEVELOPMENT_PROMPT.md](DEVELOPMENT_PROMPT.md) | 单轮任务传递模板（转发前填写；规范以 PROJECT.md 为准） | 派活人、协作者 |
| **DEV.md**（本文件） | 快速上手 | 新贡献者 |
| `scripts/clean_ui_changelog_backups.py` | 列出 / 清理 `UI_CHANGELOG_backup_*` 本地快照 | 维护本地仓库时 |

---

> **禁止事项速查**：不动 `~/.llama-proxy/`、不用 `pm2` 操作 Hermes 服务、UI 代码用绝对导入 `from hagoku.*`、不在 commit message 写 "various fixes"。完整清单见 [docs/DEVELOPMENT.md §不要做的清单](docs/DEVELOPMENT.md#不要做的清单)。