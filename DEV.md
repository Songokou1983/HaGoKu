# HaGoKu — 开发快速上手

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

```bash
# 测试
pytest tests/ -q                    # 全部测试
pytest tests/test_agents/ -q       # 单模块

# 代码质量
ruff check hagoku/                 # lint
mypy hagoku/                       # 类型检查

# 直接调试后端（不经过 UI）
.venv/bin/python -c "
from hagoku.config import HaGoKuConfig
from hagoku.manager.orchestrator import Orchestrator
config = HaGoKuConfig.load()
orch = Orchestrator(config)
result = orch.run('data.csv', '分析问题', phase='scout_first')
print(result['status'])
"

# 启动后端 API（FastAPI + WebSocket）
hagoku-api   # http://localhost:8000

# 启动前端开发服务器（React + Vite）
cd hagoku_web && npm run dev   # http://localhost:5173
```

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `HAGOKYU_LLM_BASE_URL` | LLM API 地址（OpenAI 兼容；勿与 `hagoku-api` 端口 8000 混淆） | `http://localhost:8080/v1` |
| `HAGOKYU_LLM_API_KEY` | LLM API 密钥 | — |
| `HAGOKYU_LLM_MODEL` | 模型名称（默认，所有 Agent 共用） | `Qwen3.6-35B-A3B` |
| `HAGOKYU_LLM_MODEL_DEEP` | 深度推理模型（Analyst、仲裁器） | 同 `HAGOKYU_LLM_MODEL` |
| `HAGOKYU_LLM_MODEL_QUICK` | 快速模型（Scout、Reporter、反思） | 同 `HAGOKYU_LLM_MODEL` |
| `HAGOKYU_WORK_DIR` | 工作目录 | `~/.hagoku` |
| `HAGOKYU_PROJECT_DIR` | 项目根目录（可选，覆盖默认 `~/ .hagoku/projects`） | — |
| `HAGOKYU_EMBEDDING_BASE_URL` | Embedding API 地址 | `https://api.openai-proxy.org/v1` |
| `HAGOKYU_EMBEDDING_API_KEY` | Embedding API 密钥 | — |
| `HAGOKYU_EMBEDDING_MODEL` | Embedding 模型 | `text-embedding-3-small` |

## 提交规范

```bash
git add <files>
git commit -m "$(cat <<'EOF'
fix: <具体描述>

<改动1>
<改动2>

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

每次提交只做一件事，commit message 要写清楚具体改了什么。

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

---

> **禁止事项速查**：不动 `~/.llama-proxy/`、不用 `pm2` 操作 Hermes 服务、UI 代码用绝对导入 `from hagoku.*`、不在 commit message 写 "various fixes"。完整清单见 [docs/DEVELOPMENT.md §不要做的清单](docs/DEVELOPMENT.md#不要做的清单)。