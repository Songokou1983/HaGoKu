 HaGoKu — 项目描述

## 愿景

**用数学的力量，挖出数据背后真正的信息。**

很多数据分析工具停留在"看"的层面——画好看的图、堆描述性统计、做漂亮的仪表盘。这些有用，但不够。可视化能让人一眼看到数据的样子，却看不到数据背后的真相。

HaGoKu 要做的是：**透过数字的表象，用严格的数学方法，发现潜藏在数据深处的规律、因果、异常和趋势，然后用人可理解的方式，精准地传达出来。**

### 两层价值

- **吸引力层** — 可视化和呈现。让用户第一眼就被抓住，快速看到关键信息。这是门面，很重要，没有它用户不会走进来。
- **核心价值层** — 数学洞察。因果推断、假设检验、效应量、模型诊断。这是地基，决定用户会不会留下来。没有它，再好看也只是花瓶。

**门面吸引用户走进来，地基让用户留下来。两者缺一不可，但核心价值永远在前。**

精。准。狠。

- **精** — 不堆砌信息，只呈现真正有意义的发现
- **准** — 数学上严格，统计上可靠，结论经得起检验
- **狠** — 直击要害，不绕弯子，说该说的话

---

## 什么不是 HaGoKu

❌ 不是纯可视化工具 — 画图是手段，洞察才是目的
❌ 不是报告排版器 — 好看是加分项，正确是底线
❌ 不是描述性统计汇总器 — 均值和中位数谁都会算
❌ 不是只有门面的花瓶 — 也不能只有地基没有门面

---

## 设计哲学

HaGoKu 的设计围绕四个核心原则构建，每一个决策都能追溯到这四条：

### 1. 专业（Statistical Rigor）

**每个结论都有数学支撑，每个分析都经过检验。**

HaGoKu 的专业体现在"不说没把握的话"：
- 没有统计检验不下结论
- 没有效应量不说差异大小
- 没有置信区间不说估计可靠性
- 观测数据不声称因果关系

这不是保守，是严谨。专业意味着知道边界在哪里，清楚什么时候结论是可靠的，什么时候只是猜测。

对应的设计实现：
- Statistical Guardrails 三级体系（强制/警告/建议）
- 每个 Agent 都有降级策略（失败一个工具 → 尝试另一个 → 降级到保守方案）
- 统计假设检验自动前置，不满足假设时自动切换方法（如非正态时 t 检验 → Mann-Whitney U）
- 所有错误消息都翻译成用户能理解的建议，而不是暴露内部错误

### 2. 轻量（Lightweight by Default）

**少假设多适配 — 不强求用户用专业词汇，不因配置复杂而卡住。**

HaGoKu 拒绝"预设了一堆，结果一不匹配就跳错"的工具哲学：
- 默认配置就能工作，不需要调参
- 口语化输入 → 自动映射到标准意图
- 任何步骤失败 → 降级到保守方案，继续跑
- 不认识用户输入 → 探索性分析兜底，而不是报错

对应的设计实现：
- Manager LLM 主导 + 规则兜底：LLM 理解意图并制定策略，规则在 LLM 失败时兜底
- QueryParser 口语化映射：把"效果好不好"翻译成"是否有显著差异"
- 所有 Agent 的 run() 方法都有 try/except 包裹，失败不崩溃
- Orchestrator 的 df_clean=None 检查：优先用清洗后数据，清洗失败则回退原始数据
- config.from_yaml() / ensure_work_dir() 都有异常降级，不因配置/权限问题阻断分析

### 3. 连续性（Continuity）

**一次分析的结果成为下一次的起点，记忆不丢失。**

HaGoKu 把每次分析看作数据资产，而不是一次性事件：
- 所有分析结果存入 SQLite，永久可查
- 字段语义确认后记忆化，下次分析自动应用
- 清洗后数据保留原始版本，结论可追溯
- 分析报告链接到对应数据和运行记录

对应的设计实现：
- 项目制管理（每次分析都在项目上下文内）
- schema.yaml 持久化字段语义，避免重复确认
- cleaned.parquet + raw.parquet 双版本存储
- runs/ 目录包含完整的事件日志和元数据

### 4. 情绪价值（Emotional Intelligence）

**分析结果不只是数字，要让人有收获感。**

HaGoKu 的 Agent 不仅仅是冷静地报告结果，而是理解用户的心态。Agent 通过提示词获得情感基调指引，在交互中自主判断情境，自然地表达——不是照搬话术，而是真正理解用户此刻需要什么。

**情感基调指引**（Agent 自主生成具体措辞，以下为方向）：

| 情境 | 基调 | 方向 |
|------|------|------|
| 有显著发现 | 肯定、鼓励 | 让用户感到有收获，数据确实在说话 |
| 没有显著发现 | 安慰、正面化 | 让用户知道零结果也有价值，排除了可能性 |
| 数据质量差 | 给予安全感 | 让用户知道你会谨慎处理，结论会标注限制 |
| 数据质量好 | 给予信心 | 让用户知道可以进行深入分析 |
| 遇到交互限制 | 透明告知 | 让用户知道为什么停下来，下一步怎么做 |

**设计约束**（流程层面，写死）：
- Guardrails：违规消息从"统计学家视角"翻译为"用户视角"（如"VIF 超标"→"某些列信息太相似"）
- 护栏报告：违规级别命名从"强制级违规/警告/建议"改为"需要关注/注意/供参考"
- 任何 Agent 暂停交互时，必须告知用户原因和下一步选项

---

## 什么是 HaGoKu

✅ **挖掘机** — 从数据中挖掘深层信息，不是浮在表面
✅ **审判官** — 每个结论必须经过统计检验，不靠猜
✅ **翻译官** — 把数学语言翻译成人话，但不失真
✅ **守门人** — 区分因果和相关，区分显著和噪声，区分信号和运气

---

## 用户模式 — 对的人给对的体验

**设计原则：功能可以全，但入口必须简单。** 不因为设计全面就让新用户被复杂性吓跑。

HaGoKu 提供三种模式，从"一键出报告"到"全程可控"，用户按需选择，随时可切换。

### ⚡ 快速模式 — 给懒人和新手

**一句话：扔数据，拿结果。**

```bash
hagokyu quick sales.csv
```

就这样。不用指定查询，不用确认字段，不用选模板。HaGoKu 自动：
- 推断字段含义（不问，用最佳猜测）
- 自动选择分析方向（数据画像 + 关键发现 + 异常检测）
- 默认 HTML 报告
- 纯人话输出（不出现任何公式和 p 值）

**快速模式做什么**：
1. 数据画像 — 这份数据长什么样
2. 关键发现 — 最重要的 3 个发现
3. 异常提醒 — 哪里有问题需要注意
4. 简单建议 — 下一步可以看什么

**快速模式不做什么**：
- 不问用户字段含义（用推断 + 置信度，低的在报告里标注"待确认"）
- 不做深度建模（只做描述性统计 + 基础检验）
- 不展示数学细节（`--math plain` 锁死）
- 不提供交互决策点

**快速模式报告基调**（具体格式由 Reporter 自主生成，以下为内容方向）：
- 数据画像 — 这份数据长什么样
- 关键发现 — 最重要的 3 个发现
- 异常提醒 — 哪里有问题需要注意
- 简单建议 — 下一步可以看什么

### 📋 普通模式 — 平衡，大多数人的选择

**一句话：说清楚你要分析什么，其他交给 HaGoKu。**

```bash
hagokyu run sales.csv --query "广告投入对销售有没有影响"
```

**普通模式做什么**：
- 加载数据后，Scout 会问不确定的字段含义（只问推断不出来的）
- Manager 自动制定分析计划，展示给用户确认
- 全自动执行 4 Agent 流水线
- 关键节点可介入（R² 太低时问用户要不要换模型）
- 报告人话为主，关键结论附数学证据

**普通模式的交互点**（流程强制互动写死触发条件，参与式互动由 Agent 自主发起）：

| 互动类型 | 触发方式 | 说明 |
|----------|----------|------|
| 字段确认（流程强制） | Scout 遇到中/低置信度字段时 block 看板 | 用户必须确认才能继续 |
| 清洗确认（流程强制） | Cleaner 清洗影响 > 10% 数据时 block 看板 | 用户必须确认才能继续 |
| 探索邀请（参与式） | Agent 自主判断时机，通过 block 暂停 | Agent 发现有趣模式时主动分享，邀请用户选择方向 |
| 质量反馈（透明性） | Agent 执行过程中自动发出事件 | 不需要用户操作，但让用户安心 |

**报告风格**：人话结论 + 关键数学证据，详细程度适中

### 🔬 资深模式 — 给专业人士，全程可控

**一句话：每一步都由你决定，HaGoKu 是你的工具不是你的老板。**

```bash
hagokyu run sales.csv --query "广告对销售的因果效应" --mode expert
```

**资深模式做什么**：
- Scout 对每个字段都要求确认或补充
- Manager 只提建议，所有决策由用户拍板
- 每个工具调用前展示参数，用户可修改
- 每个分析结果出来后可追问、调整、补充
- 报告完全可定制，用户给模板也行

**资深模式的交互点**（全面，每个都可跳过。Agent 通过看板 blocked 状态暂停，用户确认后 unblock 继续）：

| 互动类型 | 用户可控 |
|----------|----------|
| 字段语义 | 逐列确认，补充描述、单位、角色 |
| 分析计划 | 编辑计划：增删步骤、指定方法、设定阈值 |
| 清洗策略 | 每个清洗操作确认：缺失怎么填、异常怎么处理 |
| 分析方法 | Agent 展示选择的方法和理由，用户可建议调整 |
| 模型参数 | 用户可指定参数，Agent 执行 |
| 结果审查 | 每个发现可追问：换方法重做、补充检验、调整报告 |
| 报告定制 | 完全控制章节结构、模板、输出格式 |

**报告风格**：完整数学推导 + 方法论 + 诊断详情，`--math rigorous` + `--detail full`

### 三模式对比

| | ⚡ 快速 | 📋 普通 | 🔬 资深 |
|---|---|---|---|
| **适合谁** | 新手、懒人、先看一眼 | 大多数用户 | 数据科学家、分析师 |
| **启动命令** | `hagokyu quick data.csv` | `hagokyu run data.csv --query "..."` | `+ --mode expert` |
| **字段确认** | 不问，自动推断 | 只问推断不出的 | 逐列确认 |
| **分析计划** | 自动，不可控 | 自动生成，确认后执行 | 建议 + 用户编辑 |
| **交互点** | 0 个 | 3-4 个关键点 | 全面，但可跳过 |
| **分析深度** | 画像 + 基础发现 | 深度分析 + 检验 | 完全自定义 |
| **数学展示** | 纯人话 | 人话 + 关键证据 | 完整推导 |
| **报告定制** | 固定格式 | 选模板 + 调参数 | 自定义模板 |
| **执行时间** | 10-30s | 1-3min | 取决于用户 |
| **风险** | 可能猜错字段 | 低 | 低 |

### 模式之间无缝切换

```bash
# 快速模式看一眼，觉得值得深入
hagokyu quick sales.csv
# → 报告末尾提示: "想深入分析？运行: hagokyu run sales.csv --query '...' --mode standard"

# 普通模式跑着跑着想自己控制
# → 交互中输入 "expert" 切换到资深模式

# 资深模式太累，想省心
# → 交互中输入 "auto" 切到普通模式，后续自动跑

# 或者一开始就指定
hagokyu run sales.csv --query "分析趋势" --mode quick     # 强制快速
hagokyu run sales.csv --query "分析趋势" --mode standard   # 默认
hagokyu run sales.csv --query "分析趋势" --mode expert     # 资深
```

### 核心设计约束

1. **快速模式是第一印象** — 必须在 30 秒内出结果，必须零门槛
2. **模式只影响交互量，不影响分析质量** — 快速模式也走统计护栏，只是不展示细节
3. **每个模式都能产出完整结果** — 快速模式不是阉割版，是精选版
4. **向上兼容** — 快速模式的结果是普通模式的子集，普通模式是资深模式的子集
5. **永远有出口** — 任何模式都可以跳过、确认、切换，不会卡住

---

## 核心信念

1. **数据会撒谎，数学不会** — 表面数字可能误导，但严格的统计检验会揭示真相
2. **没有检验的结论不是结论** — 说"有差异"不行，要说"p<0.01，效应量 d=0.82"
3. **描述不是分析** — "销售额下降了 15%"是描述；"销售额下降与广告预算削减显著相关（β=-2.31, p<0.001），而非季节因素（p=0.47）"才是分析
4. **洞察的价值与稀缺性成正比** — 显而易见的发现不值得报告，反直觉的、隐藏的、非线性的才是
5. **呈现是翻译不是装饰** — 报告的目的是让人理解数学真相，不是让人觉得好看

---

## 要解决什么问题

现实中的数据分析，大部分时间花在错误的事情上：

| 症状 | 本质 |
|------|------|
| 用 Excel 画了一下午图，结论是"收入在涨" | 用描述性统计代替深度分析 |
| 报告 50 页，决策者只看 3 页 | 没有区分信号和噪声，堆砌代替精选 |
| "这两个指标看起来有关系" | 没做相关性检验，更没区分因果 |
| "我们做了 A/B 测试，B 更好" | 没检验显著性，可能是随机波动 |
| "模型准确率 95%" | 没做交叉验证，没看混淆矩阵，可能过拟合 |
| 数据清洗随手做了 | 不当的清洗方式悄悄改变了分布，后续分析全部失真 |

**HaGoKu 的存在，就是让这些错误不再发生。**

---

## 角色定义 — 四 Agent + 仲裁器 + Scribe


### Agent 能力架构



每个 Agent 通过**四件套**获得能力，而不是通过写死决策：

| 组件 | 文件 | 作用 | 写死什么 / 不写什么 |
|------|------|------|---------------------|
| **提示词** | `prompt.md` | 角色定义 + 工作原则 + 流程约束 | ✅ 写死：你是谁、你必须遵守什么、你不应该做什么。❌ 不写：具体方法选择、具体话术、决策路径 |
| **项目记忆** | `memory.md` | 项目级经验积累（用户偏好、字段确认历史） | ✅ 写死：格式和结构。❌ 不写：通用方法论（那是知识库的事） |
| **方法经验库** | `knowledge.yaml` + `knowledge.py` | 场景→方法映射（置信度+使用次数+成功/失败） | ✅ 写死：格式和索引结构。❌ 不写：决策规则——知识库是**参考**，Agent 自主判断是否适用 |
| **LLM 自由通道** | 运行时 | 知识库未覆盖的方法，LLM 自主选择 | ✅ 写死：必须用白名单库、必须声明理由、仍受 Guardrails 约束。❌ 不写：具体可选方法列表 |

**四件套的关系**：
- 提示词定义了 Agent 的**身份和边界**（"你是分析师，你拥有这些能力，你必须遵守这些规则"）
- 项目记忆让 Agent 在同一项目内有**连续性**（上次跑过什么、用户偏好什么、字段确认历史）
- 方法经验库让 Agent 有**经验参考**（遇到类似场景时，Scribe 自动注入相关知识，Agent 参考但不盲从）
- LLM 自由通道让 Agent 有**创造力**（知识库没覆盖的方法也能用，只要声明理由、受护栏约束）

**三层方法获取架构**——Agent 选择方法时，同时参考三层信息：

    第一层：工具集（确定性，写死）
      └─ check_assumptions, regression, hypothesis_test, effect_size ...
      └─ 经过验证的、有标准化输出的方法
      └─ Agent 优先使用，因为输出格式有保障

    第二层：方法经验库（经验性，Scribe 注入）
      └─ agent/knowledge.yaml：场景→方法映射
      └─ kb/：领域文章（统计方法指南、业务框架）
      └─ Scribe 在 Agent 启动前自动检索匹配，注入 prompt
      └─ Agent 参考经验，结合当前数据特征判断是否适用

    第三层：LLM 自由发挥（开放通道）
      └─ 知识库也没覆盖的方法，LLM 可以自己选
      └─ 约束：
         ① 必须声明理由："我选择XXX，因为当前数据YYY"
         ② 仍受 Guardrails 约束（必须有检验、有效应量、有置信区间）
         ③ 必须用白名单库（pandas/scipy/statsmodels/pingouin/sklearn）
         ④ 结果标注 method_source: "llm_initiative"
         ⑤ 执行失败时，降级到工具集的保守方法

**三层不是串行**（先查工具→再查知识库→最后自由发挥），而是**并行**的——LLM 在理解数据和问题后，同时参考三层信息，自主选择。工具集是"有保障的快车道"，经验库是"前辈的笔记"，LLM 自己的知识是"创造力通道"。**流程约束方向和底线，不约束能力发挥。**

**Agent 自由发挥的边界**：
- 在职责范围内自主选择方法、决定交互方式和措辞
- 知识库未覆盖的方法也可以选择（LLM 自由通道），但必须声明理由、受护栏约束
- 受提示词中的流程约束和护栏规则限制
- 通过看板 blocked 状态主动暂停与用户互动
- 不在职责范围内的事不做（Scout 不做分析，Analyst 不做清洗）
- **流程约束方向和底线，不约束能力发挥**——约束的是"必须检验、必须有效应量、必须告知用户"，不约束"用什么方法、怎么说"

---

### 仲裁器（原 Manager 总管）— 跨 Agent 综合判断

> **设计变更说明**：原"Manager 总管"已拆解。意图解析归 QueryParser + Scout，计划制定归规则引擎 + LLM 微调，调度归 Scribe + 看板，质量把关归 Guardrails。只保留**跨 Agent 仲裁**作为 Orchestrator 内的仲裁逻辑，不再是独立 Agent。去掉了一个 Agent 的 LLM 开销，让决策更透明、更可审计。

**仲裁器做什么**：

当一个 Agent 的输出需要另一个 Agent 做不同选择，或者输出质量需要综合判断时，仲裁器介入：

```python
class Arbitrator:
    """Orchestrator 内的仲裁逻辑 - 规则优先，LLM 兜底"""

    def arbitrate(self, agent_output, context, guardrails_results):
        # 1. Guardrails 强制违规 → 阻止输出
        if any(r.severity == "mandatory" and not r.passed for r in guardrails_results):
            return Arbitration(action="block", reason="Guardrails 强制违规")
        # 2. 规则可判断的场景
        rule_result = self._rule_arbitrate(agent_output, context)
        if rule_result is not None:
            return rule_result
        # 3. 规则判断不了 → LLM 仲裁（极少触发）
        return self._llm_arbitrate(agent_output, context)

    def _rule_arbitrate(self, output, context):
        # R² 过低 + 全不显著
        if output.r_squared and output.r_squared < 0.1:
            if all(p > 0.05 for p in output.p_values):
                return Arbitration(action="accept_zero", reason="R²<0.1且全不显著，接受零结果")
        # 清洗影响大
        if hasattr(output, 'impact_rate') and output.impact_rate > 0.1:
            return Arbitration(action="block", reason="清洗影响>10%，等用户确认")
        return None  # 规则无法判断
```

**仲裁规则完整表**：

| 场景 | 条件 | 仲裁结果 |
|------|------|----------|
| R² 过低 | R² < 0.1 且所有 p > 0.05 | 接受零结果，Reporter 强调"未发现显著模式" |
| R² 偏低 | 0.1 ≤ R² < 0.3 | 允许输出，标注"解释力有限" |
| 清洗影响大 | impact > 10% | block，等用户确认 |
| Guardrails 强制违规 | 任何 mandatory violation | 阻止输出，要求 Agent 修正 |
| Agent 执行失败 | try/except 捕获 | 降级到保守方案，继续 |
| LLM 调用超时 | timeout | 规则引擎兜底计划 |
| 多重共线性高 | VIF > 10 | 警告，建议删除或合并变量 |

**仲裁器不做的事**：不替 Agent 选方法、不替 Agent 写话术、不替 Agent 决定互动时机。仲裁器只在 Agent 输出不达标或跨 Agent 需要综合判断时介入。

---

### Scout（侦察员）— 理解数据上下文，不猜，问

**职责**：加载数据，理解数据本质，为后续分析提供上下文。**绝不靠猜**——能推断的标注置信度，推断不了的就问用户。

**核心理念**：数据字段名是用户起的，只有用户知道它真正什么意思。Scout 做推断辅助，但最终解释权在用户。

**工具集**：

| 工具 | 功能 | 输出 |
|------|------|------|
| `load_data` | 加载 CSV/Excel/JSON/Parquet/SQL | DataFrame |
| `data_profile` | 数据画像：类型、分布、缺失、唯一值 | DataProfile |
| `infer_semantics` | 推断列语义（置信度标注） | list[ColumnSemantic] |
| `assess_quality` | 数据质量评分（完整性、一致性、时效性） | QualityReport |
| `find_confounders` | 检测潜在混淆变量 | ConfounderReport |
| `read_document` | 解析 PDF/Word 获取背景信息 | str |

**语义推断三层策略**：

```python
class ColumnSemantic:
    column_name: str                    # 原始列名
    inferred_type: SemanticType         # 推断的语义类型
    confidence: float                   # 置信度 0.0 ~ 1.0
    evidence: str                       # 推断依据
    needs_user_input: bool              # 是否需要用户确认

class SemanticType(Enum):
    # 高置信度可自动判断的
    ID = "id"              # 唯一值比例高，无统计意义
    NUMERIC = "numeric"    # 纯数值
    DATETIME = "datetime"  # 可解析为日期时间
    BOOLEAN = "boolean"    # 只有两个值

    # 中等置信度需确认的
    CATEGORICAL = "categorical"  # 有限个离散值
    ORDINAL = "ordinal"          # 有序类别（如：低/中/高）
    CURRENCY = "currency"        # 货币金额（含货币符号或小数位固定）

    # 低置信度必须问用户的
    TARGET = "target"            # 因变量（无法自动确定）
    FEATURE = "feature"          # 自变量（无法自动确定）
    CONTROL = "control"          # 控制变量/混淆变量
    WEIGHT = "weight"            # 权重列
    IGNORE = "ignore"            # 分析时应忽略的列

    # 完全无法推断的
    UNKNOWN = "unknown"          # 需要用户说明
```

**推断策略**（阈值是流程约束，写死；具体如何展示和询问由 LLM 自主决定）：

| 列特征 | 推断结果 | 置信度 | 是否问用户 |
|--------|----------|--------|----------| |
| 100% 唯一值，无重复 | ID | 0.95 | ❌ | |
| 纯数字，连续分布 | NUMERIC | 0.90 | ❌ | |
| 可解析为日期格式 | DATETIME | 0.95 | ❌ | |
| 只有两个值 | BOOLEAN | 0.85 | ❌ | |
| <20 个唯一值，字符串 | CATEGORICAL | 0.70 | ⚠️ 确认是否有序 | |
| 名字含 "price/amount/revenue" | CURRENCY | 0.70 | ⚠️ 确认币种和单位 | |
| 名字含 "group/type/category" | CATEGORICAL | 0.60 | ⚠️ 确认 | |
| 名字含 "score/rating/level" | ORDINAL | 0.50 | ✅ **必须确认排序** | |
| 唯一值少 + 名字无提示 | CATEGORICAL or ORDINAL? | 0.40 | ✅ **必须确认** | |
| 名字含 "target/y/label" | TARGET | 0.50 | ✅ **必须确认** | |
| 名字无任何提示，数值型 | FEATURE or TARGET? | 0.30 | ✅ **必须确认** | |
| 完全看不懂的列名 | UNKNOWN | 0.00 | ✅ **必须问** |

**用户交互流程**（流程约束，具体对话方式由 LLM 自主）：

```
Scout 加载数据 → 自动推断语义 → 向用户展示理解并确认

流程约束（写死）：
1. 高置信度推断（>80%）→ 自动确认，无需打扰用户
2. 中/低置信度推断 → 必须与用户确认，Scout 自主决定用什么方式展示和询问
3. 完全无法推断 → 必须向用户提问
4. 因变量（target）→ 必须用户指定，Scout 不猜
5. 所有确认完成后，Scout 写入记忆，告知用户准备进入下一步
```

Scout 通过看板 blocked 状态暂停等待用户输入，用户确认后 unblock 继续。具体的展示格式、提问方式、措辞由 LLM 根据数据特征和用户模式自主生成。

**用户输入方式**：

1. **交互式** — Scout 自主与用户对话（默认）
2. **配置文件** — 提前定义好 schema.yaml，跳过问答
   ```yaml
   # schema.yaml
   columns:
     id: {semantic: id, ignore: true}
     date: {semantic: datetime}
     revenue: {semantic: target, unit: "万元"}
     region: {semantic: categorical, ordinal: false}
     level: {semantic: ordinal, order: [C, B, A]}
     x1: {semantic: feature, description: "客户满意度评分 1-10"}
     flag: {semantic: ignore}
   target: revenue
   confounders: [region, level]
   ```
3. **全自动** — 跳过所有确认，全用推断结果（加 `--auto` 参数，风险自担）

**关键：Scout 必须产出的上下文信息**

```python
class DataContext:
    # 基础信息
    file_path: str
    n_rows: int
    n_cols: int
    columns: list[ColumnSemantic]    # 每列的语义（经用户确认后的最终版本）

    # 数据质量
    missing_summary: dict            # 每列缺失比例
    duplicate_rate: float
    quality_score: float             # 0-100 综合评分

    # 分析上下文（Scout 的真正价值）
    target: str | None               # 因变量（用户指定，不猜）
    features: list[str]              # 自变量
    confounders: list[str]           # 混淆变量（用户指定 + 自动检测建议）
    time_column: str | None          # 时间维度
    group_columns: list[str]         # 分组维度
    column_descriptions: dict        # {列名: 用户提供的含义描述}
    units: dict                      # {列名: 单位} 如 {"revenue": "万元"}

    # 提示给 Cleaner
    missing_patterns: dict           # MCAR/MAR/MNAR 初步判断
    outlier_candidates: list[str]    # 可能有异常值的列

    # 提示给 Analyst
    variable_roles: dict             # {列名: 角色(target/feature/control/id/time/ignore)}
    suggested_analyses: list[str]    # 推荐的分析方向
    user_constraints: list[str]      # 用户提到的约束和先验知识
```

---

### Cleaner（清洁工）— 统计感知的清洗，每步评估影响

**职责**：清洗数据，但每一步都评估对后续分析的影响，不是闷头干活。

**工具集**：

| 工具 | 功能 | 统计感知 |
|------|------|----------|
| `test_missing_mechanism` | 检验缺失机制 (MCAR/MAR/MNAR) | Little's MCAR 检验 |
| `handle_missing` | 缺失值处理 | 根据机制选策略：MCAR→删除, MAR→多重填补, MNAR→模式混合 |
| `detect_outliers` | 异常值检测 | IQR/Z-score/Isolation Forest，不只标记还分析原因 |
| `handle_outliers` | 异常值处理 | 区分测量误差 vs 真实极端值，分别处理 |
| `validate_types` | 类型校验和转换 | 保留语义（日期格式、编码含义） |
| `check_distribution` | 分布检验 | Shapiro-Wilk, KS 检验 |
| `assess_cleaning_impact` | 评估清洗影响 | 对比清洗前后的分布、统计量变化 |

**关键：Cleaner 必须产出的清洗报告**

```python
class CleaningReport:
    # 清洗操作记录
    operations: list[CleaningOp]    # 每步做了什么

    # 影响评估（核心价值）
    before_stats: DescriptiveStats  # 清洗前统计量
    after_stats: DescriptiveStats   # 清洗后统计量
    distribution_shift: dict        # 每列的分布变化程度
    records_removed: int            # 删除了多少行
    records_imputed: int            # 填补了多少值
    bias_risk: str                  # 清洗引入偏差的风险评估: low/medium/high

class CleaningOp:
    operation: str                  # "drop_missing", "impute_median", "remove_outlier" 等
    columns: list[str]              # 作用的列
    rows_affected: int              # 影响的行数
    rationale: str                  # 为什么这么做（统计依据）
    impact: str                     # 对分布的影响描述
```

**清洗选择原则**（Cleaner 根据数据特征和缺失机制自主判断，以下为方向指引）：

1. **机制先行**：先检验缺失机制（MCAR/MAR/MNAR），根据机制选择策略——MCAR可安全删除或简单填补，MAR优先多重填补，MNAR需模式混合或敏感性分析
2. **保守优先**：不确定的数据宁可保留，不擅改。删除是最后手段
3. **区分异常**：检测到异常值后，进一步分析原因——集中出现的疑似测量误差可删除，分散且与业务关联的疑似真实极端值应保留标记
4. **影响评估**：任何操作后必须评估对分布的影响，影响超过10%数据时必须告知用户
5. **经验参考**：从 knowledge.yaml 中 recall 相似场景的清洗经验作为参考

---

### Analyst（分析师）— HaGoKu 的灵魂

**职责**：用数学方法挖掘数据背后的真相。不做描述性统计汇总，只做真正的分析。

**能力清单**（Analyst 拥有这些能力，根据数据特征和问题上下文自主选择）：

| 能力 | 功能 | 强制产出 |
|------|------|----------|
| `check_assumptions` | 统计假设检验 | 正态性、方差齐性、独立性、线性 |
| `regression` | 回归分析 | 系数+CI+p值+效应量+诊断 |
| `hypothesis_test` | 假设检验 | 检验统计量+p值+效应量+结论 |
| `effect_size` | 效应量计算 | Cohen's d, η², Cramér's V 等 |
| `correlation_analysis` | 相关分析 | 相关系数+CI+p值+偏相关 |
| `model_diagnostics` | 模型诊断 | 残差、VIF、影响点、异方差 |
| `cross_validate` | 交叉验证 | CV分数+混淆矩阵+学习曲线 |
| `multiple_comparison` | 多比较校正 | Bonferroni/BH 校正后 p 值 |
| `interaction_analysis` | 交互效应 | 交互项+简单效应分析 |
| `time_series_decompose` | 时序分解 | 趋势+季节+残差 |

**Analyst 的强制规则（Statistical Guardrails）**：

```python
ANALYST_GUARDRAILS = {
    # 报告前强制
    "must_test_assumptions": True,          # 做检验前先检查假设
    "must_report_effect_size": True,        # 显著性必须配效应量
    "must_report_confidence_interval": True, # 点估计必须配区间估计
    "must_diagnose_model": True,            # 建模后必须做诊断
    "must_correct_multiple_comparisons": True,  # 多次检验自动校正

    # 禁止行为
    "no_conclusion_without_test": True,     # 没检验不许下结论
    "no_causal_claim_from_observational": True,  # 观测数据不许说因果（除非用因果推断方法）
    "no_model_without_diagnostics": True,   # 没诊断不许说模型好

    # 阈值
    "significance_level": 0.05,             # 默认显著性水平
    "vif_threshold": 10.0,                  # 多重共线性预警
    "min_sample_size_ratio": 10,            # 每个自变量至少 10 个样本
}
```

**Analyst 的选择原则**（不给答案，给方向——具体选什么由 LLM 根据数据特征自主判断）：

1. **假设先行**：先检查统计假设（正态性、方差齐性），假设满足优先参数方法，不满足自动切换非参数方法
2. **经验参考**：从 knowledge.yaml 中 recall 相似场景的分析经验作为参考，但不盲从——每次的数据特征可能不同
3. **问题导向**：优先选择能直接回答用户问题的方法，而非最复杂的
4. **控制混淆**：有控制变量时优先回归而非简单相关
5. **校正多重比较**：多次检验时必须校正，选择 Bonferroni（保守）或 BH（宽松）根据情境判断
6. **功效意识**：数据量不足时先告知用户，不硬跑

**关键：Analyst 产出的结构化结果**

```python
class AnalysisResult:
    # 分析类型
    analysis_type: str               # "regression", "hypothesis_test", 等
    question_addressed: str          # 回答了什么问题

    # 核心结果（必须完整）
    test_statistic: float | None     # 检验统计量
    p_value: float | None            # p 值
    effect_size: EffectSize          # 效应量（强制）
    confidence_interval: tuple       # 置信区间（强制）

    # 结论（人话 + 数学双版本）
    conclusion_plain: str            # 人话版："广告投入对收入有显著正向影响"
    conclusion_statistical: str      # 数学版："β=2.31, 95%CI [1.82, 2.80], p<0.001, f²=0.42"

    # 诊断
    assumptions_met: dict            # 假设检验结果
    diagnostics: dict | None         # 模型诊断结果
    limitations: list[str]           # 本分析的局限性

    # 可追溯性
    data_version: str                # 用的哪个清洗后的数据
    tools_used: list[str]            # 用了哪些工具
```

---

### Reporter（报告员）— 翻译真相，先抓住眼球再征服大脑

**职责**：把数学洞察翻译成决策者能理解的内容，同时让人一眼就看到重点。输出可定制——用户可以直接给模板，也可以在预设模板基础上调整。

**双轨产出**：

```python
class ReportSection:
    # 吸引力层 — 3 秒抓住用户
    headline: str                    # 一句话结论："广告每投入1万，收入增加2.3万"
    key_metric: MetricCard | None    # 关键数字卡片
    key_chart: Chart | None          # 核心洞察图

    # 核心价值层 — 深入时看到的真东西
    plain_explanation: str           # 人话解读
    statistical_detail: str          # 数学证据
    limitations: str                 # 局限性说明
    evidence_trace: str              # 可追溯: "→ regression β=2.31 p<0.001"
```

**输出定制 — 用户掌控报告长什么样**

用户对报告的定制分三个层级，从轻到重：

#### 层级 1：参数调整（最轻，改几个选项）

```bash
# 选择预设模板
hagokyu run --data sales.csv --query "分析趋势" --template business_analysis

# 选择输出格式
hagokyu run --data sales.csv --query "分析趋势" --output html
hagokyu run --data sales.csv --query "分析趋势" --output pdf
hagokyu run --data sales.csv --query "分析趋势" --output markdown

# 控制详细程度
hagokyu run --data sales.csv --query "分析趋势" --detail brief      # 只有核心发现
hagokyu run --data sales.csv --query "分析趋势" --detail standard   # 发现 + 证据
hagokyu run --data sales.csv --query "分析趋势" --detail full       # 完整：发现 + 证据 + 方法论

# 控制数学深度
hagokyu run --data sales.csv --query "分析趋势" --math plain       # 纯人话，不出现公式
hagokyu run --data sales.csv --query "分析趋势" --math mixed       # 人话为主，关键处附数学
hagokyu run --data sales.csv --query "分析趋势" --math rigorous    # 完整数学推导
```

#### 层级 2：配置文件定制（中等，YAML 定义报告结构）

```yaml
# report_config.yaml
template: business_analysis
output:
  format: html
  detail: standard
  math_level: mixed

# 报告结构定制 — 用户决定要哪些章节、顺序如何
sections:
  - type: headline            # 核心发现（必须有，不可删）
    required: true

  - type: metrics             # 指标卡片
    columns: [revenue, growth_rate, ad_roi]

  - type: findings            # 深度发现
    max_findings: 5           # 最多展示5个发现（精！）

  - type: charts              # 图表
    style: business           # business / academic / minimal
    prefer: plotly            # plotly(交互) / matplotlib(静态)
    dpi: 150                  # 静态图分辨率

  - type: methodology         # 方法论说明
    include: true

  - type: appendix            # 附录：完整统计表
    include: true
    collapsed: true           # 默认折叠

# 不需要的章节直接去掉
# 去掉 appendix 就不生成附录
# 去掉 charts 就不生成图表

# 品牌定制
branding:
  title: "Q2 销售分析"
  logo: ./company_logo.png
  primary_color: "#2563EB"
  font: "思源黑体"
```

#### 层级 3：用户自定义模板（最重，直接给 Jinja2 模板）

用户可以写自己的 Jinja2 模板，完全控制报告的每一行：

```jinja2
{# templates/my_company_report.html.j2 #}
<!DOCTYPE html>
<html>
<head>
    <title>{{ branding.title }} — {{ date }}</title>
    <style>
        .finding { border-left: 4px solid {{ branding.primary_color }}; padding: 12px; }
        .metric-card { ... }
    </style>
</head>
<body>
    <h1>{{ branding.title }}</h1>
    <p>{{ date }} | 分析师: HaGoKu</p>

    {# 核心发现 — 用户决定怎么呈现 #}
    <div class="findings">
    {% for finding in report.findings %}
        <div class="finding">
            <h3>{{ finding.headline }}</h3>
            {% if finding.key_chart %}
                {{ finding.key_chart.to_html() }}
            {% endif %}
            <p>{{ finding.plain_explanation }}</p>
            {% if math_level != "plain" %}
                <small class="evidence">{{ finding.statistical_detail }}</small>
            {% endif %}
        </div>
    {% endfor %}
    </div>

    {# 用户自己加的章节 — HaGoKu 模板里没有的 #}
    <div class="action-items">
        <h2>行动建议</h2>
        <p>基于以上发现，建议：</p>
        <ul>
        {% for finding in report.findings if finding.effect_size.magnitude == "large" %}
            <li>{{ finding.actionable_recommendation }}</li>
        {% endfor %}
        </ul>
    </div>

    {# 方法论 — 只在 full 模式显示 #}
    {% if detail_level == "full" %}
    <div class="methodology">
        <h2>方法论</h2>
        <p>样本量: {{ report.metadata.n_rows }}</p>
        <p>检验方法: {{ report.metadata.tests | join(', ') }}</p>
    </div>
    {% endif %}
</body>
</html>
```

使用自定义模板：

```bash
hagokyu run --data sales.csv --query "分析趋势" \
    --template ./templates/my_company_report.html.j2 \
    --template-config ./report_config.yaml
```

**预设模板库**：

| 模板 | 适用场景 | 结构 | 风格 |
|------|----------|------|------|
| `business_analysis` | 商业分析报告 | 发现→指标→图表→建议→方法论 | 简洁商务 |
| `academic` | 学术/研究报告 | 问题→方法→结果→讨论→结论 | 严谨学术 |
| `ab_test` | A/B 测试报告 | 假设→结果→效应量→建议 | 数据驱动 |
| `executive_brief` | 高管简报 | 1页：核心发现+行动建议 | 极简 |
| `data_audit` | 数据审计 | 质量评分→问题清单→清洗建议 | 审计风格 |

**图表原则**：
- 每张图必须承载一个洞察（不是装饰）
- 关键数据点标注（不是让用户自己找）
- 图表标题就是结论（不是"图1: 销售趋势"，而是"Q4广告效应被节日放大87%"）
- 配色服务于理解（红=警示，绿=正向，灰=不显著）
- 用户可选交互式（Plotly）或静态（Matplotlib）

---

## 看板协作机制 — 多 Agent 协调的核心

HaGoKu 使用**项目看板（Kanban）**作为多 Agent 内部协作工具。看板不是附加功能，而是整个协作架构的骨架。

### 看板的三层角色

| 层级 | 角色 | 说明 |
|------|------|------|
| **流程约束** | 铁轨 | 管谁该跑了、谁等谁、任务之间的依赖关系 |
| **互动锚点** | 暂停机制 | Agent 遇到需要用户参与时 block 任务，用户确认后 unblock 继续 |
| **交接记录** | 接力棒 | Agent 完成任务时记录产出，下一个 Agent 从这里接手 |

### 任务链与依赖

```python
# Scribe.init_pipeline() 创建任务链
Scout (ready)          # 第一个运行
  └→ Cleaner (triage)  # 等 Scout 完成自动晋升为 ready
       └→ Analyst (triage)  # 等 Cleaner 完成自动晋升为 ready
            └→ Reporter (triage)  # 等 Analyst 完成自动晋升为 ready
```

- 父任务 complete → `_recompute_ready()` 自动将子任务从 triage 晋升为 ready
- Agent 通过 `claim_task()` 原子操作获取任务，避免并发冲突
- 长任务通过 `heartbeat()` 续期，避免锁过期

### blocked 状态 — 互动的核心机制

```
Agent 执行中自主判断"需要用户参与"
  → scribe.block_task(agent, reason)
  → 看板状态: running → blocked
  → Agent 暂停，向用户展示需要确认/选择的内容
  → 用户确认后
  → scribe.unblock_task(agent)
  → 看板状态: blocked → ready → running（继续执行）
```

**关键设计**：
- **何时 block**：Agent 自主判断（LLM 判断需要用户参与时）
- **block 后做什么**：Agent 自主决定（用什么方式跟用户沟通、展示什么内容）
- **unblock 后继续什么**：Agent 根据用户输入调整后续行为

只有**流程强制互动**写死触发条件（如 Scout 遇到低置信度字段必须 block），**参与式互动**的时机和方式由 Agent 自主决定。

### 看板不做什么

- ❌ 不替 Agent 做方法选择
- ❌ 不替 Agent 写回复话术
- ❌ 不替 Agent 决定互动话术
- ❌ 不硬编码互动触发条件（流程强制互动除外）

看板只保证**该谁上场了**和**何时该暂停**，上场后怎么打是 Agent 的事。
---


### Scribe（记录员）— 后台的隐形引擎

> Scribe 不是 Agent，不和用户对话，不被用户看见。它是确定性逻辑引擎，零 LLM 调用、零 token 消耗。

**四个职责**：

| 职责 | 说明 | 实现方式 |
|------|------|---------|
| ① 流程守护 | 看板状态管理、任务依赖、block/unblock、heartbeat | `kanban.py` 的原子操作 |
| ② 知识调度 | Agent 启动前检索并注入知识（三层知识自动匹配） | 读取 knowledge.yaml + kb/_registry.yaml → 组装注入包 → 填入 prompt |
| ③ 经验记录 | Agent 完成后捕获关键决策和结果，更新 knowledge.yaml | use_count++ / success_count++ / fail_count++ |
| ④ 经验提炼 | 同一场景签名出现 3+ 次成功时，自动生成新条目；LLM 自由发挥成功时也自动提炼 | 场景签名匹配 + 异步写入 |

**Scribe 知识调度流程**（Agent 启动前自动执行）：

1. Scribe 收到任务（看板 ready → Agent claim）
2. Scribe 读取当前 DataContext（数据特征：样本量、变量类型、缺失情况）
3. Scribe 读取 agent/knowledge.yaml，匹配场景签名
4. Scribe 读取 kb/_registry.yaml，匹配 applicable_when
5. Scribe 组装"知识注入包"：
   - 匹配到的方法经验："上次遇到类似场景，用了XX方法，成功6次/失败1次"
   - 相关领域文章摘要："t检验选择指南：独立样本 vs 配对样本的选择逻辑"
   - 失败教训："注意：两组对比不要用Kruskal-Wallis"
6. Scribe 注入到 Agent 的 prompt 中
7. Agent 开始执行，prompt 里已包含相关知识
8. Agent 自主决策：可以采纳经验，也可以不采纳（自主判断是否适用）
9. 执行结束后，Scribe 记录结果，更新 knowledge.yaml

**为什么是 Scribe 注入而不是 Agent 自己查？**
- Agent 自己查意味着每次都要调 LLM 决定"要不要查" → 额外 token 消耗
- Scribe 注入是确定性的：匹配到了就注入，零额外 LLM 调用
- 类比：不要让实习生自己去翻笔记本，而是前辈在开工前把相关笔记递给他

---

### 三层知识架构 — 统一入口

```
┌─────────────────────────────────────────────┐
│           Scribe（知识调度员）                │
│  在 Agent 执行前，自动注入相关知识             │
├──────────┬──────────────┬───────────────────┤
│ 领域知识库 │  方法经验库    │  LLM 自由发挥    │
│ (kb/)    │ (agent/)     │  (runtime)       │
│          │              │                  │
│ 静态     │  动态         │  即时             │
│ 人工维护  │  自动积累      │  LLM 自主        │
│ 教科书   │  笔记本       │  创造力           │
├──────────┼──────────────┼───────────────────┤
│ 统计方法  │  场景→方法    │  任何白名单内的   │
│ 业务框架  │  置信度+次数  │  方法，但需声明   │
│ 行业指标  │  失败教训     │  理由+受护栏约束  │
└──────────┴──────────────┴───────────────────┘
```

**第一层：领域知识库 (kb/)**

- 保持现有结构，继续手写维护
- **新增 `applicable_when` 和 `inject_to` 字段**：

```yaml
# kb/_registry.yaml 里的条目
- title: "t 检验选择指南"
  category: stats
  tags: [t检验, 假设检验]
  summary: "..."
  filename: stats/ttest.md
  applicable_when:      # ← 新增：何时该读这篇
    - "分析师需要做两组对比"
    - "用户问到差异/对比/比较"
  inject_to: [analyst]  # ← 新增：注入给哪个 Agent
```

**第二层：方法经验库 (agent/knowledge.yaml)**

重构为"场景签名 + 方法 + 效果记录"结构，**去重 + 新增失败记录**：

```yaml
knowledge:
- id: "分组对比_非正态_小样本"
  scenario_signature: "分组对比 + 非正态 + 小样本"
  method: "Mann-Whitney U 检验"
  method_code: "scipy.stats.mannwhitneyu"
  confidence: 0.9
  use_count: 7
  success_count: 6       # ← 新增
  fail_count: 1          # ← 新增
  last_used: "2026-05-06"
  notes: "非正态时优于t检验，但效应量需手动计算rank-biserial correlation"

- id: "分组对比_非正态_小样本_failed"
  scenario_signature: "分组对比 + 非正态 + 小样本"
  method: "Kruskal-Wallis"
  fail_reason: "只有两组时Kruskal-Wallis等价于Mann-Whitney U但输出不如后者直观"
  notes: "两组对比不要用Kruskal-Wallis"
```

**第三层：LLM 自由发挥**

不持久化，运行时存在。但 **Scribe 在分析结束后，如果 LLM 自由发挥产生了好的结果，自动提炼并写入第二层**。

---

### 双记忆系统

```
项目记忆（项目文件夹内）          Agent 记忆（Agent 文件夹内）
─────────────────────────        ─────────────────────────
记录"这个项目发生了什么"          记录"这个 Agent 学到了什么"

projects/sales_analysis/          agents/analyst/
├── schema.yaml    ← 字段语义     ├── memory.md    ← 方法运用经验
├── progress.yaml  ← 项目进度     └── knowledge.yaml ← 场景-方法映射
├── results/       ← 分析结果
└── notes.yaml     ← 用户反馈

生命周期：跟随项目                生命周期：跨项目积累
更新者：Scribe                    更新者：Scribe
消费者：Orchestrator、UI          消费者：Scribe（注入prompt）
```

**项目记忆 (progress.yaml)**：

```yaml
project: sales_analysis
created_at: 2026-05-01

milestones:
  - date: 2026-05-01
    event: "首次分析"
    query: "广告投入对销售有没有影响"
    result: "3个显著发现，R²=0.87"
    run_id: "20260501_143052"

user_preferences:
  - key: "preferred_regression_method"
    value: "robust"
    reason: "数据非正态时用户选择稳健回归"
    since: "2026-05-01"

field_decisions:
  - column: "revenue"
    semantic: "target"
    unit: "万元"
    confirmed_by: "user"
    confirmed_at: "2026-05-01"
```

**Agent 记忆 (memory.md)**：

```
# Analyst 方法运用经验

## 已验证的方法选择
- 分组对比 + 非正态 + 小样本 → Mann-Whitney U（成功7次）
- 回归 + 非正态 → 稳健回归（成功4次）
- 多组对比 + 正态 → ANOVA + Tukey HSD（成功3次）

## 失败教训
- 两组对比不要用 Kruskal-Wallis（等价于 Mann-Whitney U 但输出不直观）
- 小样本(n<15)不要做多元回归（自由度不够）

## 用户偏好
- 用户偏好稳健回归（2026-05-01 确认）
- 用户喜欢看到效应量的实际意义解读
```

**怎么保证 Agent 记忆被调用？** 三层保障：

1. **Scribe 主动注入**（最可靠）：Agent 启动前，Scribe 读取 knowledge.yaml，匹配场景签名，注入 prompt。Agent 不需要主动去查。
2. **Prompt 内置提醒**：在 Agent 的 prompt.md 里写一条流程约束——"在决定分析方法前，回顾你的经验记录。如果有匹配的场景签名，优先参考。但每次都要验证当前数据是否满足条件。"
3. **结果校验**：Agent 完成后，Scribe 检查——Agent 用了方法 X，knowledge.yaml 里有没有对应的场景签名？如果有，use_count+1；如果没有且分析成功，Scribe 提炼新条目写入。

**记忆写入规则**：
- ✅ 写入：用户偏好、用户纠正过的字段含义、用户选择的输出风格
- ❌ 不写入：数据特征（每次数据不同）、统计分析结果（存在 SQLite 里了）、临时状态
- 生命周期：项目记忆跟随项目，Agent 记忆跨项目积累

**知识库更新机制**：MVP 阶段领域知识库 (kb/) 纯手写维护，不自动写入。方法经验库 (agent/knowledge.yaml) 由 Scribe 自动维护（use_count/success_count/fail_count 自动更新，新条目需同一场景签名出现 3+ 次成功才写入）。V2 考虑"经验提炼"——从多次分析中自动提取高频模式，但需人工审核后才写入领域知识库。

---

### 降级策略表

| Agent | 失败场景 | 降级方案 | 用户体验 |
|-------|---------|---------|---------|
| Analyst | 回归失败 | 只做描述性统计+效应量估计，标注"未能建立模型" | 报告中说明 |
| Analyst | 假设检验失败 | 报告原始统计量，标注"假设不满足，结论需谨慎" | 报告中标注⚠️ |
| Analyst | LLM 自由发挥失败 | 降级到工具集的保守方法 | 无感知 |
| Cleaner | 填补失败 | 保留缺失值，在报告中标注"缺失值未处理" | 报告中说明 |
| Cleaner | 异常检测失败 | 不处理异常值，标注"未做异常检测" | 报告中说明 |
| Scout | 语义推断失败 | 标记 UNKNOWN | 普通模式 block 等用户确认；快速模式标注"待确认" |
| Manager | LLM 超时 | 用规则引擎兜底计划 | 无感知 |
| Reporter | 模板渲染失败 | 降级到 Markdown 纯文本输出 | 格式简化 |

---

### 用户互动兜底规则

**通用兜底**：任何 Agent 暂停等待用户输入时，必须提供至少一个"交给你决定"的选项。用户选择后，Agent 自主判断并继续。

**快速模式猜错信号检测**：
- 分析完成后，如果 R² 极低（<0.1）或所有 p 值都不显著，Reporter 应在报告末尾提示："本次分析未发现显著规律，这可能是因为字段理解有误。建议用普通模式重新分析：`hagokyu run ... --query '...'`"
- 快速模式的报告应在开头标注："字段含义为自动推断，未经确认。如有疑问请用普通模式。"

**互动预算**：
- 快速模式：0 次互动（严格）
- 普通模式：流程强制 3-4 次 + 参与式最多 2 次 = 总计不超过 6 次
- 资深模式：无限制，但每个都可跳过
- Agent 内部应有计数器，超出预算后不再主动暂停

**模式切换状态管理**：
- 模式切换只影响**后续**决策
- 已经执行的步骤不回滚，但资深模式下用户可以"重做"某个步骤

**用户反馈闭环**：
- 报告末尾增加快速反馈入口："换个方法重做" / "深入分析" / "调整报告"
- 用户反馈写入项目记忆 (progress.yaml)，下次分析时参考"

---

## Statistical Guardrails — 统计护栏

HaGoKu 的安全网，确保分析不犯低级错误。分为三级：

### 强制级（Violation = 阻止输出）

| 规则 | 说明 |
|------|------|
| `no_conclusion_without_test` | 没有统计检验不许下结论 |
| `must_report_effect_size` | 报告显著性必须配效应量 |
| `must_report_ci` | 点估计必须配置信区间 |
| `no_causal_claim_without_method` | 观测数据必须用因果推断方法才能声称因果 |
| `must_diagnose_model` | 建模后必须做残差诊断、VIF 等 |

### 警告级（Violation = 标注警告但允许输出）

| 规则 | 说明 |
|------|------|
| `assumptions_violated` | 统计假设不满足时标注，建议替代方法 |
| `small_sample_size` | 样本量不足时警告，降低结论强度 |
| `high_vif` | 多重共线性超标时警告 |
| `potential_overfitting` | 训练测试差异过大时警告 |
| `cleaning_high_impact` | 清洗操作影响了 >10% 数据时警告 |

### 提示级（Violation = 建议但不过问）

| 规则 | 说明 |
|------|------|
| `suggest_nonlinear` | 残差模式暗示非线性时建议 |
| `suggest_interaction` | 变量间可能存在交互效应时建议 |
| `missing_not_random` | 缺失非随机时建议谨慎处理 |
| `consider_power_analysis` | 建议做功效分析确认样本量足够 |

---

## 数据流与持久化

### 一次分析的数据流

```
原始数据
  │
  ▼ Scout
DataContext + raw.parquet
  │  (数据理解 + 原始数据)
  ▼ Cleaner
CleaningReport + cleaned.parquet
  │  (清洗影响评估 + 清洗后数据)
  ▼ Analyst
list[AnalysisResult] + diagnostics/
  │  (结构化分析结果 + 诊断图)
  ▼ Reporter
Report (Markdown/HTML/PDF)
  │  (吸引力层 + 核心价值层)
  ▼ 用户
```

**数据传递格式**：Parquet 文件 + 元数据 JSON

```python
class DataArtifact:
    artifact_id: str
    file_path: Path              # Parquet 文件
    schema: dict                 # 列名/类型/语义
    metadata: dict               # 行数、生成时间、来源 agent
    lineage: list[str]           # 数据血缘: ["raw" → "cleaned" → "analysis_ready"]
    cleaning_impact: dict | None # 仅 Cleaner 产出时有
```

### 数据持久化 — 分析结果不丢，可持续积累

一次分析完就扔掉？不行。HaGoKu 的分析结果是资产，要存下来、可追溯、可复用。

**存储架构**：

```
~/.hagokyu/                          # HaGoKu 工作目录（可配置）
├── config.yaml                      # 全局配置
├── projects/                        # 按项目组织
│   └── sales_analysis/              # 项目名
│       ├── schema.yaml              # 字段语义定义（用户确认后的）
│       ├── data/                    # 数据制品
│       │   ├── raw_20260501.parquet
│       │   ├── cleaned_20260501.parquet
│       │   └── ...
│       ├── runs/                    # 每次分析运行
│       │   ├── 20260501_143052/     # 运行ID：日期_时间
│       │   │   ├── run_meta.json    # 运行元数据
│       │   │   ├── plan.json        # Manager 的分析计划
│       │   │   ├── events.jsonl     # 完整事件日志
│       │   │   ├── context.json     # Scout 产出的 DataContext
│       │   │   ├── cleaning.json    # Cleaner 产出的 CleaningReport
│       │   │   ├── results/         # Analyst 产出的 AnalysisResult 列表
│       │   │   │   ├── regression_revenue.json
│       │   │   │   ├── ttest_q1_vs_q4.json
│       │   │   │   └── ...
│       │   │   ├── diagnostics/     # 诊断图
│       │   │   │   ├── residual_plot.png
│       │   │   │   └── qq_plot.png
│       │   │   └── output/          # Reporter 产出的报告
│       │   │       ├── report.html
│       │   │       ├── report.pdf
│       │   │       └── charts/      # 报告中的图表
│       │   │           ├── trend.html
│       │   │           └── comparison.html
│       │   └── 20260502_091523/     # 第二次运行
│       │       └── ...
│       └── reports/                 # 最新报告的快捷方式
│           ├── latest.html → runs/20260502_091523/output/report.html
│           └── latest.pdf  → runs/20260502_091523/output/report.pdf
└── hagokyu.db                       # SQLite 元数据库（见下文）
```

### 数据库 — 持续性分析的基础

只用文件不够。HaGoKu 内置 SQLite 元数据库，记录所有历史分析，支持持续性分析。

**为什么用 SQLite**：
- 零配置，单文件，本地优先
- 不需要额外服务
- DuckDB 可直接查询 SQLite
- 未来可迁移到 PostgreSQL（多用户时）

**数据库表结构**：

```sql
-- 项目管理
CREATE TABLE projects (
    id          TEXT PRIMARY KEY,       -- 项目名
    created_at  DATETIME,
    description TEXT,
    data_path   TEXT,                   -- 原始数据路径
    schema_path TEXT                    -- 字段语义定义文件
);

-- 数据源注册（支持多数据源）
CREATE TABLE data_sources (
    id          TEXT PRIMARY KEY,
    project_id  TEXT REFERENCES projects(id),
    name        TEXT,                   -- 数据源名
    type        TEXT,                   -- csv / excel / parquet / sqlite / postgres / mysql / api
    connection  TEXT,                   -- 连接信息（路径/连接串/API URL）
    schema_json TEXT,                   -- 字段语义 JSON
    last_loaded DATETIME,
    row_count   INTEGER,
    quality_score FLOAT
);

-- 分析运行记录
CREATE TABLE runs (
    id          TEXT PRIMARY KEY,       -- 20260501_143052
    project_id  TEXT REFERENCES projects(id),
    query       TEXT,                   -- 用户的原始问题
    plan_json   TEXT,                   -- Manager 的分析计划
    status      TEXT,                   -- running / completed / failed
    started_at  DATETIME,
    completed_at DATETIME,
    duration_ms INTEGER,
    token_count INTEGER,                -- LLM token 消耗
    manager_mode TEXT,                  -- local_weak / cloud / ...
    output_path TEXT                    -- 报告路径
);

-- 分析结果（结构化，可查询）
CREATE TABLE findings (
    id          TEXT PRIMARY KEY,
    run_id      TEXT REFERENCES runs(id),
    analysis_type TEXT,                 -- regression / hypothesis_test / ...
    question    TEXT,                   -- 回答的问题
    conclusion_plain TEXT,              -- 人话结论
    conclusion_statistical TEXT,        -- 数学结论
    p_value     FLOAT,
    effect_size FLOAT,
    effect_type TEXT,                   -- cohen_d / eta_sq / cramers_v / ...
    confidence_interval TEXT,           -- "[1.82, 2.80]"
    significance TEXT,                  -- significant / not_significant / marginal
    created_at  DATETIME
);

-- 数据制品追踪
CREATE TABLE artifacts (
    id          TEXT PRIMARY KEY,
    run_id      TEXT REFERENCES runs(id),
    agent       TEXT,                   -- scout / cleaner / analyst / reporter
    type        TEXT,                   -- parquet / json / html / pdf / png
    file_path   TEXT,
    lineage     TEXT,                   -- JSON: 数据血缘链
    metadata    TEXT,                   -- JSON: 附加元数据
    created_at  DATETIME
);
```

**持续性分析能力**：

```bash
# 查看历史分析
hagokyu history --project sales_analysis
# → 2026-05-01 14:30  "分析趋势"          completed  45s
# → 2026-05-02 09:15  "回归分析"          completed  62s

# 对比两次分析结果
hagokyu diff --run 20260501_143052 --run 20260502_091523
# → 发现1: R² 从 0.87 → 0.91 (新数据后模型提升)
# → 发现2: ad_spend 系数从 2.31 → 2.15 (边际效应递减)

# 基于上次分析继续（复用已清洗数据）
hagokyu run --project sales_analysis --resume --query "加入新数据后重新分析"
# → 跳过 Scout 和 Cleaner，直接用上次清洗后的数据

# 查询历史发现
hagokyu query "所有 p<0.01 的发现"
hagokyu query "revenue 相关的所有分析"
hagokyu query "效应量大于 0.5 的发现"

# 数据源管理
hagokyu source add --name "sales_db" --type postgres --connection "postgresql://..."
hagokyu source add --name "monthly_csv" --type csv --path "./data/202605.csv"
hagokyu source list
hagokyu source profile sales_db      # 对数据源做画像
```

**外部数据库支持（V2）**：

```yaml
# config.yaml — 数据源配置
data_sources:
  # 本地文件（默认）
  - name: sales_csv
    type: csv
    path: ./data/sales.csv

  # SQLite 数据库
  - name: analytics_db
    type: sqlite
    path: ./data/analytics.db

  # PostgreSQL（V2）
  - name: production_db
    type: postgres
    host: localhost
    port: 5432
    database: analytics
    schema: public
    # 只读连接，不写
    readonly: true

  # MySQL（V2）
  - name: warehouse
    type: mysql
    host: 192.168.1.100
    port: 3306
    database: data_warehouse

  # API（V3）
  - name: salesforce
    type: api
    url: https://api.salesforce.com/...
    auth_type: bearer
```

### 输出命名与存放

**命名规则**：

```
{项目名}/{类型}_{日期}.{扩展名}

示例:
sales_analysis/report_20260501.html
sales_analysis/report_20260501.pdf
sales_analysis/cleaned_20260501.parquet
sales_analysis/regression_revenue_20260501.json
```

**用户可自定义输出路径**：

```bash
# 默认：~/.hagokyu/projects/{项目名}/runs/{运行ID}/output/
hagokyu run --data sales.csv --query "分析趋势"

# 指定输出目录
hagokyu run --data sales.csv --query "分析趋势" --output-dir ./my_reports/

# 指定报告文件名
hagokyu run --data sales.csv --query "分析趋势" --output-name "Q2_销售分析"

# 结果：./my_reports/Q2_销售分析.html
```

**配置文件中定义默认输出规则**：

```yaml
# config.yaml
output:
  base_dir: ~/.hagokyu/projects
  naming: "{project}/report_{date}"     # 命名模板
  date_format: "%Y%m%d"
  formats: [html]                       # 默认输出格式
  auto_archive: true                    # 自动归档历史报告
  keep_latest_n: 10                     # 保留最近 10 份报告
```

**输出内容清单** — 每次运行自动生成：

```markdown
# 输出清单 — 20260501_143052

## 报告
- report.html              (128KB)  主报告
- report.pdf               (256KB)  PDF 版本
- charts/trend.html        (12KB)   趋势图（交互式）
- charts/comparison.png    (45KB)   对比图（静态）

## 数据制品
- cleaned.parquet          (2.1MB)  清洗后数据
- results/regression.json  (8KB)    回归分析结果
- results/ttest.json       (4KB)    t 检验结果

## 诊断
- diagnostics/residual.png (18KB)   残差图
- diagnostics/qq.png       (12KB)   Q-Q 图

## 元数据
- run_meta.json            (2KB)    运行元信息
- events.jsonl             (45KB)   完整事件日志
- context.json             (6KB)    数据上下文
- cleaning.json            (3KB)    清洗报告
```

---

## 可观测性

用户坐副驾驶位，全程透明：

### 工作流 — 全局进度
```
🔍 Scout ──── ✅ 完成 (12s)
🧹 Cleaner ── ✅ 完成 (8s)
📊 Analyst ── 🔄 执行中...
📝 Reporter ── ⏳ 等待中
🧠 Manager ── 监控中
```

### 工具流 — 执行细节
```
📊 Analyst:
   │  🔧 check_assumptions(data="cleaned.parquet", test="normality")
   │     → Shapiro-Wilk: revenue p=0.21 ✅, ad_spend p=0.04 ⚠️ 非正态
   │  🔧 regression(target="revenue", features=["ad_spend"], method="robust")
   │     → β=2.31, 95%CI [1.82, 2.80], p<0.001, f²=0.42
   │  🔧 model_diagnostics()
   │     → VIF: 1.2 ✅ | Breusch-Pagan: p=0.34 ✅ | Durbin-Watson: 1.98 ✅
   ✅ 完成 (18s)
```

### 协作流 — Agent 交互
```
Manager ──计划──→ Scout: "加载销售数据，判断变量角色"
Scout ──上下文──→ Manager: "revenue 为因变量，ad_spend 为自变量，season 为混淆变量"
Manager ──计划──→ Cleaner: "清洗缺失值，注意 season 列"
Cleaner ──报告──→ Manager: "清洗完成，影响低 risk，缺失为 MCAR"
Manager ──计划──→ Analyst: "控制 season，做回归，报告效应量"
Analyst ──结果──→ Manager: "R²=0.87, β=2.31 p<0.001 ✅"
Manager ──计划──→ Reporter: "3 个核心发现，强调因果证据"
```

### 数据流 — 数据血缘
```
sales.csv → Scout(raw.parquet) → Cleaner(cleaned.parquet) → Analyst(results/) → Reporter(report.html)
              │                      │                            │
              n=5832, 12列           n=5827, 15列                 R²=0.87
              23 缺失值              5 异常值已处理                3 显著发现
```

---

## 用户场景

### 场景 1：广告投放是否真的有效？

```
输入: 广告支出 + 销售额数据 + "广告投入对销售有没有因果影响？"

❌ 表面功夫的回答:
   "广告支出和销售额呈正相关，相关系数 0.89"

✅ HaGoKu 的回答方向:
   - 控制混淆变量后的因果效应估计（β、CI、p值）
   - 效应量的实际意义（每增加1万广告预算，销售额增加多少）
   - 效应的边界条件（如某些季节被放大、某些条件下不显著）
   - 残差诊断结果（排除其他解释）
   - 具体措辞由 Analyst + Reporter 自主生成
```

### 场景 2：两个产品版本谁更好？

```
输入: A/B 测试数据 + "新版转化率是否显著高于旧版？"

❌ 表面功夫的回答:
   "新版转化率 4.2%，旧版 3.8%，新版更好"

✅ HaGoKu 的回答方向:
   - 统计显著性检验（卡方/t检验 + p值）
   - 效应量的实际意义（Cramér's V 很小 → 差异虽显著但实际意义有限）
   - 置信区间（真实提升幅度的范围）
   - 实际解读（需要多少次曝光才能多获得1次转化）
   - 具体措辞由 Analyst + Reporter 自主生成
```

### 场景 3：异常值该不该删？

```
输入: 含异常值的数据 + "清洗这份数据"

❌ 表面功夫的回答:
   "已删除 5 个异常值，数据清洗完成"

✅ HaGoKu 的回答方向:
   - 异常值存在的统计证据（Grubbs检验等）
   - 异常值原因分析（集中出现→疑似测量误差，分散出现→疑似真实极端值）
   - 分别处理的建议（测量误差可删除，真实极端值保留标记）
   - 清洗影响评估（删除前后的分布变化）
   - 具体措辞和数据由 Cleaner 自主生成
```

---

## 与其他工具的本质区别

| | 传统 BI / 可视化工具 | 通用 AI Agent 框架 | **HaGoKu** |
|---|---|---|---|
| 吸引力 | ✅ 好看 | ⚠️ 一般 | ✅ **好看且有用** |
| 核心产出 | 图表仪表盘 | 文本对话 | **数学洞察** |
| 分析深度 | 描述性统计 | 取决于 prompt | **因果推断 + 假设检验 + 模型诊断** |
| 结论可靠性 | 无保障 | 无保障 | **统计检验兜底** |
| 区分因果和相关 | ❌ | 不一定 | ✅ **设计即考虑** |
| 效应量报告 | ❌ | 不一定 | ✅ **强制** |
| 多比较校正 | ❌ | ❌ | ✅ **自动** |
| 清洗影响评估 | ❌ | ❌ | ✅ **每步评估** |
| 报告原则 | 多多益善 | 自由发挥 | **精、准、狠** |
| 用户留存靠什么 | 新鲜感 | 对话体验 | **真正解决问题** |

---

## 项目结构

**注意**：使用 flat 布局（`hagokyu/` 在项目根），不是 `src/` 布局。

```
hagokyu/                          # 项目根
├── pyproject.toml
├── README.md
├── PROJECT.md                    # 本文件
├── .env.example
├── hagokyu/                     # flat 布局，所有代码在这里
│   ├── __init__.py
│   ├── cli.py                   # CLI 入口
│   ├── config.py                # 全局配置 + Manager 模式
│   ├── orchestrator.py          # 编排器
│   │
│   ├── manager/
│   │   ├── __init__.py
│   │   ├── planner.py           # 分析计划生成
│   │   ├── rule_engine.py       # 规则引擎
│   │   ├── quality_checker.py   # 质量检查
│   │   └── modes.py             # 权重模式定义
│   │
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── scout/               # Scout Agent（独立文件夹）
│   │   │   ├── agent.py
│   │   │   ├── prompt.md
│   │   │   ├── memory.md
│   │   │   └── knowledge.yaml
│   │   ├── cleaner/             # Cleaner Agent（独立文件夹）
│   │   │   ├── agent.py
│   │   │   ├── prompt.md
│   │   │   └── memory.md
│   │   ├── analyst/             # Analyst Agent（独立文件夹）
│   │   │   ├── agent.py
│   │   │   ├── prompt.md
│   │   │   └── memory.md
│   │   ├── reporter/            # Reporter Agent（独立文件夹）
│   │   │   ├── agent.py
│   │   │   ├── prompt.md
│   │   │   └── memory.md
│   │   └── _scribe/             # Scribe Agent（内部记录员）
│   │       └── agent.py
│   │
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── data_io.py           # 数据加载 (Pandas, DuckDB)
│   │   ├── profiling.py         # 数据画像 (ydata-profiling, missingno)
│   │   ├── cleaning.py          # 统计感知清洗 (sklearn, PyOD, Cleanlab)
│   │   ├── validation.py        # 数据验证 (Great Expectations)
│   │   ├── analysis.py          # 统计分析 (Pingouin, Statsmodels)
│   │   ├── diagnostics.py       # 模型诊断 (Statsmodels)
│   │   ├── automl.py            # AutoML (FLAML)
│   │   ├── causal.py            # 因果推断 (DoWhy) [V3]
│   │   ├── visualization.py     # 洞察图 (Plotly, Matplotlib)
│   │   └── reporting.py         # 报告渲染 (Jinja2) + 导出 (Quarto)
│   │
│   ├── guardrails/
│   │   ├── __init__.py
│   │   ├── statistical.py       # 统计护栏核心
│   │   ├── mandatory.py         # 强制级规则
│   │   ├── warnings.py          # 警告级规则
│   │   └── suggestions.py       # 提示级规则
│   │
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── kanban.py            # 项目看板（SQLite）
│   │   ├── project_manager.py   # 项目管理（创建/列表/归档）
│   │   ├── artifact.py          # DataArtifact 定义 + Parquet 管理
│   │   ├── lineage.py           # 数据血缘追踪
│   │   ├── database.py          # SQLite 元数据库
│   │   ├── sources.py           # 数据源管理（文件/DB/API）
│   │   └── output.py            # 输出命名 + 存放路径管理
│   │
│   ├── observability/
│   │   ├── __init__.py
│   │   ├── event_bus.py         # 事件总线
│   │   ├── events.py            # 事件类型定义
│   │   ├── display.py           # 终端实时显示
│   │   └── replay.py            # 执行回放
│   │
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── app.py               # Streamlit 入口
│   │   ├── _pages/              # 页面（Streamlit 要求 _ 前缀）
│   │   ├── components/          # 组件
│   │   └── static/              # 静态资源
│   │
│   └── prompts/
│       ├── manager.yaml
│       ├── scout.yaml
│       ├── cleaner.yaml
│       ├── analyst.yaml
│       └── reporter.yaml
│
├── tests/
│   ├── test_guardrails/
│   ├── test_tools/
│   ├── test_agents/
│   ├── test_storage/
│   └── test_pipeline/
│
└── examples/
    ├── advertising_effect.py
    ├── ab_test_analysis.py
    └── sales_trend.py
```

---

## 交付物

### MVP — 先让灵魂跑起来

- [x] 项目立项
- [ ] Statistical Guardrails 框架（强制级 + 警告级）
- [ ] Analyst 核心能力：回归 + 假设检验 + 效应量 + 模型诊断
- [ ] Cleaner 统计感知清洗：缺失机制检验 + 清洗影响评估
- [ ] Scout 数据上下文理解：语义推断 + 用户确认交互
- [ ] Reporter 双轨输出：吸引力层 + 核心价值层
- [ ] Manager 规则引擎 + 基础调度
- [ ] 项目管理 + SQLite 元数据库 + 输出命名/存放
- [ ] CLI + 终端实时输出
- [ ] 本地 LLM 适配
- [ ] 1 个端到端示例（广告效果分析）

### V2 — 让洞察可见、可持续

- [ ] Streamlit Web UI
- [ ] 可视化：每个检验配诊断图
- [ ] 执行回放 (replay)
- [ ] 报告导出 HTML/PDF
- [ ] 人工介入决策点
- [ ] 更多报告模板
- [ ] 外部数据库支持（PostgreSQL/MySQL）
- [ ] 持续性分析：resume、diff、历史查询
- [ ] 数据源管理（多源注册 + 定期画像）

### V3 — 让分析可扩展

- [ ] 因果推断：工具变量、DID、断点回归
- [ ] 时间序列深度分析
- [ ] 自定义 Agent 扩展接口
- [ ] 数据库直连
- [ ] REST API
- [ ] 多用户支持

---

## 技术选型 — 借力而非造轮子

HaGoKu 力量有限，每个组件都选现成最强的，自己只写 Agent 逻辑 + 统计护栏 + 编排策略 + 报告模板。

### 🧠 大脑 — 统计分析核心

**Pingouin** + **Statsmodels**

| 库 | Stars | 选它理由 |
|---|---|---|
| **Pingouin** | 1,500+ | 自动报告效应量（Cohen's d, η², Cramér's V），一个函数出完整结果，HaGoKu 的"准"就靠它 |
| **Statsmodels** | 10,000+ | 回归诊断最全（VIF、Breusch-Pagan、Durbin-Watson），Pingouin 覆盖不到的深度靠它补 |

策略：优先 Pingouin（API 简洁、自带效应量），深度诊断退回 Statsmodels。

### 🦴 骨骼 — 因果推断

**DoWhy** (Microsoft) — V3 集成

| 库 | Stars | 选它理由 |
|---|---|---|
| **DoWhy** | 13,500+ | 唯一成熟的 Python 因果推断库，四步框架（建模→识别→估计→反驳），HaGoKu 区分因果和相关的核心武器 |

MVP 不急，但架构上现在就留好接口。

### 👁 眼睛 — 数据理解与画像

**ydata-profiling** + **missingno**

| 库 | Stars | 选它理由 |
|---|---|---|
| **ydata-profiling** | 13,500+ | 一行代码出完整数据画像，类型推断、缺失分析、分布、相关性全覆盖，Scout 的主力眼 |
| **missingno** | 4,200+ | 缺失值可视化，一眼看清缺失模式（随机 vs 系统），Cleaner 判断 MCAR/MAR/MNAR 的视觉辅助 |

### 🧹 手 — 数据清洗

**sklearn IterativeImputer** + **PyOD** + **Cleanlab**

| 库 | Stars | 选它理由 |
|---|---|---|
| **sklearn IterativeImputer** | 56,000+ | 内置 MICE 实现，无需额外依赖，Cleaner 的缺失值填补主武器 |
| **PyOD** | 9,800+ | 60+ 异常检测算法，Cleaner 区分"测量误差"和"真实极端值"就靠它 |
| **Cleanlab** | 11,400+ | 自动发现数据中的标签错误和异常，数据质量评分 |

不选 fancyimpute/autoimpute — 维护不活跃，sklearn 的 IterativeImputer 够用且稳定。

### 🦾 臂 — AutoML 建模

**FLAML** (Microsoft)

| 库 | Stars | 选它理由 |
|---|---|---|
| **FLAML** | 7,500+ | 最轻量 AutoML，自动选模型+调参，Analyst 的预测建模用 |

不选 PyCaret（太重）/AutoGluon（偏图像文本），FLAML 刚好覆盖表格数据建模。

### 📝 嘴 — 报告生成

**Quarto** + **Jinja2**

| 库 | Stars | 选它理由 |
|---|---|---|
| **Quarto** | 8,500+ | 学术级报告质量，支持 PDF/HTML/Word，LaTeX 数学公式渲染完美 |
| **Jinja2** | 12,000+ | 模板引擎，Reporter 的"模板管呈现，AI 管内容"靠它实现 |

Quarto 负责最终格式输出，Jinja2 负责动态填充内容。

### 🦿 腿 — Agent 编排

**CrewAI**

| 库 | Stars | 选它理由 |
|---|---|---|
| **CrewAI** | 30,000+ | 角色分配式编排，最匹配 HaGoKu 的 4 Agent + Manager 设计 |

不选 LangGraph（偏底层图编排）/AutoGen（偏对话式），CrewAI 的角色→任务→团队模型最自然。

### 🫀 心脏 — LLM 集成与结构化输出

**Instructor** + **Pydantic**

| 库 | Stars | 选它理由 |
|---|---|---|
| **Instructor** | 10,000+ | 让本地 LLM 输出严格遵循 Pydantic Schema，校验失败自动重试 |
| **Pydantic** | 23,000+ | 全系统的数据结构定义和校验，AnalysisResult、CleaningReport 等全部 Pydantic 模型 |

所有 Agent 的输入输出都通过 Instructor + Pydantic 保证结构化，不靠 AI "自觉"。

### 🛡 免疫系统 — 数据验证

**Great Expectations**

| 库 | Stars | 选它理由 |
|---|---|---|
| **Great Expectations** | 11,500+ | 期望式数据验证，"这列不应有空值""数值应在 0-100 之间"，Cleaner 的质检工具 |

### 🏃 脚 — 代码执行

**subprocess + 限制器**（自建轻量方案）

不选 E2B（云服务，与本地优先冲突）。自建安全执行：
- 限制可用模块白名单（pandas, numpy, scipy, statsmodels, pingouin, sklearn）
- 超时控制（30s）
- 禁止网络/文件写入

### 📊 数据处理三件套

**Pandas** + **DuckDB** + **PyArrow**

| 库 | 用途 |
|---|---|
| **Pandas** | 通用数据操作，所有工具的基础 |
| **DuckDB** | SQL 查询，大文件高效分析，Scout 的查询引擎 |
| **PyArrow** | Parquet 读写，Agent 间数据传递格式 |

### 🖥 界面

**Click** + **Streamlit** (V2)

| 库 | 用途 |
|---|---|
| **Click** | CLI 交互，MVP 就有 |
| **Streamlit** | Web UI，V2 加，可视化+交互 |

---

### 选型总览

| 部位 | 选型 | 核心价值 | 对应 Agent |
|------|------|----------|-----------|
| 🧠 大脑 | Pingouin + Statsmodels | 自动效应量 + 深度诊断 | Analyst |
| 🦴 骨骼 | DoWhy (V3) | 因果推断 | Analyst |
| 👁 眼睛 | ydata-profiling + missingno | 数据理解 + 缺失可视化 | Scout, Cleaner |
| 🧹 手 | sklearn + PyOD + Cleanlab | MICE 填补 + 异常区分 + 质量评分 | Cleaner |
| 🦾 臂 | FLAML | 轻量 AutoML | Analyst |
| 📝 嘴 | Quarto + Jinja2 | 学术级报告 + 模板填充 | Reporter |
| 🦿 腿 | CrewAI | 角色式 Agent 编排 | 全体 |
| 🫀 心脏 | Instructor + Pydantic | 结构化输出保证 | 全体 |
| 🛡 免疫 | Great Expectations | 数据验证 | Cleaner |
| 🏃 脚 | subprocess + 白名单 | 安全代码执行 | Analyst |
| 📊 数据 | Pandas + DuckDB + PyArrow | 数据处理 | 全体 |
| 🖥 界面 | Click + Streamlit (V2) | CLI + Web UI | 用户交互 |

**12 组借力组件，HaGoKu 自己只需要写：Agent 逻辑 + 统计护栏 + 编排策略 + 报告模板。**

---

## 项目信息

- **名称**: HaGoKu
- **灵魂**: 用数学挖掘数据背后的真相
- **原则**: 精、准、狠
- **价值**: 门面吸引用户走进来，地基让用户留下来
- **许可**: MIT
- **状态**: 立项阶段
