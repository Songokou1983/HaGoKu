# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## 项目

**HaGoKu Studio — 1 个数据分析师 + 专业工具箱**（Phase D 已完成 4 agent 合 1）。详见 [`PROJECT.md`](PROJECT.md)。

## 铁律（违反 = PR 拒）

### 铁律 0 — 查 dump 再开口
收到报错：先 `ls -lt ~/.hagoku/llm_dumps/ | head -5`，引用 dump 证据再改代码。

### 铁律 -1 — 禁用回滚，只做正向修复
禁止 `git revert` / `git reset` / `git checkout -- file`。删错了用户许可才能恢复。

### 铁律 -2 — 用户确认前禁止改代码
发现 bug → 报告根因 + 方案 → 等用户说"修/改/做" → 才动代码。

### 铁律 -3 — 禁止无证据归因外部系统
禁止说"可能是模型/浏览器/网络/代理的问题"——贴日志/dump 行号证据。

### 铁律 -4 — 禁止绕过已有诊断信息
dump 没读完不准加新日志、不准写 E2E 脚本替代读 dump。

### 铁律 1 — 零硬编码语义
业务关键词列表、中文正则分支、if-elif 中文意图链 → 全禁。LLM 的活代码不替。prompt 说流程不说结论。

### 铁律 7 — 失败在场
LLM 失败 → `raise RuntimeError` 让用户看见。禁止 except 兜底/默认值/缓存降级/静默重试。

### 铁律 9 — 配置中性
文档/AI 输出/记忆不绑具体模型名/URL/端口。写 `<用户配置>` 占位。

### 铁律 10 — 提示词修改慎重
禁止全文重写 prompt.md、无 dump 对比删 system_prompt 片段、"觉得啰嗦"就改。改 prompt 必须：开 dump → 定位 → 最小改 → dump 对比 → commit 引用证据。

#### 刹车 A — 禁止提示词关键词匹配测试
`assert "ignore" in prompt` → 范畴错误，测试 GREEN ≠ 行为正确。

#### 刹车 B — 提示词 PR 必须附 dump 对比
改 prompt.md / system_prompt / tool description → PR body 含改前/改后 dump。

### 铁律 11 — 提示词层禁止预设业务结论

> **漏洞转移防线**：铁律 1 限制了代码层，但 AI 实现者在代码层被限制后，容易把同样的"替 LLM 做判断"转移到提示词里。表面合规，实质违规。

**合法的提示词内容**（装备信息）：
- 当前阶段说明、字段列表、用户原话、工具签名、输出格式

**违规的提示词内容**（预设业务结论）：
- "你**必须**把带'收入'字样的字段判断为 target"
- "如果用户说 X，**应该**理解成 Y"
- "**不要**分析 Z 类型的关系"
- 为了让某个测试通过而在 prompt 里写死"当遇到 A 场景时输出 B"

**最典型触发场景**：测试不绿 → 在 prompt 里规定答案 → 测试绿了 → 实质上变成了提示词层硬编码。

**区分线**：提示词说"你面对什么"是合法的。提示词说"你应该得出什么"是违规的。

### 已由架构自动守门（不需人记）
- `build_messages()` 唯一入口 → pre-commit hook 自动拦截（Phase B5）
- `to_messages_for_llm()` 统一 LLM 调用 → agent 内无法直接构造 messages（Phase D）
- `route_to` 阶段切换 → 代码无 if-elif 中文分支（Phase C）
- 禁止 tool 结果字符串化 → 方案 B OpenAI 标准协议（Phase B）

## 触发词速查（写代码时秒查）

| 触发 | 铁律 |
|------|------|
| `except: return []` / `except: return None` | 7 失败在场 |
| `if intent == "预测"` / 中文 if-elif | 1 零硬编码 |
| `["收入","营收"]` / `re.search(r"收入\|销售")` | 1 零硬编码 |
| 文档写 `Qwen`/`MiniMax`/`localhost:8000` | 9 配置中性 |
| `@lru_cache` 装饰 LLM 调用 | 禁止——LLM 调用必须实时，缓存 = 隐性降级 |
| prompt 里出现「必须判断为」/「应该理解成」/「不要分析」 | 11 提示词层禁止预设结论 |
| 测试不绿 → 在 prompt 里写死答案 | 11 提示词层禁止预设结论 |
| 架构重构后 `to_messages_for_llm()` 输出变短 | 上下文保真律 — 纠正不可丢失 |

## 常见错误 → 正确做法

| 本能 | 正确 |
|------|------|
| 测试不绿 → 加规则 | 查 prompt/tool schema |
| 测试不绿 → 在 prompt 里规定答案 | 找真正的通道缺失，补信息或补工具 |
| LLM 失败 → except 兜底 | `raise RuntimeError` |
| 字段名"收入"→ dict 映射 | LLM 用工具判断 |
| 觉得 prompt 啰嗦 → 精简 | 不动（铁律 10） |
| 架构重构 → 顺手压缩 messages 历史 | 重构前后对比 `to_messages_for_llm()` 输出，保证不变短 |
