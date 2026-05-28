# HaGoKu 律 4 + 律 7 双修方案 — test0526 现行犯

**触发场景**：用户 2026-05-26 报告
- 分析目标：`分析店铺的收入变动趋势`
- 用户原话：`只有店铺编号、时间周期、店铺收入需要参与分析`
- 系统回复：`本轮 0 条写入（回复 22 字）。仍需确认的列：（无）`

**P1 抓现行犯结论**（已通过 `tests/test_product/test_information_arrival.py` 11 个测试坐实）：

| 律 | 状态 | 证据 |
|---|------|------|
| 律 1 意图穿透 | ✅ 抵达 | `test_真实场景_律1律2_意图与原话均抵达LLM` |
| 律 2 原话抵达 LLM | ✅ 抵达 | 同上 |
| 律 4 工具表达通路 | ❌ 漏 | `test_真实场景_律4_工具是否能表达补集排除`：工具只能说"排除"，不能直接说"包含" |
| 律 7 不确定可见化 | ❌ 漏 | `test_真实场景_律7_LLM未理解时无未理解信号`：空 tool_calls 无信号 |
| 律 2 结构化保留 | ❌ 半漏 | `test_真实场景_律2_用户原话保存到context`：raw 函数返回后丢失 |

**真因画图**：

```
用户原话："只有店铺编号、时间周期、店铺收入需要参与分析"
          │
          ▼ ✅ 律 1/2 — 信息通道无残缺
       LLM 收到了
          │
          ▼ ❌ 律 4 — LLM 想表达"包含集"，但工具只有"补集"出口
       LLM 沉默（空 tool_calls）
          │
          ▼ ❌ 律 7 — 代码不向用户暴露"未理解"
       前端："本轮 0 条写入" → 用户："我说的没用"
```

---

## 主要文件清单（按改动量排）

| 文件 | 函数/区块 | 改动点 |
|------|----------|--------|
| `hagoku/manager/orchestrator.py:466-563` | `_SCOUT_FIELD_UPDATE_TOOLS` | **律 4**：新增 `restrict_analysis_to` 工具 |
| `hagoku/manager/orchestrator.py:650-960` | `_apply_scout_reply_with_llm` | **律 4**：新增 tool 分支；**律 7**：返回前判定空 applied → 写 `_last_understanding_failure`；**律 2**：入口处保留 raw 到 `context["utterances"]` |
| `hagoku/manager/orchestrator.py` | `_apply_role_update`（约 565-650） | **律 4**：抽出可复用的「列名解析 + ignored 落地」逻辑，新增 `_resolve_to_column_names` |
| `hagoku/manager/orchestrator.py` | `scout_user_input_received_payload` | **律 7**：透传 `understanding_failure` 字段 |
| `hagoku_web/src/panels/AnalyzePanel.tsx:494-518` | `formatScoutUserInputFactLine` | **律 7**：当 `inner.understanding_failure` 存在时显示「系统未理解你的输入，请换一种说法」 |
| `tests/test_product/test_information_arrival.py` | `test_真实场景_律7_*`、`test_真实场景_律4_*`、`test_真实场景_律2_*` | 修完后改为正向断言 + 新增端到端落地测试 |

---

## 律 4 修复 — `restrict_analysis_to` 工具

### 1. 新增工具定义（`_SCOUT_FIELD_UPDATE_TOOLS` 末尾）

```python
{
    "type": "function",
    "function": {
        "name": "restrict_analysis_to",
        "description": (
            "当用户用「只有 X、Y、Z 参与分析」「我只关心 A 和 B」等**包含集**语义"
            "限定参与分析的字段时调用此工具。"
            "代码会自动把未列出的字段 used_in_analysis 设为 false，无需你计算补集。"
            "字段可用列名（Code/Inc1）或业务名（店铺编号/店铺收入）任一种表达，"
            "代码会基于当前 column_descriptions/display_names 做映射。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "included_fields": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "用户明确希望参与分析的字段，列名或业务名均可。",
                },
                "rationale": {
                    "type": "string",
                    "description": "你为何这样理解用户原话的简要说明（可选，便于审计）。",
                },
            },
            "required": ["included_fields"],
        },
    },
},
```

### 2. system prompt 增补一段（`_apply_scout_reply_with_llm` 内拼接 system_msg 处）

> **包含集纠错（最高优先级）**：当用户说"只有 X、Y、Z 参与分析"「我只要看 A 和 B」「除了 X 都不参与」，**必须调用 `restrict_analysis_to(included_fields=[...])`**，把用户提到的字段（业务名或列名都可）放入参数。代码会做映射和补集运算，你无需算补集。

### 3. tool_calls 分支（`_apply_scout_reply_with_llm` 主路径，约第 849 行附近）

```python
if func_name == "restrict_analysis_to":
    args = _json.loads(func_args_str) if isinstance(func_args_str, str) else func_args_str
    raw_includes = args.get("included_fields") or []
    # 业务名 → 列名映射
    resolved = _resolve_to_column_names(raw_includes, columns, display_names, descs)
    if not resolved:
        continue  # 落空，让律 7 接手
    # 落地：包含集 used_in_analysis=true、补集 used_in_analysis=false
    keep = set(resolved)
    for s in semantics:
        col = str(s.get("column_name", ""))
        s["used_in_analysis"] = col in keep
        applied.append(f"{col}:[uia]←{col in keep}")
    # 律 9 钩子：标记结构性变更
    context["_pending_reinference"] = True
    continue
```

### 4. 业务名→列名解析辅助函数（新增）

```python
def _resolve_to_column_names(
    tokens: list[str],
    columns: list[str],
    display_names: dict[str, str],
    descriptions: dict[str, str],
) -> list[str]:
    """把用户给的业务名 / 列名混合 token 映射为真实列名。
    优先级：精确列名 > display_name 完全匹配 > description 包含 > 列名前缀（Inc → Inc1/2/3）。
    无映射的 token 静默丢弃（由律 7 在外层判定空集时报"未理解"）。"""
    col_set = set(columns)
    dn_to_col = {v: k for k, v in display_names.items() if v}
    out: list[str] = []
    for t in tokens:
        t = (t or "").strip()
        if not t:
            continue
        if t in col_set:
            out.append(t)
        elif t in dn_to_col:
            out.append(dn_to_col[t])
        else:
            # description 包含 / 前缀匹配（如"店铺收入"→ Inc1/2/3）
            matched = [c for c in columns if t in (descriptions.get(c) or "")]
            matched += [c for c in columns if c.lower().startswith(t.lower()) and c not in matched]
            out.extend(matched)
    return list(dict.fromkeys(out))  # 去重保序
```

---

## 律 7 修复 — 未理解信号

### 5. `_apply_scout_reply_with_llm` 返回前补一段

```python
# 已有：if tool_calls: ... 处理完
# 新增：若整轮无任何 applied 且 raw 非空 → 写未理解信号
if not applied and raw.strip():
    context["_last_understanding_failure"] = {
        "raw_text": raw,
        "model_reply_text": _raw_text or "",
        "had_tool_calls": bool(tool_calls),
        "stage": "scout_field_review",
    }
else:
    context.pop("_last_understanding_failure", None)
return applied
```

### 6. `scout_user_input_received_payload` 增字段

```python
def scout_user_input_received_payload(ctx, raw, applied, revision):
    # ... 原逻辑 ...
    failure = ctx.get("_last_understanding_failure")
    payload["understanding_failure"] = failure  # None 或 dict
    return payload
```

### 7. 律 2 结构化保留（顺手补，几行）

在 `_apply_scout_reply_with_llm` 入口处：

```python
if raw and raw.strip():
    utterances = context.setdefault("utterances", [])
    utterances.append({
        "raw_text": raw,
        "stage": "scout_field_review",
        "revision": context.get("interaction_revision", 0),
        "consumed": False,  # tool_call 落地后由分支改 True
    })
```

### 8. 前端文案（`AnalyzePanel.tsx:494-518`）

```typescript
function formatScoutUserInputFactLine(inner: Record<string, unknown>): string {
  // 优先检查未理解信号
  const failure = inner.understanding_failure as { raw_text?: string } | null | undefined;
  if (failure && typeof failure === "object") {
    return `系统未理解你的输入「${failure.raw_text ?? ""}」，请尝试换一种说法（例如直接给出列名、或更具体的业务关系）。`;
  }
  // ... 原有 lines/count/pure 逻辑保持不变 ...
}
```

---

## 测试调整

把现有 3 个反向探针改为正向断言：

```python
# test_真实场景_律4_工具是否能表达补集排除  → 改名为 _直接表达包含集
assert "restrict_analysis_to" in tool_names

# test_真实场景_律7_LLM未理解时无未理解信号  → 改为正向
assert ctx.get("_last_understanding_failure") is not None
assert ctx["_last_understanding_failure"]["raw_text"] == _REAL_SCENE_REPLY

# test_真实场景_律2_用户原话保存到context  → 改为正向
assert any(u["raw_text"] == _REAL_SCENE_REPLY for u in ctx.get("utterances", []))
```

再补一条**端到端用例**（mock LLM 返回 `restrict_analysis_to(included_fields=["店铺编号","时间周期","店铺收入"])`），断言：

- `Inc1/Inc2/Inc3` 中至少一个 `used_in_analysis=True`（前缀匹配命中）
- `BU/StoreID/Bos1` 全部 `used_in_analysis=False`
- `context["_pending_reinference"] is True`
- `applied` 非空、无 `_last_understanding_failure`

---

## 操作顺序建议（如分两次提交）

1. **PR-A（律 7 + 律 2 结构化）**：步骤 5、6、7、8 + 测试调整。半天。**用户即刻看到「未理解」反馈**。
2. **PR-B（律 4 主因）**：步骤 1、2、3、4 + 端到端用例。1 天。**用户那句话能被直接落地**。

如一次到位：1→2→3→4→5→6→7→8。改动集中在 `orchestrator.py`（约 80-120 行 diff）+ `AnalyzePanel.tsx`（约 8 行）+ 测试文件（约 30 行）。

---

## 给开发的一句话交代

> 信息通道没问题——用户原话和分析意图都到 LLM 了。卡点是：① LLM 想说"只保留这几个"但工具只让它说"排除那几个"；② LLM 放弃后代码静默吃掉。修两点：加一个正向工具让 LLM 表达「包含集」由代码做补集运算；空 applied 时往 context 写「未理解」让前端报警。`orchestrator.py` 主战场，前端 `AnalyzePanel.tsx` 改一行文案分支。
