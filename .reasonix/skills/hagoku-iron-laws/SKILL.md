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

查运行日志（时间线，固定路径）：
```bash
tail -30 ~/.hagoku/hagoku.log
# 如果文件过大 → head -5 看最新事件
# 如果文件不存在 → ls -la ~/.hagoku/ 检查目录结构
```

查 session（前端显示的对话镜像）：
```bash
# 优先用固定路径（session保存时同步到 session.latest.json）
latest=~/.hagoku/projects/*/session.latest.json
for f in $latest; do
  [ -f "$f" ] && python3 -c "
import json,sys
d=json.load(open('$f'))
msgs=d['messages']
print(f'{d.get(\"analysis_goal\",\"?\")}: {len(msgs)}条消息')
ua=[m for m in msgs if m.get('role') in ('user','assistant')]
print(f'  对话: {len(ua)}条')
for m in msgs[-4:]:
    r=m.get('role','?')
    c=str(m.get('content',''))[:60]
    print(f'  [{r}] {c}')
"
done
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
| 找不到日志/session/数据 | **铁律 12 扩展 → 只跑一条命令就结论不存在 = 撒谎。** 必须试 3 种以上方法再下结论。固定路径优先：`~/.hagoku/hagoku.log` / `{project_dir}/session.latest.json` |
| 后端改了状态只发 ack 不发 WS 推送 | 刹车 I → 状态同步：后端清空自己 ≠ 前端知道了 |
| 说"可能是…""估计是…""试试…"（无日志证据） | **铁律 12 / 刹车 J** → 停下来补日志系统，拿到证据再开口 |
| 另开 REST /switch、useEffect 清消息、localStorage 恢复 | **铁律 13 / 刹车 K** → `handleStateSnapshot` 是前端状态唯一写入点。不准绕开。 |
| 改 handlers/AnalyzePanel/ProjectPanel 后不查唯一真相源 | **违反验证协议** → 必须 grep `clearMessages|fetch.*switch|setCurrentDataPath` 确认不在 `handleStateSnapshot` 外出现 |

## 系统认知

- **单入口**: `session.to_llm_messages()` → `build_messages()` — 唯一 LLM 消息路径
- **对话循环**: `run_step()` (`hagoku/agents/agent.py` 中的 `while tc_list and _round < 20` 自续轮) — 已有工具调用→dispatch→回传→继续。不自己写循环
- **流程控制**: LLM 自驱动（读对话历史判断当前阶段）。代码不做 if-elif 阶段判断。`route_to` 工具已于 2026-06-24 永久删除
- **代码=通道**: 不替 LLM 做语义判断，不替用户做选择
- **唯一真相源**: `handleStateSnapshot` 是前端状态的唯一写入点。WS `state_snapshot` 是项目切换和断连重连的唯一数据通道。不准另开路径。
- **项目真相**: `PROJECT.md`、`CLAUDE.md`、`reasonix.toml`

## 流程

1. 用户反馈问题 → 先读 dump + 日志 + session（`ls -lt ~/.hagoku/llm_dumps/` + `tail -30 ~/.hagoku/hagoku.log` + 读 session.json 对话数据）
2. 贴 dump 证据 → 回答四行
3. 用户确认 → 改代码
4. **唯一真相源自查** — 改过 `handlers.ts` / `AnalyzePanel.tsx` / `ProjectPanel.tsx` 后，必须 grep `clearMessages|fetch.*switch|setCurrentDataPath` 确认这些操作不出现在 `handleStateSnapshot` 之外。如果有 → 撤回，改由 WS snapshot 推送。
5. 跑 `bash scripts/ci/self_check.sh` + `pytest`
6. commit message 含 dump/path/gap + 【自检】
