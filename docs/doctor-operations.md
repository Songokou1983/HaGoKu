# HaGoKu Doctor 操作手册

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

Doctor 在对话中自动获得以下信息：
- 系统健康状态（9 项检查）
- 最近 30 行日志（自动过滤错误行）
- 当前 LLM 配置（base_url + model）
- 激活的提示词预设
- 最新审计报告内容

## 诊断流程

1. 用户描述症状
2. 查看自动注入的日志和健康状态
3. 匹配本文档中的操作
4. 向用户简短说明诊断结论
5. **直接执行修复**——在回复末尾加上 `[fix:操作名 {...}]`，系统自动执行。需要参数时用 JSON: `[fix:create_tool_stub {"name":"xxx","implementation":"def ..."}]`
6. 告知用户验证方法

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
