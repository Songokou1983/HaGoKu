# 通道消息管理

> ChatGPT 怎么做，我们就怎么做。

---

## 谁可以发消息

| 来源 | role | 示例 |
|------|------|------|
| **用户** | user | 打字输入 |
| **LLM** | assistant | 文字回复、表格、提问 |
| **系统** | system | 分析开始、分析中止——纯状态通知 |
| ~~代码~~ | ~~system~~ | **禁止。代码不产出任何用户可见内容。** |

---

## 给 LLM 的和给用户的分开

| | 给 LLM (`to_llm_messages`) | 给用户 (`build_snapshot`) |
|---|---|---|
| assistant | ✅ | ✅ |
| user | ✅ | ✅ |
| tool | ✅ | ❌（JSON 对用户无意义） |
| system | ❌（是给用户看的） | ✅ |

---

## 当前违规

| # | 文件 | 行 | 问题 |
|---|------|:--:|------|
| 1 | session.py:84 | — | `to_llm_messages` 不过滤 system——LLM 看到给用户的表，干扰判断 |
| 2 | agent_tool_defs.py:144 | — | `_append_field_review` 死函数——拼 markdown 不写 |
| 3 | agent_tool_defs.py:136,140 | — | 调用死函数 |
| 4 | app.py:183 | — | build_snapshot 丢 collapsible 等 extra 字段 |
| 5 | handlers.ts:27 | — | roleMap "tool"→"system" 死映射 |
| 6 | handlers.ts:39 | — | collapsible 永不为真 |
| 7 | handlers.ts:141,182 | — | 注释"卡片"——已删 |
| 8 | reply_handlers.py:31 | — | 注释"卡片写入由工具 handler"——已删 |
| 9 | agent.py:599 | — | 注释"工具卡片"——已删 |
| 10 | ConvoFeed.tsx | — | `onAskReply` prop 未使用 |
| 11 | AnalyzePanel.tsx:298 | — | `onAskReply={submitUserReply}` 白传 |
| 12 | useAnalyzeSession.ts:32 | — | `fieldReviewScrollNonce` 死代码 |

---

## 保留的 session.add

- agent.py:541 — LLM 产出 (assistant)
- agent.py:597 — add_tool_call (assistant+tool)
- ws_handler.py:458 — 用户输入 (user)
- orchestrator.py:311 — 系统通知 (进度导入)
- orchestrator.py:442 — 系统通知 (分析中止)
