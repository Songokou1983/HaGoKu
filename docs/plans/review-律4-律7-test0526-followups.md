# test0526 修复方案 — 审核与跟进建议（交付给实施者）

**审核时间**：2026-05-27
**审核对象**：`docs/plans/fix-律4-律7-test0526.md` 已落地的实现
**审核结论**：✅ 8 步全部完成、超额完成律 3 多轮历史、全套 360 passed 无回归。本文件列出 4 条非阻塞改进 + 1 条真实 LLM 验证建议 + 下一阶段路线。

---

## ✅ 已落地清单（验证通过）

| 律 / 步骤 | 实现位置 | 状态 |
|---|---|---|
| 律 4 · `restrict_analysis_to` 工具定义 | `hagoku/manager/orchestrator.py:568` | ✅ |
| 律 4 · `_apply_restrict_analysis_to` handler | `hagoku/manager/orchestrator.py:723-776` | ✅ |
| 律 4 · `_resolve_to_column_names` 业务名→列名映射 | `hagoku/manager/orchestrator.py:~690-720` | ✅ |
| 律 4 · system prompt「包含集纠错规则」教学段 | `hagoku/manager/orchestrator.py:943-947` | ✅ |
| 律 4 · 主 dispatch 分支 | `hagoku/manager/orchestrator.py:1017-1019` | ✅ |
| 律 7 · `_last_understanding_failure` 主路径写入 | `hagoku/manager/orchestrator.py:1119-1126` | ✅ |
| 律 7 · `_last_understanding_failure` 异常路径写入 | `hagoku/manager/orchestrator.py:1138-1144` | ✅ |
| 律 7 · 成功路径 pop 旧信号 | `hagoku/manager/orchestrator.py:1079, 1129` | ✅ |
| 律 7 · `scout_user_input_received_payload` 透传 | `hagoku/manager/orchestrator.py:1184-1188` | ✅ |
| 律 7 · 前端文案分支 | `hagoku_web/src/panels/AnalyzePanel.tsx:510-515` | ✅ |
| 律 2 · `utterances` 入口处保留 | `hagoku/manager/orchestrator.py:805-810` | ✅ |
| 律 2 · `utterances.consumed` 标记 | `hagoku/manager/orchestrator.py:1082, 1133` | ✅ |
| 律 9 · `_pending_reinference` 信号 + 重推断触发 | `hagoku/manager/orchestrator.py:775, 2135` | ✅ |
| 律 3 · `_conversation_history` 注入（超额完成） | `hagoku/manager/orchestrator.py:958-995` | ✅ |
| 测试 · 12 个用例（含 e2e） | `tests/test_product/test_information_arrival.py` | ✅ 12 passed |

---

## ⚠️ 4 条非阻塞改进建议

### 建议 1：`_conversation_history` 窗口口径不一致

**位置**：`hagoku/manager/orchestrator.py:963-994`

**问题**：

```python
# 注入历史轮次（最多保留最近 6 轮，避免 prompt 过长）
for turn in conv_history[-6:]:
    messages.append(...)
...
# 保留最近 10 轮（20 条消息）
if len(conv_history) > 20:
    conv_history = conv_history[-20:]
```

注释口径混乱：注入说"6 轮"（实际是 6 条消息 ≈ 3 轮），持久化说"10 轮（20 条消息）"（OK）。一个 conversation turn = user + assistant 两条消息。

**改法**：

```python
# 文件顶部常量化
_CONV_HISTORY_INJECT_TURNS = 3   # 注入到 prompt 的最近轮数（user+assistant 算 1 轮）
_CONV_HISTORY_KEEP_TURNS = 10    # 持久化保留的最近轮数

# 使用
for turn in conv_history[-(_CONV_HISTORY_INJECT_TURNS * 2):]:
    messages.append(...)
...
max_msgs = _CONV_HISTORY_KEEP_TURNS * 2
if len(conv_history) > max_msgs:
    conv_history = conv_history[-max_msgs:]
```

**收益**：注释与实际一致；调参集中在两个常量；读代码无歧义。

---

### 建议 2：`utterances` 无裁剪策略 → 长会话可能膨胀

**位置**：`hagoku/manager/orchestrator.py:805-810`

**问题**：每次 `_apply_scout_reply_with_llm` 入口都 `utterances.append(...)`，但没有截断。同一项目反复纠错的长会话下，`utterances` 数组单向增长，会一直跟着 context 序列化保存。

**改法**：在 append 之后加一行裁剪，与 `_conversation_history` 策略对齐：

```python
utterances: list[dict[str, Any]] = context.setdefault("utterances", [])
utterances.append({
    "raw_text": raw,
    "stage": "scout_field_review",
    "revision": context.get("interaction_revision", 0),
    "timestamp": _utc_now_iso(),  # 已有；如无则用 datetime.utcnow().isoformat()
    "consumed": False,
})
# 裁剪：保留最近 50 条 utterance（覆盖任何合理纠错回合数）
if len(utterances) > 50:
    context["utterances"] = utterances[-50:]
```

**收益**：防 context 单向膨胀；持久化文件大小可控；不影响审计信息（50 条足够）。

---

### 建议 3：测试缺「业务名解析」用例 — 真实场景未被覆盖

**位置**：`tests/test_product/test_information_arrival.py::test_真实场景_restrict_analysis_to_e2e`

**问题**：现 e2e 测试 mock LLM 返回的是**列名**：

```python
'{"included_fields": ["Code", "Period", "Inc1"]}'
```

这走的是 `_resolve_to_column_names` 中 `if t in col_set` 直通路径。但 test0526 现行犯的真实场景里，LLM 看到用户说"店铺收入"，更可能直接传**业务名**而非列名（特别是当 `column_descriptions` 已含业务名时）。当前 e2e 没覆盖 description / 前缀匹配分支。

**改法**：新增一个测试用例：

```python
def test_真实场景_restrict_analysis_to_业务名解析():
    """律 4 完整通路：LLM 用业务名调工具，_resolve_to_column_names 通过 description 命中。

    覆盖路径：包含集 = {店铺编号, 时间周期, 店铺收入}（用户原话中的业务名）
    映射依据：column_descriptions 中已有的业务描述。
    """
    from hagoku.manager.orchestrator import _apply_scout_reply_with_llm

    ctx = _make_real_scene_context()
    # 假设 Scout 第一轮已把业务描述填进去
    ctx["column_descriptions"] = {
        "Code": "店铺编号",
        "Period": "时间周期",
        "Inc1": "店铺收入",
        "Inc2": "其它收入",
        "Inc3": "杂项收入",
        "BU": "事业部",
        "StoreID": "店铺ID",
        "Bos1": "费用项",
    }

    spy = LLMSpy(response_factory=lambda m: _make_tool_call_response(
        '{"included_fields": ["店铺编号", "时间周期", "店铺收入"]}',
        function_name="restrict_analysis_to",
    ))
    _apply_scout_reply_with_llm(ctx, _REAL_SCENE_REPLY, _REAL_SCENE_COLUMNS, spy.client, "test")

    sem = {s["column_name"]: s for s in ctx["column_semantics"]}
    # 业务名通过 description 命中
    assert sem["Code"]["used_in_analysis"] is True, "店铺编号 → Code"
    assert sem["Period"]["used_in_analysis"] is True, "时间周期 → Period"
    assert sem["Inc1"]["used_in_analysis"] is True, "店铺收入 → Inc1"
    # 补集排除
    for c in ["BU", "Inc2", "Inc3", "StoreID", "Bos1"]:
        assert sem[c]["used_in_analysis"] is False, f"{c} 应被排除"
    assert ctx.get("_pending_reinference") is True
    assert ctx.get("_last_understanding_failure") is None
```

**收益**：覆盖 `_resolve_to_column_names` 的非直通路径；锁住"业务名 → 列名"映射能力；test0526 现行犯的真实形态被测试守护。

---

### 建议 4：`_apply_restrict_analysis_to` 嵌套循环可微优化

**位置**：`hagoku/manager/orchestrator.py:759-772`

**问题**：

```python
for c in keep_set:
    for s in semantics:
        if str(s.get("column_name", "")) == c:
            ...
for c in complement:
    for s in semantics:
        if str(s.get("column_name", "")) == c:
            ...
```

O(N²)。实际数据集 ≤30 列无感，但读起来重复且不直接表达「按列名查 semantic」的意图。

**改法**：

```python
sem_by_name: dict[str, dict] = {
    str(s.get("column_name", "")): s for s in semantics
}

for col in columns:
    target = col in keep_set
    s = sem_by_name.get(col)
    if s is None:
        continue
    s["used_in_analysis"] = target
    s["needs_user_input"] = False
    applied.append(f"{col}:[used_in_analysis]←{'true' if target else 'false'}")
```

**收益**：O(N)；意图清晰；applied 顺序与 `columns` 顺序一致（更可预测）。

---

## 🔬 真实 LLM 验证（强烈建议）

mock 测试只能保证「**如果** LLM 调用了 `restrict_analysis_to`，代码正确处理」。
真实 LLM 验证要回答「**LLM 是否真的会调用** `restrict_analysis_to`」——这才是 test0526 现行犯能否被根治的关键。

### 验证步骤

1. 启动本地 LLM 服务（`localhost:8080`，已有 `tests/test_field_llm_e2e.py` 模式）
2. 用一份与 test0526 同构的小数据集（含字段 Code/Period/Inc1/Inc2/Inc3/BU/StoreID/Bos1）
3. 走完整 Scout 流程：
   - query = `"分析店铺的收入变动趋势"`
   - 用户回复 = `"只有店铺编号、时间周期、店铺收入需要参与分析"`
4. 抓取 LLM 实际 tool_call 名 / 参数
5. 断言：
   - `restrict_analysis_to` 被调用（**核心**）
   - `included_fields` 包含至少一个能映射到 Inc1/Inc2/Inc3 的 token
   - context 中 `_pending_reinference is True`
   - 无 `_last_understanding_failure`

### 可能的真实 LLM 风险

| 风险 | 应对 |
|---|---|
| LLM 仍选择调用旧的 `update_field_role(ignored=...)` | 检查 system prompt 中「包含集纠错规则」是否被「最终强制规则」覆盖；考虑提高包含集规则的位置或加重语气 |
| LLM 调了 `restrict_analysis_to` 但 `included_fields` 全是业务名、`_resolve_to_column_names` 没命中 | 需要建议 3 的测试先保护住；并检查 `column_descriptions` 在调用前是否已填充 |
| LLM 同时调用多个工具（restrict + update_field_understanding） | 当前主循环 `continue` 跳过其它工具——确认这是否符合预期。如果想保留 update 的副作用（如补充 description），需调整循环逻辑 |

---

## 🎯 下一阶段路线（按 audit P2-P9）

### P2 · 单一权威 FieldSemantic 数据模型（律 5）

**当前漏水**：状态分散在三处：

- `context["column_semantics"]: list[dict]` — `column_name`, `used_in_analysis`, `suggested_role`, `needs_user_input`, ...
- `context["column_descriptions"]: dict[str, str]` — 业务描述
- `context["column_display_names"]: dict[str, str]` — 中文短名

修改任一处都可能与其它两处不同步。`_resolve_to_column_names` 已不得不同时读三个。

**目标**：合并为一个 `FieldSemantic` Pydantic 模型，单一字典 `context["fields"]: dict[str, FieldSemantic]`。

**预估**：1 日（结构改 + 全部读写位点迁移 + 兼容旧持久化文件的迁移函数）。

### P4-P9 · 其余律的渐进落地

按 audit 路线图，配合真实场景累积按需推进。当前 P0/P1/P2/P3 落地后，回头看 audit §4 决策。

---

## 📦 推荐 commit 拆分

如果以**单一 PR** 收尾本轮：
1. 当前实现 + 建议 1（窗口口径）+ 建议 2（utterances 裁剪）→ 主 PR
2. 建议 3（业务名解析测试）→ 紧随其后或合入主 PR
3. 建议 4（微优化）→ 可延后

如果**先 commit 现状**：
- 当前可直接 commit，所有建议放下一个 PR

---

## 给实施者的一句话交代

> 当前实现已超额完成 P1 修复方案，全套 360 测试通过。请按本文件 4 条非阻塞建议补完代码与测试，并安排一次真实 LLM 端到端验证（test0526 原句）。完成后 P1 阶段彻底关闭，开始 audit P2（FieldSemantic 单一权威数据模型）。
