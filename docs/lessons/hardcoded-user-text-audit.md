# 硬编码用户可见文本 — 审计

> 代码生成固定文案替代 LLM 应该动态生成的内容。只整理，不动代码。

## 🔴 高危：前端按钮直接作为 LLM 输入

| 文件:行 | 硬编码文本 |
|---------|-----------|
| `AnalyzePanel.tsx:347` | `submitUserReply("确认继续")` |
| `AnalyzePanel.tsx:354` | `submitUserReply("确认继续")` |
| `AnalyzePanel.tsx:357-359` | `submitUserReply("已核对上表中的 p 值、效应量与置信区间，同意进入报告阶段")` |
| `AnalyzePanel.tsx:364` | `submitUserReply("可以进入下一阶段了")` |

## 🔴 高危：后端固定文本替代 LLM 输出

| 文件:行 | 文本 | 说明 |
|---------|------|------|
| `agent.py:162` | `"生成数据画像..."` | AGENT_THINKING 固定文本 |
| `agent.py:264` | `"正在推理字段语义..."` | 同上 |
| `agent.py:125` | `{"goal": "理解数据字段和质量问题"}` | AGENT_STARTED goal 硬编码 |
| `orchestrator.py:308` | `"📄 导入了 {n} 条进度定义"` | 固定模板+emoji |
| `orchestrator.py:355` | `"⏩ 从 {stage} 阶段恢复..."` | 固定模板 |
| `orchestrator.py:437` | `"分析已由用户中止。"` | 固定取消文案 |
| `power_analysis.py` 全部 `user_message` 字段 | 12 处固定解释文本 | 剥夺 LLM 解释统计结果的能力 |

## 🟡 中危：前端替代 LLM 应输出的内容

| 文件:行 | 文本 | 说明 |
|---------|------|------|
| `utils.ts:20` | `"未能理解你的说明。请改用原始列名..."` | fallback 消息替代 LLM 澄清回复 |
| `AnalystReviewTable.tsx:14` | 引导说明文案 | 应来自 LLM |
| `FieldReviewTable.tsx:6` | summary fallback | 应来自 LLM |
| `wsGuardrails.ts:47` | 护栏拦截说明 | 应让 LLM 生成 |
| `ThinkingStrip.tsx:16` | ✅ 已修复 | "正在处理"改为 LLM thinking 文本 |

## 🟢 低危：可以接受

| 位置 | 说明 |
|------|------|
| Review 表格标题 ("评估清洗"等) | UI 标签 |
| `parsers.ts:163-164` 显著性映射 | 展示层本地化 |
| API error message | 系统级消息 |
