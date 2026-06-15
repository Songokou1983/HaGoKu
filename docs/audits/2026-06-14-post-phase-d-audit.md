# Phase D 后架构审计报告（2026-06-14）

> **审计人**：Cascade（AI 审核方）
> **审计范围**：Phase A-D 完成后代码和文档的一致性、架构承诺兑现度、隐性问题
> **测试状态**：601 passed, 0 failures（doctrine + information_arrival + 全套回归）

---

## 总结

Phase D 的核心承诺是「物理唯一入口 `to_messages_for_llm()`」和「4 agent 合 1」。经审计：
- ✅ 4 个旧 agent 目录已删干净
- ✅ crewai 依赖已清除
- ✅ `from hagoku.agents.scout|cleaner|analyst|reporter` 全仓 0 命中
- ✅ `from hagoku.kb` 全仓 0 命中
- ⚠️ 「物理唯一入口」**尚未完全兑现**——存在 8 处绕过点

---

## Finding 1（严重）：`build_messages()` 直接调用仍存在 8 处

**承诺**：Phase D 后所有 LLM 调用走 `to_messages_for_llm()`，agent 内无法直接构造 messages。

**事实**：`build_messages()` 在以下 8 个位置被直接调用（绕过 ProjectContext）：

| # | 文件 | 行号区域 | 场景 |
|---|------|---------|------|
| 1 | `hagoku/agents/agent.py` | `infer_field_semantics()` L266 | `project_ctx` 为 None 时回退 |
| 2 | `hagoku/manager/query_parser.py` | `_llm_parse_intent()` L97 | 意图解析 |
| 3 | `hagoku/manager/refinement.py` | `_parse_via_llm()` L174, L188 | 反馈解析（含异常重试） |
| 4 | `hagoku/manager/orchestrator.py` | `_call_llm_for_plan()` L438 | 计划生成 |
| 5 | `hagoku/manager/llm_dispatch/confirmation.py` | `_llm_classify_confirmation()` L21 | 确认分类 |
| 6 | `hagoku/manager/llm_dispatch/reply_handlers.py` | `_rewrite_as_written_summary()` L170 | 摘要重写 |
| 7 | `hagoku/manager/payloads/pipeline_helpers.py` | 护栏风险分析 L114 | 护栏 LLM |
| 8 | `hagoku/agents/lesson_auditor/agent.py` | `_llm_audit()` L108 | Lesson 审计 |

**影响**：这些调用不经过 ProjectContext，不进入对话历史，LLM 看不到上下文→推断质量降级。同时违背 CLAUDE.md §61 「已由架构自动守门」的宣告。

**修复方案**：

- **#1（agent.py fallback）**：删除 `else: build_messages(...)` 分支。`project_ctx` 为 None 应 raise RuntimeError（铁律 7）。
- **#2-5（独立 LLM 调用）**：这些是"辅助 LLM"（意图解析/计划生成/确认分类/refinement），不写入主 chat 是合理的。但应在代码注释中标注为 `# EXEMPT: 辅助 LLM，非主对话通道`，并考虑加入 pre-commit 白名单而非无标注。
- **#6（reply_handlers）**：`_rewrite_as_written_summary` 是主对话路径的一环——摘要重写结果会展示给用户。应迁移到走 `to_messages_for_llm()`。
- **#7（pipeline_helpers）**：护栏风险分析是辅助 LLM，可豁免但需标注。
- **#8（lesson_auditor）**：Meta 层辅助 LLM，使用 `meta_llm` 配置，合理豁免。

**优先级**：P1（#1 必须修；#6 应修）；P2（#2-5,7,8 标注豁免）

---

## Finding 2（高）：`pipeline_helpers.py` 铁律 7 违规

```python
# hagoku/manager/payloads/pipeline_helpers.py:123-128
except Exception as e:
    logger.warning(f"LLM 风险分析失败，使用默认护栏报告: {e}")
    risk_analysis = (
        "无法生成风险分析（LLM 调用失败）。请人工审核以下护栏违规详情。\n\n"
        f"{violation_summary}"
    )
```

**问题**：LLM 调用失败后 `logger.warning` + 降级为默认文本。铁律 7 要求 `raise RuntimeError`。

**辩护空间**：这是护栏报告的「风险分析」附加段——即使 LLM 失败，护栏违规详情本身是代码产出的事实数据，不依赖 LLM。可以认为"LLM 风险分析"是增值而非必须。

**修复方案**：不 raise，但将 `logger.warning` 改为向用户显式展示「LLM 风险分析不可用」（已基本做到），并在代码注释标注 `# 豁免铁律 7：risk_analysis 是增值段，核心护栏报告不依赖 LLM`。

**优先级**：P2

---

## Finding 3（高）：`scout_reply.py` 仍有 759 行

**承诺**：Phase B 设计文档预估 `scout_reply.py` 收缩到 ~300 行以下。

**事实**：759 行仍在，且 `reply_handlers.py`（335 行）+ `orchestrator.py`（688 行）= 管理层合计 1782 行。

**影响**：`scout_reply.py` 是 Phase B brief 明确标注的"退化温床范式"。它在 Phase D 后应大幅缩减（scout 逻辑已迁入 `agent.py`），但实际行数未减。可能是死代码残留。

**修复方案**：开发者审查 `scout_reply.py`，对比 `agent.py:run_scout_phase()` + `infer_field_semantics()`，标出重复 / 死路径。预期可删 300-400 行。

**优先级**：P1

---

## Finding 4（中）：`refinement.py` 的 `_build_unknown_intent` 是静默降级

```python
# hagoku/manager/refinement.py:237-251
def _build_unknown_intent(self, feedback: str) -> RefinementIntent:
    """LLM 不可达或不理解时的最小兜底。"""
    return RefinementIntent(
        raw_input=feedback,
        refine_type="unknown",
        confidence="low",
        guidance=("💡 我支持以下调整：...")
    )
```

**问题**：当 LLM 返回非 tool_call 且 content 无法 JSON 解析时，返回一个"unknown"意图 + 引导文案。用户不知道 LLM 失败了——这是铁律 7 的灰色地带。

**辩护空间**：这不是"静默继续"——用户会看到引导文案，并被明确告知系统不理解。这更接近路径 3（语义未理解→反馈给用户）。

**修复方案**：在 guidance 文案开头加一句"⚠️ 我暂时未能理解你的意图。"使失败可见。不需要 raise。

**优先级**：P3

---

## Finding 5（中）：`agent_tool_defs.py` 中 `phase_tag` 描述未在 `to_openai()` 输出中体现

**上下文**：PROJECT.md 和 collapse brief 都说"phase_tag 仅 LLM 自己看做参考，不做可见性过滤"。但 `to_openai()` 输出的 tool schema 里 `phase_tag` 没有出现在 description 中——LLM 也看不到哪些工具适合当前关注点。

**影响**：LLM 面对 27+ 工具全集，没有"这个工具在理解字段阶段最有用"这类提示。对于小模型可能增加工具选择困难。

**修复方案**：在 `to_openai()` 序列化每个 tool 的 description 时，追加 `（典型关注点：理解字段）` 后缀。让 LLM 能自行判断哪些工具与当前阶段最相关。

**优先级**：P3

---

## Finding 6（中）：`orchestrator.py` 仍有 688 行 —— 距目标（~200 行）差距大

**承诺**：Phase D brief CO-D4 预估 orchestrator 退化为 ~200 行。

**事实**：688 行。

**修复方案**：这可能大部分是 pipeline 编排 + 事件 emit 的合理代码。开发者需要审计是否有 Phase D 前的"阶段切换 if-else"残留。不急于强行缩短，但需对账。

**优先级**：P3

---

## Finding 7（低）：`prompt.md` 参考长度不一致

PROJECT.md §提示词写作规范说"prompt.md 在 2026-06-12 重构后为 ~500 字节"。

实际 `prompt.md` 文件 3166 字节、74 行。

**修复方案**：PROJECT.md 数字修正为当前事实。可能 500 字节是 6/12 的状态，之后又补了记忆工具段和推理链路段。

**优先级**：P3

---

## 审计通过项（无问题）

| 检查项 | 结果 |
|--------|------|
| `grep -rn "from hagoku.agents.scout\|cleaner\|analyst\|reporter" hagoku/` | ✅ 0 命中 |
| `grep -rn "from hagoku.kb" hagoku/` | ✅ 0 命中 |
| `grep -rn "crewai" hagoku/ pyproject.toml` | ✅ 0 命中 |
| `pytest tests/test_doctrine_compliance.py` | ✅ 14 passed |
| `pytest tests/test_product/test_information_arrival.py` | ✅ 15 passed |
| `pytest` 全套 | ✅ 601 passed, 0 failures |
| 铁律 7 在主路径 (`agent.py`) | ✅ 所有 except → raise RuntimeError |
| `to_messages_for_llm()` 在 `agent.py:assess()` / `run_step()` | ✅ 正确使用 |
| `route_to` 阶段切换 LLM 化 | ✅ `prompt.md` 明确声明，`agent.py` 机械执行 |
| 4 关注点 prompt 结构 | ✅ 清晰，无预设业务结论 |
| 旧 agent 目录物理删除 | ✅ scout/cleaner/analyst/reporter 均不存在 |

---

## 修复优先级汇总

| 优先级 | Finding | 动作 | 估工 |
|--------|---------|------|------|
| **P1** | #1 build_messages fallback | 删 else 分支，改 raise | 15 min |
| **P1** | #3 scout_reply.py 死代码 | 审计 + 删减 | 2-4h |
| **P2** | #1 辅助 LLM 白名单标注 | 加 `# EXEMPT` 注释 + pre-commit 白名单 | 30 min |
| **P2** | #2 pipeline_helpers 铁律 7 | 加豁免注释 | 5 min |
| **P2** | #1 reply_handlers 摘要重写 | 迁移到 `to_messages_for_llm` 或标注 | 1h |
| **P3** | #4 unknown_intent 文案 | 加 ⚠️ 前缀 | 5 min |
| **P3** | #5 phase_tag 注入 tool description | `to_openai()` 追加后缀 | 30 min |
| **P3** | #6 orchestrator 行数对账 | 审计死代码 | 1-2h |
| **P3** | #7 prompt.md 长度描述 | PROJECT.md 数字修正 | 5 min |

---

## 转发开发者时的注意事项

1. **P1 项必须修完才能进 Phase E**——否则"物理唯一入口"的架构承诺是空话
2. **P2 项本周处理**——标注 + 小改，不影响功能
3. **P3 项可排入下周**——改善质量但不阻塞
4. 修复后三组测试必跑：
   ```bash
   .venv/bin/python -m pytest tests/test_doctrine_compliance.py -q
   .venv/bin/python -m pytest tests/test_product/test_information_arrival.py -q
   .venv/bin/python -m pytest --tb=short -q
   ```
