# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Structure

This is a home directory containing multiple projects:

- **hermes-agent-self-evolution/** — Primary project: evolutionary self-improvement for Hermes Agent using DSPy + GEPA
- **feishu-bot/** — Feishu (Lark) messaging bot (Node.js/Express)
- **.hermes/** — Symlinked to Windows path containing hermes-agent repo

## hermes-agent-self-evolution

Evolutionary optimization pipeline that evolves Hermes Agent's skills, prompts, tool descriptions, and code using DSPy + GEPA (Genetic-Pareto Prompt Evolution).

### Commands

```bash
# Install
cd hermes-agent-self-evolution
pip install -e ".[dev]"

# Run tests
pytest tests/ -q

# Evolve a skill
python -m evolution.skills.evolve_skill --skill github-code-review --iterations 10 --eval-source synthetic

# Dry run (validate setup)
python -m evolution.skills.evolve_skill --skill github-code-review --dry-run
```

### Architecture

```
evolution/
├── core/           # Shared infrastructure
│   ├── config.py           # EvolutionConfig, HERMES_AGENT_REPO env var
│   ├── dataset_builder.py  # SyntheticDatasetBuilder, EvalDataset (train/val/holdout splits)
│   ├── fitness.py          # skill_fitness_metric, LLMJudge (LLM-as-judge scoring)
│   └── constraints.py      # ConstraintValidator (size limits, caching compat)
├── skills/         # Phase 1: Skill evolution
│   ├── evolve_skill.py     # Main CLI entry point
│   └── skill_module.py     # SkillModule (wraps SKILL.md as DSPy module)
├── tools/          # Phase 2: Tool description evolution (planned)
├── prompts/        # Phase 3: System prompt evolution (planned)
├── code/           # Phase 4: Code evolution via Darwinian Evolver (planned)
└── monitor/        # Phase 5: Continuous loop (planned)
```

### Key Concepts

- **DSPy + GEPA**: Reflective prompt evolution that reads execution traces to understand failures
- **EvalDataset**: Train/val/holdout splits for evaluating evolved variants
- **SkillModule**: Wraps SKILL.md as a DSPy module for optimization
- **ConstraintValidator**: Enforces size limits (skills ≤15KB), caching compatibility, semantic preservation
- **Fitness metric**: LLM-as-judge scoring on rubrics, not exact text matching

### Configuration

Set `HERMES_AGENT_REPO` env var to point at the hermes-agent repository:
```bash
export HERMES_AGENT_REPO=~/.hermes/hermes-agent
```

## feishu-bot

Simple Feishu (Lark) messaging bot using Express.js. Listens on `/webhook` endpoint.

### Commands

```bash
cd feishu-bot
npm install
node server.js
```

### Notes

- Webhook URL: `http://localhost:3000/webhook`
- Supports simple commands: hi, hello, 你好, 时间, 帮助, 状态

## hagokyu/

Multi-agent data analysis platform. Fully documented in `hagokyu-project.md` (记忆目录).

```bash
cd hagokyu
hagokyu doctor          # LLM 健康检查
hagokyu run data.csv -q "哪个渠道ROI最高"   # CLI 分析
hagokyu-ui              # 启动 Web UI（Streamlit，端口 8501）
```

- **架构**: Manager → Scout → Cleaner → Analyst → Reporter
- **LLM**: MiniMax 云端（`~/.hagokyu/.env` 配置），**不要动 Hermes 的本地 35B**
- **代码量**: 18,607 行 Python，223 pytest 100% 通过
- **UI**: Streamlit，terminal/sci-fi 深色主题（JetBrains Mono + Inter 字体）
- **包布局**: flat（`hagokyu/` 在项目根，不用 `src/hagokyu/`）
- **导入注意**: UI 包内禁止相对导入，全用 `from hagokyu.*` 绝对导入

## HaGoKu UI 设计原则（每一条改动都必须遵守）

1. **考虑用户体验**：每次改动想清楚用户看到什么、怎么用
2. **差异化**：和市面上产品有明显区别，不是功能堆砌
3. **互动性**：Agent 主动引导用户，不是等着用户输入
4. **不要出现重复功能**：一个功能只在一个地方
5. **不要重复犯错**：同一错误不犯第二次
6. **理解确认清楚需求再改动**：不确定就问用户，不要乱猜
7. **表格规则（HTML table via st.markdown() 实现时）**：
   - 表头 **必须居中**（`text-align:center`）— 这是死规定，**绝对不允许违反**
   - 数据列内容 **不要居中**，保持默认左对齐
   - 绝不添加未经用户明确要求的功能（如"文件数列"、"总项目数"等汇总栏）
8. **新建项目表单**：始终固定在页面底部，不可在顶部
9. **操作按钮**：图标 + 文字双重要素，缺一不可
10. **最小改动原则**：每次只改用户要求的那一个地方，不做额外的改动，不改变未要求的元素
11. **每次改动前必须备份**：使用 `cp file UI_CHANGELOG_backup_YYYYMMDDHHMMSS.py` 备份，每一步改动都要记录到 UI_CHANGELOG.md

## 全局工作原则（所有项目适用）

### 不要让我重复说同一件事
用户说过的问题 → 立即记录到项目文档 + 代码注释。修完 bug → 写测试防止 regression。每次开始工作前先读项目文档再动手。

### 不要重新发明轮子
已有配置/服务 → 直接用，不要新建。
- **Hermes**：运行着本地 35B 模型，`~/.llama-proxy/` 配置（**不要动**）
- PM2 管理服务 → 不要 stop/restart 不认识的服务
- 如果需要调用已有 LLM → 找它的配置，不要自己新建

### 开发流程
1. 先读项目文档（`docs/DEVELOPMENT.md` 或 `*.md`）
2. 边做边记录，不等人提醒
3. 学到新东西 → 写进项目文档，不是记在脑子里
4. 提交前确认测试通过

### 测试方法
- 优先用 Python 直接测后端逻辑（不依赖 UI 自动化）
- UI 测试 → 手动在浏览器测
- 不要花大量时间搞 UI 自动化测试框架

### 提交规范
- commit message 写清楚改了什么，不要写"fix: update"或"various fixes"
- 每次提交只做一件事

---

## Karpathy 编码原则（自动应用）

### 1. Think Before Coding
**不猜、不藏疑点，先说假设。**
- 不确定 → 先问，不要猜
- 有多种解释 → 说出来，不要自己选
- 有更简单方案 → 提出来，不要闷头实现
- 不清楚 → 停下来，说清楚，问用户

### 2. Simplicity First
**最少代码解决问题，不 speculative。**
- 不做没要求的功能
- 单次使用的代码不抽象
- 不做没被要求的"灵活性"
- 200行能解决就不要写2000行

### 3. Surgical Changes
**只改需要改的，不顺手优化。**
- 不改旁边没问题的代码
- 不顺手格式化
- 不删除没被要求删除的代码
- 只清理自己改动产生的孤儿代码

### 4. Goal-Driven Execution
**给可验证的成功标准。**
- "修bug" → 先写测试复现，再修
- "加功能" → 先说清楚怎么算完成
- 多步任务 → 先列计划，每步有验证点
