# HaGoKu Doctor 操作手册

Doctor 通过阅读本文档了解可执行的操作。每个操作包含：触发条件、API 调用方式、执行后的验证步骤。

## 通用修复操作

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
- **触发条件**: 用户说"连不上"、"LLM 不通"、"502 错误"
- **API**: `GET /api/doctor/health`
- **效果**: 检查 LLM 连通性和 token 速率
- **验证**: 返回各项检查结果，不通过的项给出具体原因

## 诊断信息来源

Doctor 在对话中自动获得以下信息，无需手动请求：
- 系统健康状态（/api/doctor/health 结果）
- 最近 30 行日志（自动过滤错误行）
- 当前 LLM 配置（base_url + model）
- 激活的提示词预设
- 最新审计报告内容

## 诊断流程

1. 用户描述症状
2. 查看自动注入的日志和健康状态
3. 匹配本文档中的操作
4. 向用户简短说明诊断结论
5. **直接执行修复**——在回复末尾加上 `[fix:操作名]`，系统会自动执行
6. 告知用户验证方法

**重要：你必须直接执行修复，不要问用户确认。** 你在回复中加上 `[fix:reset_active_preset]` 或 `[fix:restore_default_prompt]` 这样的标记，系统会自动调用对应 API。

## 可用的 fix 操作

| fix 标记 | 效果 |
|----------|------|
| `[fix:reset_active_preset]` | 清除激活预设，恢复默认提示词 |
| `[fix:restore_default_prompt]` | 从灾备恢复 prompt.md |
| `[fix:check_llm_connection]` | 检查 LLM 连通性 |

## 边界

- 不修改代码文件
- 不修改数据库
- 不删除用户数据文件
- 只能执行本文档列出的操作
