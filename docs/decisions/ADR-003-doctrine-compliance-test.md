# ADR-003：机器化 doctrine 守门测试

- **日期**：2026-05-28
- **状态**：✅ 已落地
- **相关律 / 铁律**：铁律 1（零硬编码）、铁律 2（LLM 失败的唯一合法路径）、刹车 4（信息抵达正向断言）

## 背景

项目所有者反复观察到：**AI 实现者每次进入仓库，都倾向于把已删除的硬编码再次加回来。删了又出现，出现又删——死循环**。

诊断（详见 `CLAUDE.md §「常见错误模式」`）：

1. 哲学是文档，硬编码是代码——**不对称**。CI 不报警，code review 靠人脑，AI 实现者赢
2. AI 进仓库时无记忆，每次重新违反规则
3. 测试不绿时 AI 本能加规则让它绿；LLM 失败时 AI 本能加 except 兜底
4. 哲学缺「失败合法路径」时，实现者只能选「报错给用户」（UX 灾难）或「偷偷加兜底」（哲学违反）

文档级口号 + 人工审查显然守不住。

## 决策

写一份机器化守门测试 `tests/test_doctrine_compliance.py`，把哲学变成**可执行的断言**。每个 PR 提交前必须跑过此文件。

7 条守门：

| # | 守门 | 抓什么 |
|---|------|--------|
| 1 | 业务关键词字面量集合 | `["收入", "营收", "销售额", ...]` 这种 list/tuple/set 中同时含 ≥2 个业务关键词 |
| 2 | 中文语义正则分支 | `re.search(r"收入|营收|销售", text)` 这种带 `|` 的中文短语正则 |
| 3 | 中文 if-elif 分类链 | `if x == "预测" elif x == "对比" elif x == "趋势"`（≥3 分支） |
| 4 | 伪 LLM 函数 | 函数名 `_infer_/_detect_/_classify_/_understand_/_recognize_/_interpret_` 但函数体内无 LLM 调用标记 |
| 5 | LLM except 静默吞 | LLM 调用 except 块直接 `return [] / return None` 而无 `raise` / 未理解信号 |
| Meta-1 | 受检文件清单非空 | 元测试，确保扫描配置没坏 |
| Meta-2 | 中文正则探测器自检 | 元测试，确保守门 2 真的会触发 |

并设立**历史债务白名单** `_KNOWN_LLM_EXCEPT_VIOLATIONS`（详见 [ADR-004](ADR-004-known-llm-except-violations-whitelist.md)）。

## 替代方案

| 方案 | 否决理由 |
|------|---------|
| 仅靠文档约束（PROJECT.md / CLAUDE.md） | 已被证伪——文档没有强制力，AI 实现者反复违反 |
| 仅靠 code review（人工） | 不可扩展；reviewer 也会疲劳；新 reviewer 不知道历史 |
| 用静态分析工具（pylint / ruff 自定义规则） | 对中文/语义判断模式识别能力差；维护成本高于自写 AST 检查 |
| 让 LLM 审 PR diff（agent based） | 本身可能产生硬编码；不可重现；成本高 |

## 后果

**正面**：

- 哲学变成 CI 红线，AI 实现者无法绕过
- 上线时直接抓出 5 处历史违规（详见 ADR-004），证明工具有效
- 新增违规会立即被守门 5 拦下，**死循环被打破**
- 提供给 AI 实现者「提交前必跑」的明确行动指引

**负面 / 待办**：

- 守门是**启发式**，硬编码的伪装无穷尽——只能拦最常见的 4-5 类
- 守门 5 的 LLM 调用上下文判定基于字符串匹配 (`chat.completions.create` 等)，新增 LLM 客户端工厂时需更新 `_LLM_CALL_HINT_LINES`
- 业务关键词 `_BUSINESS_KEYWORDS` 列表是手工维护的——遗漏新业务概念时需人工补充

**影响范围**：

- 新建：`tests/test_doctrine_compliance.py`
- 文档：`CLAUDE.md §「铁律 3 提交前自检」`、`PROJECT.md §「代码层合法动作清单」`
- 流程：`docs/prompts/dev-task-briefing.md`（场景 A 的"提交前必跑"段）

## 引用

- 测试位置：`tests/test_doctrine_compliance.py`
- 相关 ADR：[ADR-004](ADR-004-known-llm-except-violations-whitelist.md)（白名单管理）
- 验证方式：`pytest tests/test_doctrine_compliance.py -v` → 7 passed
