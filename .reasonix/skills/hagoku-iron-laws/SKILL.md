---
name: hagoku-iron-laws
description: 改代码前强制执行四行诊断+铁律检查，不可跳过
---

# HaGoKu 铁律执行器

每次改代码前必须完成，不可跳过。

## 四行诊断（缺一不写代码）

回答以下四行再调用 edit_file：
1. **dump**: 粘贴 dump 原文（文件路径:行号:内容）
2. **path**: 从入口到断裂点的代码路径（file:line → file:line）
3. **gap**: LLM 收到了什么 vs 应该收到什么
4. **exists**: 系统里已有代码可以解决这个问题吗？（grep 搜过后回答 file:line 或 none）

## 铁律速查

| 触发 | 禁止 |
|------|------|
| 关键词列表、中文 if-elif | 铁律 1 → 让 LLM 判断 |
| `except: pass/return []` | 铁律 7 → raise RuntimeError |
| `setdefault` / `.get("role", "feature")` | 刹车 C → 删 |
| prompt 里「禁止」「不要」「不准」 | 刹车 G → 查 mismatch 先 |
| 改 prompt 不加 dump 对比 | 铁律 10 → 必须先 dump |
| 说"可能是模型的问题" | 刹车 F → 贴代码证据 |
| `return null` / `pass` 在渲染路径 | 检查 → 是否静默吞行为 |

## 系统认知

- **单入口**: `to_messages_for_llm()` → `build_messages()` — 唯一 LLM 消息路径
- **对话循环**: `run_step()` — 已有工具调用→dispatch→回传→继续。不自己写循环
- **流程控制**: LLM 通过 `route_to` 决定阶段。代码不做 if-elif 判断
- **代码=通道**: 不替 LLM 做语义判断，不替用户做选择
- **项目真相**: `PROJECT.md`、`CLAUDE.md`、`reasonix.toml`

## 流程

1. 用户反馈问题 → 先读 dump（`ls -lt ~/.hagoku/.../llm_dumps/`）
2. 贴 dump 证据 → 回答四行
3. 用户确认 → 改代码
4. 跑 `bash scripts/ci/self_check.sh` + `pytest`
5. commit message 含 dump/path/gap + 【自检】
