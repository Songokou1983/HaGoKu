# 一次性执行协议（Analyst 二段化 + 控制通道全面修复）

> **文档定位**：实施 AI 执行 `2026-06-07-analyst-and-routing-brief.md` 的**操作手册**。
>
> 与之前 brief 的差异：**无中途审核，10 commit 一次性交付**。本文档定义在此模式下的纪律、自检流程、停下时机、最终交付物。
>
> 本文档与 brief 配套使用：brief 说"做什么"，本文档说"怎么做才合规"。

---

## §0 执行模式声明

| 维度 | 之前 (channel-hardening) | 本次 (analyst-and-routing) |
|------|-------------------------|---------------------------|
| 审核节奏 | 每 commit 后人工审核 | **无中途审核，10 commit 一次性交付** |
| 风险 | 单 commit 错只损 1 任务 | 单 commit 错会污染后续任务 |
| 实施方责任 | 完成任务即可 | **每任务完成必须自检全绿才能进下一个** |
| 停下时机 | 等待审核反馈 | **触发 §B 任一条立刻停**（详见下文） |

**核心约束**：本次没人帮你拦错。你的诚信契约 = 唯一防线。

---

## §1 必读文档（按顺序读，缺一不可）

按顺序读完后才动手。读完后在第一条回复中确认"已读完 X 份文档"。

1. `docs/plans/2026-06-07-channel-hardening-brief.md` —— 工作流契约 + 铁律 + 自检模板（继承）
2. `docs/plans/2026-06-07-analyst-and-routing-brief.md` —— **本次的真 brief**（10 任务详细规范）
3. `docs/plans/2026-06-07-analyst-two-phase-brief.md` —— **已作废**，仅读 banner 知道为什么作废，**不要执行其内容**
4. CH-7-fixup commit body —— `git show $(git log --grep="CH-7-fixup" -n 1 --format=%H)`，找到自加的 3 条诚信契约

读完后回复格式：

```
已读完 4 份文档：
- channel-hardening-brief.md：<一句话总结工作流契约>
- analyst-and-routing-brief.md：<一句话总结 A/B/C 三系列依赖关系>
- analyst-two-phase-brief.md（作废）：<一句话说作废原因>
- CH-7-fixup：<列出自加的 3 条诚信契约>

继承的 3 条诚信契约：
1. <原文>
2. <原文>
3. <原文>

我将按 brief §6 依赖图执行 10 任务，每任务完成自检全绿才进下一个，触发本协议 §B 任一条立刻停。
准备就绪，等待 go 信号开始 A-1。
```

**不要在第一条回复中开始任何任务**。

---

## §2 执行顺序（严格按此，不许跳）

```
A-1 → A-2 → A-3 → B-1 → B-2 → B-3 → A-4 → C-1 → A-5 → C-2
```

**为什么这个顺序**：
- A-1 是基础（LLM 失明修复），所有后续依赖
- A-2/A-3 实现 Analyst 核心行为
- B 系列在 A-3 后做（同模式扩展）
- A-4 prompt 重写依赖 A-1~A-3 行为就位
- C-1 契约升级依赖 A-3 + B 系列实现完成
- A-5 死代码清理放在 C-1 之后（确认无回归才删）
- C-2 E2E 冒烟最后做（验全链路）

**不许并行，不许跳过，不许调换顺序**。任何调换 = 违反 brief。

---

## §3 每任务的执行循环（9 步机械化，不许偷工）

对每个任务 `[X-N]`：

### Step 1：读 brief 对应章节
打开 `docs/plans/2026-06-07-analyst-and-routing-brief.md` §2 对应小节，读完"根因 / 改动范围 / 实现要点 / 验收 / 红线"全部 5 部分。

### Step 2：调研先行（仅 A-5 / B-1 / B-2 / B-3 强制）
对这 4 个任务，brief 列出了"调研先行"步骤。必须先跑调研命令，**输出贴到 commit body**，然后才决定是否进入实现。

#### A-5 调研命令
```bash
grep -rn "AnalystAgent.*\.begin\|AnalystAgent.*\.respond\|AnalystAgent.*\.run\b" hagoku/ tests/ scripts/ hagoku_web/
grep -rn "_analyst_agent\.begin\|_analyst_agent\.respond\|_analyst_agent\.run\b" hagoku/ tests/
python -c "
import ast, pathlib
for f in pathlib.Path('hagoku').rglob('*.py'):
    try:
        tree = ast.parse(f.read_text(encoding='utf-8'))
    except SyntaxError:
        continue
    for n in ast.walk(tree):
        if isinstance(n, ast.Attribute) and n.attr in ('begin','respond','run'):
            if 'analyst' in str(f).lower():
                print(f, n.lineno, n.attr)
"
```

#### B-1/B-2/B-3 调研命令
```bash
# 替换 <agent> 为 scout / cleaner / reporter
grep -rn "agent_tools\.dispatch\|_agt\.dispatch" hagoku/agents/<agent>/ hagoku/manager/llm_dispatch/*<agent>* 2>&1
```

**调研结果决定 Option A 还是 Option B**（B-2/B-3 见 brief §2）。

### Step 3：实现
按 brief "改动范围"严格圈定文件。**禁止越界**。

### Step 4：写新测试
按 brief "验收"列出的测试，**全部写完**才能进 Step 5。

### Step 5：自检三组 pytest（必须全绿）
```bash
.venv/bin/python -m pytest tests/test_doctrine_compliance.py -q --tb=no | tail -3
.venv/bin/python -m pytest tests/test_product/test_information_arrival.py -q --tb=no | tail -3
.venv/bin/python -m pytest -q --tb=no | tail -3
```

**任一非全绿 → 不许 commit，先修**。修不动 → §B 触发，停下。

### Step 6：grep 反向断言
按 brief 任务列出的反向 grep（如 A-5 的 `grep "生成报告\|继续分析\|结束分析"` 应空）跑一遍，输出贴 commit body。

### Step 7：写 commit body
严格按 brief §5 模板填，**所有数字 / grep 输出当次实测**。继承的 3 条诚信契约逐条遵守。

### Step 8：commit
```bash
git add -A
git commit -m "<按 brief §5 模板填>"
git log -n 1 --stat | head -20  # 自验 diff 范围
```

**diff 越界** → 立刻 `git reset --soft HEAD~1` 收回，回 Step 3 缩范围。

### Step 9：进下一个任务
回到 Step 1。

---

## §4 全局诚信契约（继承 CH-7-fixup，本次强制）

每个 commit body 中**所有事实断言**都必须可被 shell 命令复现：

### 契约 1：文件名 / grep / ls 类断言须有 shell 实测证据
- **反例**：body 写"`direct_llm_dialog*.py 不存在`"但实际存在
- **正例**：body 必须贴 `ls tests/direct_llm_dialog* 2>&1` 真实输出

### 契约 2：数字必须当次实测，禁止抄写
- **反例**：A-2 body 抄 A-1 的 `494 passed`
- **正例**：每次 commit 前重跑 `pytest --tb=no -q | tail -3`，贴当次输出

### 契约 3：否定断言（不存在 / 空 / 无）须两种工具交叉验证
- **反例**：仅用 shell glob `ls foo*` 返回 exit 2 就说"不存在"（可能是 glob failure 而非 absence）
- **正例**：`find . -name "foo*" -type f` + `ls -la foo*` 双验

---

## §A 死代码清理特殊条款（A-5 专用）

A-5 是高风险任务。**触发以下任一条立刻停**：

1. 调研命令输出含 `AnalystAgent.begin` / `.respond` / `.run` 任一 caller（除 `agent.py` 内自调用）
2. `_analyst_agent.begin` / `.respond` / `.run` 在任何文件出现（除 `agent.py`）
3. AST 双验找到调用点

触发任一 → **立刻停**，跳到 §B 触发点 7 报告。**不许强删**。

---

## §B 必须停下回报架构审核方的 9 种情形

任一触发 → **立刻停止后续任务**，把当前进度（已 commit 任务 + 触发点详情）写到 `docs/plans/PROGRESS_2026-06-07.md`，等待人工。

### 继承 channel-hardening-brief §7 的 5 种
1. 发现 brief 描述与代码事实矛盾
2. 任务依赖关系实际不成立
3. brief 实现某条会破坏现有契约测试
4. 遇到 brief 未涵盖的设计抉择
5. 不确定是否越界 brief 范围

### 本 brief 新增 4 种
6. A-2 书面概括化用现有 prompt 工程难以稳定产出三要素结构
7. A-5 调研发现死代码 caller
8. B-1 Scout 跨阶段跳转（`route_to(reporter)` 跳过 Cleaner/Analyst）是否允许
9. B-2/B-3 调研发现 Cleaner/Reporter 实际有 LLM 工具入口（与 brief §1.4.2 假设不符）

### 禁止行为
- 看到 §B 触发点了还硬上
- 自己改 brief 范围"绕过"问题
- 用 `# TODO` / `# FIXME` 标记后跳过任务

---

## §C 最终交付物清单（10 任务全部完成后给我）

完成 C-2 后，**不要继续做其他事**。回复以下结构化报告：

```
# 一次性执行报告

## 全 10 commit 列表
$ git log -n 11 --oneline | head -11
<贴输出>

## 自检三组实测（最终态）
$ .venv/bin/python -m pytest tests/test_doctrine_compliance.py -q --tb=no | tail -3
<贴输出>
$ .venv/bin/python -m pytest tests/test_product/test_information_arrival.py -q --tb=no | tail -3
<贴输出>
$ .venv/bin/python -m pytest -q --tb=no | tail -3
<贴输出>

## 关键指标对比
- Analyst agent.py 行数：执行前 483 → 执行后 <M>（A-5 应减少 ≈230 行）
- 总测试数：执行前 494 → 执行后 <N>（应 ≥ 494 + 本 brief 新增测试数）

## C-2 真 LLM 冒烟证据
- dump 文件路径：<path>
- 关键 LLM 调用工具名：<list>

## 风险与未尽事项
- B-2/B-3 是否被标记为 Option B（schema-only）：<是/否 + 原因>
- A-5 死代码删除调研结果：<grep + AST 输出粘贴>
- 任何 §B 触发但绕过的情形：<必须诚实报告，不报告 = 违反诚信契约 R10>

## 自加契约遵守自检
- 契约 1（实测证据）：10 commit body 是否全部含 shell 输出？
- 契约 2（数字不抄）：每 commit pytest 数字是否当次实测？
- 契约 3（双工具否定）：所有"不存在 / 空"断言是否双工具验证？
```

---

## §D 反规则（违反任一 = 整轮交付被退回）

| # | 反规则 | 理由 |
|---|--------|------|
| R1 | 把 10 个 commit 合并成 1-2 个 | 单职责 + 审核可追溯 |
| R2 | 跳过依赖顺序（如先做 A-3 再做 A-1） | 基础未就位会污染后续 |
| R3 | 自检 pytest 未全绿就 commit | 诚信契约 |
| R4 | 调研发现死代码 caller 仍强删 | §A 红线 |
| R5 | 触发 §B 任一条不停下 | 工程纪律 |
| R6 | commit body 数字抄写不实测 | 契约 2 |
| R7 | 否定断言单工具验证 | 契约 3 |
| R8 | 修改 brief 文件（除 PROGRESS 报告） | 实施方无权改 brief |
| R9 | 用 `skip` / `xfail strict=False` 隐藏 C-1 盲点 | C-1 红线 |
| R10 | 在 §C 报告中隐瞒任何 §B 触发情形 | 致命诚信问题 |

---

**协议出具时间**：2026-06-07
**协议出具方**：Cascade（架构审核方）
**对应 brief**：`2026-06-07-analyst-and-routing-brief.md`
**执行模式**：一次性 10 commit 无中途审核
