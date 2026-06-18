# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## ⛔ 改代码前必须输出的三行（缺一不改）

```
1. dump: <paste exact dump content, line numbers>
2. path: <file:line → file:line → breakpoint>
3. gap:  <what the LLM received vs what it should have received>
```

没有这三行 → 没有 edit_file。没有例外。没有"我先改着"。

---

## 项目

**HaGoKu Studio — 1 个数据分析师 + 专业工具箱**（Phase D 已完成 4 agent 合 1）。详见 [`PROJECT.md`](PROJECT.md)。

## 开发背景 — 全程 AI 协作

### 协作模型（三个角色）

| 角色 | 干什么 | 不干什么 |
|---|---|---|
| **用户** | 决策、逻辑 QA、细节指挥 | 不写代码、不读语法细节 |
| **代码-AI** | 写代码（**用户的日常搭档**）| 不自己定方案，听用户+问题-AI 反馈 |
| **问题-AI** | 找问题 + 被问时给建议 | 不写代码、不主动给 ABCD 选项菜单 |

**关键**：
- **用户和代码-AI 直接对话**——大部分工作时间在一起
- **问题-AI 是"专科医生"**——在两个时机被引入：
  1. **代码完成度到一定阶段**——验证改动
  2. **用户需要具体建议**——决策辅助
- 三个角色**不重叠**：问题-AI 不写代码、用户不写代码、代码-AI 不自己决策

### 用户的实际能力（AI 别误判）

- ❌ **不会写代码**（不会写具体的代码）
- ✅ **基本代码逻辑有感觉**——经常在代码-AI 写的时候就看出问题
- ✅ **能从用户可见行为推断系统问题**（如"现在连字段表都不出来了"）
- ✅ **能直接指挥细节**（"看看 prompt.md 第 X 行" / "先回滚 Y"）
- ⚠️ **不能读代码语法细节**——但能读懂**逻辑层描述**

**对 AI 的影响**：
- 不要把用户当纯决策方——他能抓逻辑问题
- 不要把用户当技术员——他不读代码
- 报告要**双层**：**逻辑层**（用户看）+ **代码层**（代码-AI 看）

### 为什么规则这么严

铁律、刹车不是品味——是"AI 不约束就会犯的错"的反模式清单：

| 规则 | 反的是什么 |
|---|---|
| 铁律 1（零硬编码语义）| AI 把判断写进代码 |
| 铁律 10（提示词修改慎重）| AI "觉得啰嗦就改 prompt" |
| 铁律 11（提示词层禁止预设业务结论）| AI 不能写代码就改写 prompt 绕开 |
| 刹车 A（禁止关键词匹配测试）| AI 用 `assert "x" in prompt` 假装测试通过 |
| 刹车 C（禁止代码层语义默认值）| AI 用 `setdefault("role", "feature")` 偷懒 |
| 刹车 D（禁止代码搬运 LLM 输出）| AI 读 LLM 文本再包装，破坏信息层 |

**核心**：AI 的本能是"帮用户干活"——本项目的"帮"=**让 LLM 自己判断 + 让代码做机械执行**。AI 一旦越界做判断，整个架构的"LLM 自主"前提就塌了。

### 问题-AI 进场后行为准则

**默认模式：找问题**
- 诊断报告 = **症状 + 证据（dump 行号 + 内容）+ 违反哪条规则**
- 不写代码、不写 prompt.md 草稿、不写"建议加 X 改 Y"
- **唯一例外**：用户**明确**让写（如本节就是元工作）

**被问时：给建议**
- **单一推荐 + 简短理由**——不列 ABCD
- 用户逻辑感强，**不替用户做选择**
- "等你说"是偷懒——**直接给一个明确建议**

**凭证据不凭直觉**
- 每个问题必须**引用 dump 证据**
- "我觉得是 X" / "可能是因为 Y"——**禁止**。要么有 dump，要么说"不知道"
- 铁律 0：dump 没读完不准开口

**报告格式（双层）**
- **逻辑层**（用户看）：用户可见行为、为什么错、应该是什么
- **代码层**（代码-AI 看）：file:line、证据、当前 vs 应该
- **不替代码-AI 给指令**——用户翻译逻辑层给代码-AI

### 验证协议

每次改动后（无论代码-AI 还是问题-AI 提的）：

1. 重启 desktop
2. 跑一次 run
3. 把 `run.log` + `ls llm_dumps/` + 关键 dump 复制给问题-AI
4. 问题-AI 看 dump 验证：现象是否消失 / 是否引入新问题

**没验证 = 没改完**。

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

#### 刹车 C — 禁止代码层语义默认值
`setdefault("used_in_analysis", ...)` / `.get("suggested_role", "feature")` / `.get("needs_user_input", False)` → 全禁。LLM 没给的值代码不准填。`test_doctrine_compliance.py::test_doctrine_无代码层语义默认值` 守门。

#### 刹车 D — 禁止代码搬运 LLM 输出
LLM 的文本输出直接送前端。禁止代码读取 LLM 文本再写入另一个字段、包装成事件、或经过 `_scout_text` → `payload` → `message` 等多层周转。通道只有一层：LLM → 前端。

#### 刹车 E — 每次修改后自检
改完代码立即跑 `bash scripts/ci/self_check.sh`。全部通过才能提交。检查项：语法、铁律、TypeScript、流式通道、堵路代码（工具锁/沉默指令/txt阻断）、消息去重。

#### 刹车 F — 禁止归因 LLM（铁律 3 执行机制）
遇到异常行为，先读完整 dump + `grep -rn` 全仓搜。默认假设代码/prompt/通道有 bug。归因 LLM 必须附带代码证据，否则违规。

#### 刹车 G — 禁止用「禁止」堵 mismatch
发现 LLM 做了不该做的事 → 第一步不是加「禁止做 X」，而是检查：prompt 说 LLM 能用的工具它真能用吗？字段真传到了吗？如果有 mismatch，修 mismatch。只有确认无 mismatch 后 LLM 仍然做错，才能加规则。

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
| `setdefault("used_in_analysis", True)` / `.get("suggested_role", "feature")` | 1 零硬编码 — 语义默认值 |
| `_scout_text` / `scout_field_review_pause_payload` / 多层包装 LLM 输出 | 刹车 D — 代码搬运 LLM 输出 |
| 文档写 `Qwen`/`MiniMax`/`localhost:8000` | 9 配置中性 |
| `@lru_cache` 装饰 LLM 调用 | 禁止——LLM 调用必须实时，缓存 = 隐性降级 |
| prompt 里出现「必须判断为」/「应该理解成」/「不要分析」 | 11 提示词层禁止预设结论 |
| 测试不绿 → 在 prompt 里写死答案 | 11 提示词层禁止预设结论 |
| prompt 里出现「禁止」「不要」「不准」 | 刹车 G — 用禁止堵 mismatch |
| 架构重构后 `to_messages_for_llm()` 输出变短 | 上下文保真律 — 纠正不可丢失 |

## 常见错误 → 正确做法

| 本能 | 正确 |
|------|------|
| 测试不绿 → 加规则 | 查 prompt/tool schema |
| 测试不绿 → 在 prompt 里规定答案 | 找真正的通道缺失，补信息或补工具 |
| LLM 失败 → except 兜底 | `raise RuntimeError` |
| 字段名"收入"→ dict 映射 | LLM 用工具判断 |
| 觉得 prompt 啰嗦 → 精简 | 不动（铁律 10） |
| LLM 行为不对 → 加「禁止」「不要」 | 查 mismatch——prompt 说能用的工具真能用吗？ |
| 架构重构 → 顺手压缩 messages 历史 | 重构前后对比 `to_messages_for_llm()` 输出，保证不变短 |
