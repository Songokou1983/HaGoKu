# CLAUDE.md

## ⛔ 第一原则：改代码前必须有这三行

```
1. dump: <paste exact dump content, line numbers>
2. path: <file:line → file:line → breakpoint>
3. gap:  <what LLM received vs what it should have received>
```

**没有这三行 → 没有 edit_file。没有例外。没有"我先改着"。**

---

## 铁律（违反 = 无效）

| # | 规则 | 一句话 |
|---|------|--------|
| 0 | 查 dump 再开口 | `ls -lt ~/.hagoku/llm_dumps/ \| head -5`，贴证据 |
| -2 | 用户确认前禁止改代码 | 报根因 + 方案 → 等用户说"修" → 才动 |
| -3 | 禁止无证据归因外部 | 不说"可能是模型问题"——贴 dump 行号 |
| -4 | 禁止绕过已有诊断 | dump 没读完不准加新日志 |
| 1 | 零硬编码语义 | 关键词列表/中文if-elif/regex → 全禁 |
| 7 | 失败在场 | LLM失败 → `raise RuntimeError`，不except兜底 |
| 9 | 配置中性 | 不写死模型名/URL/端口 |
| 10 | 提示词修改慎重 | 改 prompt 必须：开dump→定位→最小改→dump对比 |
| 11 | 提示词不预设结论 | 说"你面对什么"✅ 说"你应该得出什么"❌ |

---

## 刹车（最常犯的排前面）

| 刹车 | 触发词 | 一句话 |
|------|--------|--------|
| **F** | "可能是模型的问题" | 默认假设代码/prompt/通道有bug，归因LLM必须带代码证据 |
| **G** | prompt里出现"禁止/不要/不准" | 先查mismatch：prompt说的工具真能用吗？字段真传到了吗？修mismatch，不加禁止 |
| **C** | `setdefault` / `.get("role","feature")` | LLM没给的值代码不准填 |
| **D** | `_scout_text` → payload → message | LLM文本直接送前端，不经过代码多层周转 |
| **E** | 改完代码 | 跑 `bash scripts/ci/self_check.sh` 全部通过才提交 |

---

## 触发词速查

| 你在写 | 违反 |
|--------|------|
| `except: return []` / `except: return None` | 铁律 7 |
| `["收入","营收"]` / `re.search(r"收入\|销售")` | 铁律 1 |
| `setdefault("used_in_analysis", True)` / `.get("suggested_role", "feature")` | 刹车 C |
| `_scout_text` / 多层包装LLM输出 | 刹车 D |
| prompt里「必须判断为」「应该理解成」「不要分析」 | 铁律 11 |
| prompt里「禁止」「不要」「不准」 | 刹车 G |
| `@lru_cache` 装饰 LLM 调用 | 铁律 7 |

---

## 常见错误 → 正确做法

| 本能 | 正确 |
|------|------|
| 测试不绿 → 加规则 | 查 prompt/tool schema |
| LLM 行为不对 → 加「禁止」「不要」 | 查 mismatch——prompt 说能用的工具真能用吗？ |
| LLM 失败 → except 兜底 | `raise RuntimeError` |
| 觉得 prompt 啰嗦 → 精简 | 不动（铁律 10） |

---

## 项目

**HaGoKu Studio — 1 个数据分析师 + 专业工具箱**（Phase D 已完成 4 agent 合 1）。详见 [`PROJECT.md`](PROJECT.md)。

## 已由架构自动守门（不需人记）
- `build_messages()` 唯一入口 → pre-commit hook 自动拦截
- `to_messages_for_llm()` 统一 LLM 调用 → agent 内无法直接构造 messages
- `route_to` 阶段切换 → 代码无 if-elif 中文分支

## 开发背景 — 全程 AI 协作

### 协作模型（三个角色）

| 角色 | 干什么 | 不干什么 |
|---|---|---|
| **用户** | 决策、逻辑 QA、细节指挥 | 不写代码、不读语法细节 |
| **代码-AI** | 写代码（**用户的日常搭档**）| 不自己定方案，听用户+问题-AI 反馈 |
| **问题-AI** | 找问题 + 被问时给建议 | 不写代码、不主动给 ABCD 选项菜单 |

### 用户的实际能力

- ❌ 不会写代码
- ✅ 基本代码逻辑有感觉——经常在代码-AI 写的时候就看出问题
- ✅ 能从用户可见行为推断系统问题
- ✅ 能直接指挥细节
- ⚠️ 不能读代码语法细节——但能读懂逻辑层描述

### 为什么规则这么严

铁律、刹车不是品味——是"AI 不约束就会犯的错"的反模式清单。核心：AI 的本能是"帮用户干活"——本项目的"帮"=**让 LLM 自己判断 + 让代码做机械执行**。AI 一旦越界做判断，整个架构的"LLM 自主"前提就塌了。

### 验证协议

1. 重启 desktop
2. 跑一次 run
3. 把 `run.log` + `ls llm_dumps/` + 关键 dump 复制给问题-AI
4. 问题-AI 看 dump 验证：现象是否消失 / 是否引入新问题

**没验证 = 没改完**。
