---
name: hagoku-iron-laws
description: 改代码前强制执行四行诊断+铁律检查，不可跳过
---

# HaGoKu 铁律执行器

每次改代码前必须完成，不可跳过。

## ⛔ 强制第一步：查 dump + 查日志 + 查 session（三者缺一不可）

**每次用户反馈问题，必须先执行以下命令并贴出结果：**

查 LLM dump：
```bash
ls -lt ~/.hagoku/llm_dumps/ | head -5
# 项目 dump
find ~/.hagoku/projects -name 'llm_dumps' -type d | while read d; do ls -lt "$d" | head -3; done
```

查运行日志（时间线）：
```bash
tail -30 ~/.hagoku/hagoku.log
```

查 session（前端显示的对话镜像）：
```bash
find ~/.hagoku/projects -name 'session.json' -newer /tmp/api.log | head -1 | xargs python3 -c "
import json,sys
d=json.load(open(sys.argv[1]))
msgs=d['messages']
ua=[m for m in msgs if m.get('role') in ('user','assistant')]
print(f'{len(msgs)}条总消息, {len(ua)}条对话')
"
```

**dump 回答 LLM 在想什么。日志回答系统在干什么。session 回答前端显示了什么。三者缺一不可。禁止问用户"你看到了什么"。**

## 四行诊断（缺一不写代码）

回答以下四行再调用 edit_file：
1. **dump + 日志**: 粘贴 dump 原文 + 日志关键行（文件路径:行号:内容）
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
| 不看日志就说"后端没问题" | 铁律 12 → 先 `tail -30 ~/.hagoku/hagoku.log` |
| 不看 session 就问用户"你看到了什么" | 铁律 13 → session 是前端对话镜像 |

## 系统认知

- **单入口**: `to_messages_for_llm()` → `build_messages()` — 唯一 LLM 消息路径
- **对话循环**: `run_step()` — 已有工具调用→dispatch→回传→继续。不自己写循环
- **流程控制**: LLM 通过 `route_to` 决定阶段。代码不做 if-elif 判断
- **代码=通道**: 不替 LLM 做语义判断，不替用户做选择
- **项目真相**: `PROJECT.md`、`CLAUDE.md`、`reasonix.toml`

## 流程

1. 用户反馈问题 → 先读 dump + 日志 + session（`ls -lt ~/.hagoku/llm_dumps/` + `tail -30 ~/.hagoku/hagoku.log` + 读 session.json 对话数据）
2. 贴 dump 证据 → 回答四行
3. 用户确认 → 改代码
4. 跑 `bash scripts/ci/self_check.sh` + `pytest`
5. commit message 含 dump/path/gap + 【自检】
