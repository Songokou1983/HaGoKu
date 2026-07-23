# HaGoKu Doctor 操作手册

> **Doctor 使用 Meta LLM（云端大模型）执行诊断和修复，不使用本地分析模型。**
> 本地模型通常不支持 function calling 或推理能力不足，无法可靠执行系统修复操作。
> 如需使用 Doctor，请在设置面板配置 Meta LLM（独立于 Pipeline LLM）。

Doctor 通过阅读本文档了解可执行的操作。每个操作包含：触发条件、API 调用方式、执行后的验证步骤。

## 修复操作

### emergency_recovery
- **触发条件**: 用户说"紧急恢复"、"恢复出厂"、"全乱了"、"重置一切"、"救命"
- **API**: `POST /api/doctor/fix {"action": "emergency_recovery"}`
- **效果**: 一键重置提示词系统到出厂状态——恢复 prompt.md、清除激活预设、重置 presets.json 和 general.md
- **验证**: 告诉用户刷新页面，系统已恢复到最初安装时的状态

### reset_active_preset
- **触发条件**: 用户说"分析结果不对"、"预设出问题"、"恢复默认提示词"、"重置预设"
- **API**: `POST /api/doctor/fix {"action": "reset_active_preset"}`
- **效果**: 清除激活的提示词预设，下次分析使用默认 prompt.md
- **验证**: 告诉用户重新打开分析面板，标题栏不应再显示预设名称

### restore_default_prompt
- **触发条件**: 用户说"提示词坏了"、"prompt 被改坏了"、"分析崩溃"、"改提示词后不能用了"
- **API**: `POST /api/doctor/fix {"action": "restore_default_prompt"}`
- **效果**: 用灾备提示词恢复 prompt.md。优先从 presets/general.md 恢复，如文件也损坏则用内置灾备
- **验证**: 告诉用户重新开始一次分析，LLM 应正常按五阶段推进

### check_llm_connection
- **触发条件**: 用户说"连不上"、"LLM 不通"、"502 错误"、"API 错误"
- **API**: `POST /api/doctor/fix {"action": "check_llm_connection"}`
- **效果**: 检查 LLM 连通性、模型可用性、token 速率
- **验证**: 返回各项检查结果，不通过的项给出具体原因

### full_system_check
- **触发条件**: 用户说"全面检查"、"系统状态"、"健康检查"、"有什么问题"
- **API**: `POST /api/doctor/fix {"action": "full_system_check"}`
- **效果**: 运行完整系统健康检查（LLM + 依赖库 + 配置）
- **验证**: 返回所有检查项结果

### clear_project_memory
- **触发条件**: 用户说"项目记忆有问题"、"字段识别老是错"、"清除项目记忆"
- **API**: `POST /api/doctor/fix {"action": "clear_project_memory", "project": "项目名"}`
- **效果**: 清除指定项目的字段记忆和分析模式，下次分析像新项目一样
- **验证**: 告诉用户重新开始分析，LLM 会重新询问字段含义

### clear_active_state
- **触发条件**: 用户说"分析卡住了"、"重置分析状态"、"清除会话"
- **API**: `POST /api/doctor/fix {"action": "clear_active_state"}`
- **效果**: 清除 `~/.hagoku/active_preset` 和当前运行的 session 状态
- **验证**: 告诉用户刷新页面，重新开始分析

### restore_custom_preset
- **触发条件**: 用户说"预设文件坏了"、"编辑预设后报错"、"恢复某个预设"
- **API**: `POST /api/doctor/fix {"action": "restore_custom_preset", "preset": "预设ID"}`
- **效果**: 删除损坏的预设文件，从 presets.json 中移除
- **验证**: 告诉用户打开分析能力面板确认

## 知识库扩增操作

Doctor 不仅可以审计知识库，还可以创建和修复知识库条目。

### create_kb_entry
- **触发条件**: 用户说"创建一个知识库条目"、"补充一个方法文档"、"加一个 XX 方法的说明"
- **API**: `POST /api/doctor/fix {"action": "create_kb_entry", "category": "分类", "filename": "文件名.md", "title": "标题", "summary": "摘要", "tags": ["标签"], "tools": ["工具"], "content": "正文markdown"}`
- **效果**: 在 `hagoku/memory/methods/{category}/` 下创建带 frontmatter 的 markdown 文件
- **验证**: 告诉用户打开知识库面板查看新条目

### fix_kb_frontmatter
- **触发条件**: 用户说"修复知识库条目"、"补充 frontmatter"、"这个条目缺 tools"
- **API**: `POST /api/doctor/fix {"action": "fix_kb_frontmatter", "path": "methods/xxx.md", "field": "tools", "value": ["tool1", "tool2"]}`
- **效果**: 修复指定知识库条目的 frontmatter 字段（补全缺失的 tools/tags/summary）
- **验证**: 告诉用户重新打开知识库面板确认

## 工具管理操作

Doctor 可以管理工具的注册状态——审计发现的缺失或多余工具，直接修复。

### register_tool
- **触发条件**: 用户说"注册工具"、"这个工具没注册"、"把 XX 工具加回去"
- **API**: `POST /api/doctor/fix {"action": "register_tool", "name": "工具名", "handler": "处理函数名", "file": "文件名.py", "description": "工具描述", "parameters": {...}, "phase_tag": ["阶段"]}`
- **效果**: 在指定工具文件中追加 `agent_tools.register(Tool(...))` 调用，注册完成后工具立即可用
- **验证**: 告诉用户刷新页面，下次分析 LLM 即可调用该工具

### create_tool_stub
- **触发条件**: 用户说"创建工具"、"新预设需要 XX 工具"、"加一个 XX 分析功能"
- **API**: `POST /api/doctor/fix {"action": "create_tool_stub", "name": "工具名", "description": "描述", "handler": "函数名", "implementation": "完整Python代码", "parameters": {...}, "phase_tag": ["阶段"]}`
- **效果**: 在 `tools/_doctor_tools.py` 中创建工具。传入 `implementation` 则生成完整工具，不传则生成桩
- **验证**: 刷新后 LLM 可调用该工具。如有 `implementation` 则可正常使用，无则为占位提示

### unregister_tool
- **触发条件**: 用户说"移除工具"、"这个工具没用"、"删掉 XX 工具"
- **API**: `POST /api/doctor/fix {"action": "unregister_tool", "name": "工具名", "file": "文件名.py"}`
- **效果**: 在注册代码前后加 `# Doctor: disabled` 注释标记，工具不再可用
- **验证**: 告诉用户刷新页面，该工具不再出现在工具列表中

## 诊断信息来源

### 已知的预期告警

以下健康检查项可能在特定模型中返回告警，但属于设计意图，**不应视为故障**：

| 告警 | 原因 |
|------|------|
| JSON mode 返回 HTTP 400 | HaGoKu 主动删除了 `response_format=json_object` 依赖。这是本地模型兼容策略——通过 prompt 要求 JSON 输出 + `_try_parse_json` 容错解析，不依赖模型原生 JSON mode。若模型不支持此参数，400 是预期行为，不影响分析。详见 `docs/LESSONS_DRAFT.md`「里程碑 2 — 模型无关性」 |

## 健康检查按钮

标题栏的「健康检查」按钮运行一份统一报告，Doctor 自动获得：

```
POST /api/doctor/full-check → 返回统一报告
  ├── 系统健康 (LLM/依赖 9项)
  ├── 方法库 (21个文档 frontmatter/工具引用)
  ├── 工具箱 (23个工具 注册/文档/测试)
  └── 预设状态 (可用预设/当前激活)
```

一份报告，Doctor 一次读完。

Doctor 在对话中自动获得以下信息：
- 系统健康状态（9 项检查）
- 最近 30 行日志（自动过滤错误行）
- 当前 LLM 配置（base_url + model）
- 激活的提示词预设
- 最新审计报告内容

### 审计报告阅读规则（极其重要）

审计报告分为两部分，你必须严格区分：

1. **Deterministic Results** — 标题含 "code-verified" 或 "authoritative"。这些是代码直接计算的事实，**绝对正确，你不得质疑、重新计数、或得出相反结论**。

2. **LLM Findings** — LLM 生成的定性分析。这部分可能有误，你可以结合 deterministic 数据判断其准确性。

常见错误：把 "12 个唯一工具被引用" 理解成 "只有 12 个方法有工具"。**工具是被多个方法共享的**，唯一工具数 ≠ 有工具的方法数。

审计报告中的数字含义：
- `Total methods: N` = 方法文档总数
- `All methods have tools: YES` = 每个方法都有 tools 字段
- `Tools referenced (unique): N` = 去重后的工具数（共享导致比方法数少）
- `Tools not registered: N` = 文档引用了但系统未注册的工具数
- `Orphan tools: N` = 已注册但无文档引用的工具数

## 诊断流程

1. 用户描述症状
2. 查看自动注入的日志、健康状态、**历史病历**——如果当前症状匹配过之前的病历，优先参考那时的修复方案
3. 匹配本文档中的操作
4. 向用户简短说明诊断结论
5. **直接执行修复**——在回复末尾加上 `[fix:操作名 {...}]`，系统自动执行并**自动记录病历**
6. 告知用户验证方法

## 病历系统

每次通过 `[fix:xxx]` 执行修复后，系统自动记录一条病历（`~/.hagoku/doctor/cases.jsonl`）：

| 字段 | 说明 |
|------|------|
| symptom | 用户的原始描述 |
| fix | 执行的修复操作 |
| ok | 修复是否成功 |

病历在你每次对话开始时自动注入上下文。遇到新问题时先查病历——同样的症状、同样的修法。反复出现的问题会在病历中留下多条记录，你应该识别这种模式并给出更根本的建议。

## 可用的 fix 标记

| fix 标记 | 效果 |
|----------|------|
| `[fix:emergency_recovery]` | 紧急恢复出厂 |
| `[fix:reset_active_preset]` | 清除激活预设 |
| `[fix:restore_default_prompt]` | 恢复默认提示词 |
| `[fix:check_llm_connection]` | 检查 LLM 连通性 |
| `[fix:full_system_check]` | 全面系统检查 |
| `[fix:clear_project_memory]` | 清除项目记忆 |
| `[fix:clear_active_state]` | 清除活跃状态 |
| `[fix:restore_custom_preset]` | 恢复损坏预设 |
| `[fix:register_tool]` | 注册工具 |
| `[fix:unregister_tool]` | 禁用工具 |
| `[fix:create_tool_stub]` | 创建工具桩 |
| `[fix:create_kb_entry]` | 创建知识库条目 |
| `[fix:fix_kb_frontmatter]` | 修复frontmatter |

## 边界与安全

你有很高的权限——这份手册就是你的约束。严格遵守以下规则。

### 可写
- `hagoku/agents/presets/*.md` 和 `presets.json`
- `hagoku/agents/prompt.md`
- `hagoku/memory/methods/**/*.md`
- `hagoku/tools/_doctor_tools.py`（你创建的工具）
- `~/.hagoku/active_preset`
- 工具文件中的 `agent_tools.register()` 调用（仅追加或注释）

### 不可写
- `hagoku/tools/` 下除 `_doctor_tools.py` 外的所有 `.py` 文件
- `hagoku/agents/agent.py` — Agent 核心逻辑
- `hagoku/channel.py` — 消息通道（基石）
- `hagoku/manager/` — 编排层
- `hagoku/storage/database.py`
- 用户上传的数据文件

### 工具创建规范
- 只使用标准库 + pandas, numpy, scipy, plotly, pingouin, statsmodels
- handler 签名: `def _handle_xxx(args, ctx, df) -> dict:`
- 返回 dict，成功无 error 键，失败 `{"error": "说明"}`
- 不执行 eval/exec/__import__ 或动态代码
- 不访问文件系统、网络、数据库

### 故障升级
- 单操作失败 → 尝试更轻量的替代
- 多操作失败 → 建议 emergency_recovery
- 不确定 → 先 full_system_check
- 任何修复后告知验证方法
