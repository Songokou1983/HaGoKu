# HaGoKu Studio — 项目规范（The Single Source of Truth）

> **核心信条**：LLM 在语义判断上比代码更可靠。Code 的活是构建通道让 LLM 自由发挥，不是替 LLM 干活。

## 灵魂

> **让每个小模型，都能做专业级商业分析。**

HaGoKu Studio 追求统计分析深度：自动检验假设、报告效应量、做模型诊断，区分因果和相关。同时不牺牲信息设计的吸引力——门面吸引用户走进来，地基让用户留下来。

---

## 演进方向

> **Phase A-D 已完成（2026-06-11）**：4 agent 合 1 DataAnalystAgent + 27 工具全集 + Meta v2 四组件。[详见](docs/plans/2026-06-11-collapse-to-single-agent-brief.md)。核心信条不变。
>
> **Phase A-D 已完成（2026-06-11）**：4 agent 合 1，prompt 单点化，阶段切换 LLM 化，Meta v2 四组件。[详见](docs/plans/2026-06-11-collapse-to-single-agent-brief.md)

---

## 设计哲学

| 维度 | 含义 |
|------|------|
| **精** | 报告结论精炼：不超过 5 条核心发现 |
| **准** | 每条结论有统计检验支撑（p值 + 效应量 + 置信区间） |
| **狠** | 直接回答用户问题，不回避不确定性 |
| **轻量** | 本地 LLM 优先，最小依赖，数据不出本机 |
| **专业** | 严肃对待不确定性，不假装 100% 确定 |

---

## 壳子、架构、通道

HaGoKu Studio 由三个要素构成。代码只负责壳子（运行环境）、架构（编排规则）、通道（信息流 + 控制权双向路由）。所有语义理解和流程决策由 LLM 完成。

| 要素 | 含义 | 代码做什么 |
|------|------|-----------|
| **壳子** | Web UI + CLI + 事件系统 + 存储 | 给用户操作界面，给 Agent 运行环境 |
| **架构** | Agent 分工 + 协作顺序 + 护栏 + 看板 | 谁在什么时候做什么，产出如何传递 |
| **通道** | 信息通道（上下文 ↔ LLM）+ 控制通道（LLM 流程决策） | 信息完整到达 LLM 且不被截断丢弃；LLM 的产出/决策机械执行；失败轮次原样保留 |

**通道有两类，缺一不可**：

- **信息通道**：用户输入 / 数据画像 / 上游摘要 → LLM；LLM 的结构化产出 → 状态。
- **控制通道**：LLM 主动表达"本阶段完成 / 留在本阶段 / 跳回上一阶段 / 再问用户一次"作为 tool_calls，由代码机械执行。**控制权也是信息的一种**——不通控制权的设计，LLM 永远只能在工位上发言，工厂总图归代码所有。

**通道的检验标准（二问）**：

1. **信息是否完整到达？** LLM 看到的上下文，能否支撑它做出正确决定？不能 → 通道残缺，补通道（多传信息或多开出口），不补代码规则。
2. **失败后上下文是否还在？** 一轮对话失败后，对话历史是原样保留供下一轮继续，还是被 RuntimeError 一起扔掉了？被扔掉了 → 通道断裂。信息通道不仅管"向前送"，也管"不后撤"——代码没有权力替 LLM 销毁它可能需要的历史。

**通道的首选机制**：function calling（tools）。代码定义工具签名（语义工具 `update_field_understanding`、控制工具 `done_with_stage` / `route_to` 等），LLM 主动调用。代码仅机械执行 `msg.tool_calls` 的结果。

任何需要"判断"的环节——用户想干什么、字段是什么意思、下一步去哪、失败后该换什么策略——信息必须完整到达 LLM，LLM 的决定必须能完整回到系统。**详见下文「通道完备性十律」**。

---

## 代码边界

### LLM 负责（语义决策）

- 理解用户自然语言输入
- 推断字段含义和角色
- 选择分析方法
- 生成报告叙述
- 决定降级策略

### 代码负责（机械执行）

- LLM 健康检查、事件路由、状态写入、格式校验
- 统计计算（Pingouin/Statsmodels）
- 可视化渲染（Plotly）
- 数据 I/O（Pandas/DuckDB）
- 护栏校验（p 值/效应量/置信区间存在性检查）
- 看板状态机（确定性状态转换）

**区分线**：LLM 管"做什么"，代码管"怎么做"。

### 字段理解的归属（2026-06-03 确立）

字段语义是**项目级信息**，不属于跨项目知识库。

| 存储 | 归属 | 生命周期 |
|------|------|---------|
| **项目记忆**（SQLite memory 表） | 用户确认过的字段名/描述 | clear-history 时清除 |
| **跨项目知识库**（knowledge.yaml/db） | 分析策略模式，**不存字段名** | 跨项目持久 |

**设计原则**：
- LLM 看列名 + 样本值 + 数据类型就够推断字段含义，不需要历史知识库
- 知识库存字段名会污染新项目（BU 在 A 项目=公司，B 项目=业务单元）
- 只有用户显式纠正过的字段（`confirmed_by_user=True`）才持久化到项目记忆
- `clear-history` 清除数据库和项目文件，**不清除知识库**（知识库是分析经验，不是字段名）

### Scope 引导式分析（2026-06-03 设计阶段）

字段理解阶段产出 scope（分析范围：target + features + excluded），注入后续关注点的上下文。Scope 是**引导性的**——全表始终对 LLM 可见，scope 告诉 LLM "优先关注这些"，用户随时可解锁新维度。

详见 `docs/superpowers/specs/2026-06-03-scope-guided-analysis-design.md`。

### 工具与流程：给 LLM 用，不给代码用

代码提供工具和流程，**LLM 决定用不用、怎么用**。

HaGoKu Studio 的核心隐喻：**LLM 是工作室的资深分析师，代码提供的是工位、工具、电话线。用户走进工作室，跟分析师直接沟通需求。没有人在用户和分析师之间自作主张。**

**示例对比**：

| 场景 | ✅ 工具与流程（代码该做） | ❌ 硬写（代码不该做） |
|------|--------------------------|---------------------|
| 字段理解 | 代码提供 3 列表格模板（display_name/description/状态），LLM 填写内容 | 代码用正则解析用户输入，自己判断哪个列该更新什么 |
| 分析方法 | 代码注册 50+ 分析方法（工具库），LLM 选择调用哪个 | 代码用 if-else 根据关键词选择分析方法 |
| 用户反馈处理 | 代码提供 `update_field_understanding` function calling 工具，LLM 通过 tool_calls 主动选择更新哪些字段，代码机械写入 context | 代码用正则 `col=desc` 格式解析用户输入并自行更新字段 |
| 保底/降级 | LLM 失败时保留原 context 不变，通知用户"AI 暂时无法处理" | LLM 失败时代码用正则/默认值自己填表 |

**检验标准**：如果一段代码的语义产出（字段含义、方法选择、报告叙述）可以被删除且不影响最终结果（因为 LLM 会产生同样的产出），那这段代码就是硬写——应删除。

**保底的正确姿势**：保底不是"代码替 LLM 完成任务"，而是"保留原样，通知用户"。LLM 失败 → 保留原 context 不变 → 报告用户 → 用户决定重试或调整。

**关于模板**：表格列结构、报告章节、分析方法签名——这些都是"办公用品"，由代码定义供 LLM 使用。代码定义**形状**，LLM 填写**内容**。

### 全局工具注册表

HaGoKu 有一个**项目级工具注册表**（`hagoku/tools/registry.py`）。代码只做三件事：注册工具签名、执行工具调用、返回结果。LLM 决定调哪个、什么时候调。

```
hagoku/tools/
├── registry.py          # AgentTools 注册表（单例）：register / to_openai / dispatch
├── agent_tool_defs.py   # 工具定义：每个 Tool = name + description + parameters + handler + agents
└── ...
```

**新增工具只需在 `agent_tool_defs.py` 加一个 `Tool(...)` 注册**，指定 `phase_tag=["理解字段","评估清洗"]` 标注典型关注点。Phase D 后 27 工具全集对 LLM 可见。

**已注册工具**（7 个，Phase D 后全集对 LLM 可见）：

| 工具 | 典型关注点 | 用途 |
|------|----------|------|
| `get_column_stats` | 通用 | 获取某列统计量（min/q25/median/q75/max/mean） |
| `get_sample_rows` | 通用 | 获取某列抽样值 |
| `list_columns` | 通用 | 列出所有列名和类型 |
| `group_stats` | 评估清洗, 跑统计 | 按某列分组查看另一列统计 |
| `update_field_understanding` | 理解字段 | 更新字段中文名/含义 |
| `update_field_role` | 理解字段 | 设置 target/features/ignored |
| `restrict_analysis_to` | 理解字段 | 限定参与分析的字段 |

**检验标准**：新增能力时，若要在 prompt 里手写 JSON 格式让 LLM 输出 → 说明缺工具，应在注册表补。

---

### 全局联动原则

字段理解、角色分配、参与分析、清洗建议——这些不是孤立决策。LLM 更新任何一项后，必须同步检查其他项是否需要调整。代码通过 channel 传递完整上下文（字段表、分析目标、对话历史），LLM 基于全局做联动判断。

> 这不是规则，是能力。通道的任务是让 LLM 看到全局。LLM 看到了，自己会联动。

---

## 上下文保真律

> **在一个由上下文驱动、事件驱动、LLM 决策驱动的系统里，"默认知道"是不够的——必须"显式写死"。用户纠正必须持续生效，不能靠代码"记得"。**

对话的连贯性不靠精巧的算法。靠的是：信息没被截断、没被隐藏、没被代劳。每一次用户的纠正、每一次 LLM 的偏差、每一次工具调用的结果——全部留在上下文里，原样传递。LLM 拿到完整记录，自己会读、会调整。

这条律是十律的前提——没有上下文保真，通道再"完备"也只是在传送一份被代码篡改过的副本。

### 一、总原则

1. **动态上下文优先，且排在指令前面** — 分析目标、字段状态、上游摘要、用户纠正——这些是 LLM 做判断的**依据**，必须排在 prompt.md 等静态指令的**前面**。存在但埋在末尾 96% 位置 = 不存在。LLM 第一眼看到的必须是"你要分析什么、数据长什么样"，然后才是"你有哪些关注点、你的推理链路是什么"。
2. **用户纠正不可丢失** — 用户说的每一个纠正，是对话的原始证据。追加，不覆盖，不合并，不摘要。
3. **代码不得替模型摘要、删减、代言** — 代码没有权力决定"这句用户原话不重要，可以压缩"。`upstream_summary` 不能替代原始对话记录——上一阶段的 tool exchange 必须原样进入当前阶段的 messages_history。

### 二、操作规则

1. **动态上下文排在静态指令前面** — `to_messages_for_llm()` 拼装 system 消息时，分析目标 + 字段状态 + 上游摘要必须排在 prompt.md 正文**之前**。prompt.md 是指令（告诉 LLM 怎么做），动态上下文是依据（告诉 LLM 面对什么）。依据在前，指令在后。
2. **用户原话必须原样保留** — `raw_user_text` 逐字存储，不得改写、精简、"理解后替换"。
3. **纠正必须进入后续 prompt/history** — `to_messages_for_llm()` 序列化时，历史 messages 包含全部轮次的用户输入，不以"只保留最近 N 轮"为由截断早期纠正。
4. **跨阶段原始对话不可丢弃** — 阶段切换时（如 cleaner→analyst），上一阶段的 tool exchange 必须以原始 role=tool 形式出现在 messages_history 中，不得仅以 `upstream_summary` 的一段摘要文字替代。代码不知道哪些工具结果对下游重要——LLM 自己看。
5. **只允许展示层做清洗，不允许信息层失真** — UI 渲染层可以格式化、高亮、折叠，但传给 LLM 的 messages 必须是用户说的每一个字，原样。
6. **失败轮次也必须保留** — LLM 答错、没调工具、产出废话——那一轮的完整记录（用户说了什么、LLM 回了什么、工具结果是什么）全部留在上下文里。RuntimeError 不能成为销毁对话记录的借口。

### 三、反例说明

| 反例 | 为什么违规 |
|------|-----------|
| 用户纠正了三次，代码合并成一句"用户调整了字段映射" | 用户纠正不可丢失——LLM 需要看到用户是怎么一步步纠正的，而不是一句总结 |
| 代码把三轮对话压缩成"用户想要 ROI 分析"后传给 LLM | 代码替模型摘要——LLM 失去了用户原话中的语气、重点、歧义容忍度 |
| 只保留最近 3 轮，丢掉第 1 轮的用户原话 | 后续轮次必须能看到此前纠正——早期纠正可能是最关键的 |
| UI 为了整洁裁掉历史上下文 | 展示层清洗不能影响信息层——UI 可以折叠，但传给 LLM 的不能少 |
| 代码根据"看起来差不多"自行覆盖用户的修正 | 代码替模型代言——用户说"不是收入，是净利润"，代码不能存成"字段映射纠正" |
| LLM 一轮没调对工具 → RuntimeError，整段对话丢弃 | 失败轮次也必须保留——对话有自愈能力，LLM 看到失败和纠正，下一轮自己会调整 |

> **起源**：2026-06-12 架构讨论。"我们现在的对话为什么连贯——因为没有隐藏状态。你说了什么我全看到，我偏了你能纠正。上下文是对话的脊椎，断了就瘫了。"

---

## 三层禁止硬编码

> **核心认知**：铁律只覆盖代码层是不够的。AI 实现者在代码层被限制后，会自然地把限制转移到提示词层——表面上代码干净了，实质上"替 LLM 做判断"这件事只是换了个隐蔽的地方继续发生。必须在**代码层、提示词层、上下文层**三层同时守门。

### 三层对照表

| 层 | 违规形式 | 典型症状 |
|---|---|---|
| **代码层** | 写死业务判断 | `if field_name == "revenue": role = "target"` |
| **提示词层** | 预设业务结论 | "你必须把带有'收入'字样的字段判断为目标变量" |
| **上下文层** | 替 LLM 摘要 | 把用户三次纠正压缩成"用户调整了字段映射"后传入 messages |

### 提示词层合法 vs 违规

**合法**（给 LLM 装备信息，告诉它面对什么）：
- 当前阶段说明、数据字段列表、用户原话、工具使用方式、输出格式要求
- 分析目标、数据背景、上游阶段摘要

**违规**（替 LLM 做判断，预设业务结论）：
- "你必须把这个字段判断为 target"
- "如果用户说 X，你应该理解成 Y"
- "不要分析 Z 类型的关系"
- "这个数据集的异常值应该忽略"
- "用户说的 A 其实是指 B"

**区分线**：提示词说"你有什么工具、你面对什么数据"是合法的。提示词说"你应该得出什么结论"是违规的。

### 铁律转移漏洞

> **这是最常见的隐性退化路径**：开发者（包括 AI 实现者）遵守了代码层铁律，却在提示词里写入了业务语义预设。代码 review 看不出来，测试也不容易覆盖，但它彻底破坏了"LLM 自主语义判断"的设计原则。

**识别方式**：检查每次 prompt.md / system_prompt 修改，看是否出现了「应该/必须/禁止」修饰具体业务对象的句子。

**防御方式**：
1. prompt.md 修改必须附 dump 对比（铁律 10 已覆盖）
2. AI 实现者做 code review 时，提示词改动和代码改动都要过铁律检查
3. 当某个测试不绿时，禁止通过在 prompt 里"规定答案"来让测试通过——这是最典型的转移漏洞触发场景

---

## 提示词写作规范

> **起源**：2026-06-12，prompt.md 从 15520 字节重构到 ~500 字节过程中总结的可操作判准。

### 核心判准：系统接口 vs 思考方法

| | 系统接口（写） | 思考方法（不写） |
|---|---|---|
| **定义** | LLM 需要知道才能**操作这个系统**的信息 | LLM 拿到数据和上下文后**自己能推导**的判断 |
| **例子** | route_to 怎么调、ask_user 有几种格式、报告结论必须含四层 | 工具怎么选、字段怎么判断、离群值要不要洗 |
| **检验** | 删掉这段 → LLM 无法正确操作系统 | 删掉这段 → LLM 仍能从上下文推导出正确行为 |

### 可写清单（四类）

| 类别 | 说明 | 示例 |
|------|------|------|
| **角色定义** | 一句话，LLM 的身份 | "你是数据分析师" |
| **系统控制接口** | LLM 必须知道才能调的系统机制 | route_to 用法、ask_user 格式、submit 工具时机 |
| **阶段边界** | 当前阶段触发条件和职责范围 | "只做字段理解，不做清洗"、"进入时自动触发" |
| **输出格式** | 代码无法从 tool schema 里替代的结构要求 | 报告四层结构（含义/统计/溯源/局限性） |

### 不可写清单（四类）

| 类别 | 说明 | 反例 |
|------|------|------|
| **工具速查表** | tool schema description 已有，写两遍 = 双重维护点 | 26 行工具表、策略列表 |
| **分步工作流程** | 替 LLM 规划步骤，LLM 拿到上下文自己会做 | "1.查记忆 2.获取数据画像 3.深度分布分析..." |
| **判断规则** | 预设业务结论，违反铁律 1 的提示词等价形式 | "极端值有意义，倾向于不洗"、"目标变量 → 极度保守" |
| **重复信息** | 同一件事在提示词里出现两次 | 两张 route_to 表 |

### 检验方法

对 prompt.md 每一行问三个问题：

1. **这是系统接口还是思考方法？** — 思考方法 → 删
2. **LLM 不看这行还能正确操作吗？** — 能 → 删
3. **这行在 tool schema / 对话历史里已有吗？** — 有 → 删

三个问题都"否"才留。

### 退化预警

以下模式出现时，说明思考方法正在伪装成系统接口进入 prompt：

- "你应该先…再…" → 分步工作流程
- "倾向于 / 保守 / 通常" → 判断规则
- "如果用户说 X，你应该 Y" → 意图映射
- 工具名出现在 prompt 正文里（不在系统控制接口段） → 工具速查表

### 参考长度

HaGoKu 的 prompt.md 当前 ~3KB / 74 行。长度本身不是目标——但如果增长到超出当前 2 倍，检查是否写了不可写清单里的内容。

---

## 配置中性（原「通道完备性十律」，已由架构自动满足）

> **Phase D 后**：单 agent + 单 chat（ProjectContext）+ `to_messages_for_llm()` 统一入口已物理保证原律 1-6/8-10 自动满足。仅保留配置中性（铁律 9）作为文档规范。契约测试（`tests/test_product/test_information_arrival.py`）持续守门。

> 项目文档（`CLAUDE.md` / `PROJECT.md` / `.env.example` / commit message / memory / AI 输出）**不绑具体部署配置**——LLM 模型名、API 端点 URL、端口等都是用户运行时通过 `hagoku-ui` 设置功能选择的，不是项目真理。

**反例**：
- `PROJECT.md` 写 `HAGOKYU_LLM_MODEL=Qwen3.6-35B-A3B` 当默认值——一旦换模型就过时
- `.env.example` 写 `HAGOKYU_LLM_BASE_URL=http://localhost:8080/v1` 当模板值——云端模型不是这个地址
- AI 输出 "因为当前用 35B 模型 context 是 128K"——把 runtime config 当 design constraint
- memory 写 "项目当前用某个云端模型 1M context"——memory 跨 session 持久，runtime 变了就误导

**合法写法**：
- 文档/示例里出现模型名时 → `<用户配置>` 占位
- BASE_URL / port 等部署值 → 留空 + `# 用户配置` 注释
- 描述列加 "（用户运行时通过设置功能选择）" 说明
- 涉及 LLM 能力时 → 按"配置范围"评估（如"假设 context 在 128K-1M 之间"），不绑具体模型
- `config.py` 数据类默认值可保留（Python 类行为），但 docs 描述不许指向具体值

**检验**：
```bash
grep -rn "Qwen\|A3B\|localhost:8\|text-embedding" CLAUDE.md PROJECT.md .env.example  # 应空
grep -rn "minimax\|claude\|gpt-\|gemini" hagoku/ docs/  # AI 内部输出不留具体模型名
```

> 起源：2026-06-06 scribe redesign 讨论中，AI 反复在项目文档/AI 输出/记忆里写具体模型名（先 Qwen 后又写另一个云端模型名），被用户两次纠正。

---

## 防退化机制

> **Phase D 后**：单 agent + `to_messages_for_llm()` + pre-commit hook 已物理拦截所有 4 类退化。信息抵达契约（`tests/test_product/test_information_arrival.py`）持续守门。

### 已知退化路径清单

每次大改之后，回来对照这张清单检查：

| 退化路径 | 典型触发场景 | 检验方式 |
|---|---|---|
| **代码层硬编码** | 新增字段处理逻辑时 | 铁律 1；pre-commit hook |
| **提示词层硬编码** | 测试不绿时在 prompt 里"规定答案" | 铁律 10 + dump 对比 |
| **上下文层摘要替换** | 架构重构、阶段合并时顺手"整理"历史 | `test_information_arrival.py` |
| **纠正信息被轮次截断** | 历史窗口优化、prompt 长度压缩 | 纠正信息不得早于普通历史被截断 |
| **raw/clean 混流** | 流式输出、事件总线调整时 | UI 消费的必须是 clean channel，raw 仅用于 dump |
| **失败被静默兜底** | 防御性 try/except、默认值填充 | 铁律 7；`raise RuntimeError` |
| **架构收缩顺手压扁上下文** | 多 agent 合并为单 agent 时 | 重构前后对比 `to_messages_for_llm()` 输出 |

### 可测试性守门

| 测试 | 守护目标 |
|---|---|
| `test_information_arrival.py` | 用户纠正在后续轮次仍可见 |
| `test_control_channel_link_integrity.py` | tool_call → 业务效果链路完整 |
| `test_doctrine_compliance.py` | 代码层零硬编码 |
| 待补：提示词层审计 | prompt.md 无业务结论预设 |
| 待补：纠正保留测试 | 第 N 轮纠正在第 N+3 轮仍在 messages 中 |

---

## Agent

**唯一 DataAnalystAgent**（`hagoku/agents/agent.py`）。按 4 关注点工作（理解字段/评估清洗/跑统计/写报告），通过 `route_to` 自主切换。统一 prompt（`hagoku/agents/prompt.md`，74 行）。27 工具全集可见。

ProjectContext 持有唯一 chat；`to_messages_for_llm()` 统一 LLM 调用入口。

### 分析计划生成

用户查询到达后，系统通过 LLM 两阶段生成分析计划（pipeline 编排的决策依据）：

| 阶段 | 组件 | 作用 |
|------|------|------|
| **意图解析** | `QueryParser.parse()` → LLM Structured Output | 从自然语言提取意图、目标变量、分组维度、过滤条件等 |
| **计划生成** | `plan_schema.LLMPlanResponse` + `llm/prompts.py` | LLM 依据意图和上下文，决定 Agent 编队、分析焦点（regression/causal/hypothesis_test 等 7 种）、计划名、目标变量 |

**Schema 定义**（`llm/plan_schema.py`）：
- `LLMPlanResponse`（Pydantic）：`plan_name`、`agents`、`analyst_focus`（7 种可选）、`target`、`query`、`reasoning`
- 默认探索焦点：`["regression", "hypothesis_test", "correlation"]`
- LLM 失败兜底：已修复（2026-06-11 doctrine-violations-cleanup）。`parse_query()` 在 LLM 不可达时 raise RuntimeError。

**Prompt 模板**（`llm/prompts.py`）：
- 系统 prompt：定义分析规划师角色、决策依据、6 种分析类型描述、决策规则
- 调整模式：在规则计划基础上由 LLM 判断是否需调整

**代码职责**：仅定义 schema 形状和 prompt 模板，不参与决策。LLM 选方法、定焦点；代码机械校验 schema 并调度 Agent。

> 实现：`hagoku/llm/plan_schema.py`、`hagoku/llm/prompts.py`、`hagoku/manager/query_parser.py`

---

## 人机互动

- **LLM 主动暂停**：通过 `ask_user(question, expected_format)` 工具触发，UI 按 choice/free_text/yes_no 渲染
- **自然语言对话**：单 chat 贯穿全程，`route_to` 自主切换关注点
- **字段记忆复用**：确认的字段描述通过 MemoryManager 持久化，下次自动复用

> 命令系统：`docs/COMMAND_SYSTEM.md`

---

## 报告设计 — 双轨输出

| 层 | 面向 | 内容 |
|----|------|------|
| **吸引力层** | 所有人 | 核心结论（≤5条）、关键图表、通俗解读 |
| **核心价值层** | 专业人士 | 完整统计结果、检验假设、方法细节、诊断数据 |

---

## 知识系统（三层 Memory）

| 层 | 存储 | 内容 | 生命周期 |
|---|------|------|--------|
| ① 学术方法库 | `hagoku/memory/methods/` | 教科书级统计方法知识 | 手动维护，低频更新 |
| ② 成长记忆 | `hagoku/memory/lessons.jsonl` | 实战经验（LLM 通过 `save_lesson` 工具积累） | 跨项目持久 |
| ③ 项目记忆 | MemoryManager (SQLite) | 当前项目字段定义、用户纠正 | `clear-history` 时清除 |
| 兜底 | LLM 自由发挥 | 前两层无匹配时由 LLM 自行推导 | 无持久化 |

> 实现：`hagoku/memory/`、`hagoku/tools/memory_tools.py`（8 工具注册）


---

## 看板（UI 显示对象）

`kanban.db` 在 Phase C 后降级为 UI 进度显示对象，不再参与流程控制。阶段切换由 LLM 通过 `route_to` 工具自主决定。

```
~/.hagoku/projects/{project}/
├── kanban.db       ← SQLite（UI 进度条数据源）
├── context.md      ← 项目上下文
├── data/           ← 数据制品 (Parquet)
├── runs/           ← 分析运行记录
└── progress.yaml   ← 项目记忆
```

---

## 统计护栏 — 三级安全网

### 强制级（Violation = 阻止正式报告输出）

| 规则 | 说明 |
|------|------|
| `no_conclusion_without_test` | 无统计检验不下结论 |
| `must_report_effect_size` | 显著必须配效应量 |
| `must_report_ci` | 点估计必须配置信区间 |
| `no_causal_claim_without_method` | 声称因果须有因果推断方法 |
| `must_diagnose_model` | 建模后须做残差诊断 |

### 警告级（Violation = 标注但允许输出）

| 规则 | 说明 |
|------|------|
| `assumptions_violated` | 假设不满足，建议替代方法 |
| `small_sample_size` | 样本量不足警告 |
| `high_vif` | 多重共线性超标警告 |

### 提示级（Violation = 建议不阻断）

| 规则 | 说明 |
|------|------|
| `suggest_nonlinear` | 残差暗示非线性，建议检查 |
| `missing_not_random` | 缺失非随机，建议谨慎 |

---

## 失败处理

HaGoKu 中失败只有三条路径，不做任何「降级到次优路径」的设计。三类失败各有应对策略，但**共同点是：不许代码替 LLM 做语义判断来"装作成功"**。

### 路径 1：LLM 异常

| 场景 | 处理 |
|------|------|
| LLM 超时 / 不可达 / 返回格式异常 | 终止当前 run，通知用户修复 LLM 配置（API key、网络、模型名）后重试 |

> **前置拦截**：pipeline 启动前 `health.check_llm_health()` 验证 LLM 可达性；失败则返回错误，不进 pipeline。

### 路径 2：通道失败 = 项目失败

通道（Agent 输入输出 serialize → transport → validate 链路）是 HaGoKu 的脊梁，**通道失败即项目失败**。

| 场景 | 处理 |
|------|------|
| 任一通道环节（序列化、传输、解析）抛异常 | **项目失败，必须修复通道后重跑**，不允许降级、不允许绕过、不允许兜底 |

> 通道范畴：
> - `orchestrator.py` 对 Agent 的上下文组装与结果写入
> - `storage/` 读写（parquet / yaml / sqlite / JSON）
> - `guardrails/parsers.py` 结构化输出校验
> - `api/ws_handler.py` WebSocket 消息序列化
> - `tools/` 工具函数签名与返回值约定
> - 任一环节抛非 LLM 类异常（`ValueError` / `TypeError` / `FileNotFoundError` 等）均属通道异常

### 路径 3：语义未理解（铁律 7）

LLM 收到了用户输入但未产生任何有效工具调用（tool_calls 为空、或参数全空、或工具调度结果与用户原话明显无关）——属于第三类失败，**必须显式反馈给用户**，不得静默继续。

| 场景 | 处理 |
|------|------|
| LLM 对用户暂停回复未调用任何工具 | UI 显式提示"系统未理解你的输入，请换一种说法"，保留原 context，本轮暂停继续等待 |
| LLM 调用了工具但参数全为空 / 与原话无关 | 同上，并在 `process_log.md` 记录 raw_text + 工具调用结果供审计 |

> **禁忌**：`logging.warning(...)` 然后默默推进 — 用户感觉"我说了好几遍系统都没反应"，是 B 类语义漏水的高发症状。

### 设计原则

> **不做降级，只做三种响应：提醒用户修 LLM、修代码修通道、提醒用户换说法。**

### 代码层合法动作清单（给实现者）

当代码遇到 LLM 调用失败、解析失败、工具未调、参数无效等异常情况时，**唯一合法的代码动作只有以下四种**。任何其它"防御性兜底"都是违规：

| 合法动作 | 适用情况 | 写法 |
|---------|---------|------|
| **A. 抛 RuntimeError** | LLM 不可达 / 模型返回完全无法解析（非语义失败） | `raise RuntimeError("LLM 不可达，请检查配置")` → 走路径 1 |
| **B. 写未理解信号** | LLM 调用成功但未产生有效工具调用 | `ctx["_last_understanding_failure"] = {raw_text, model_reply, ...}` 然后 `return []` → 走路径 3 |
| **C. 透传给下一轮** | LLM 给出部分工具调用但语义不完整 | 已落地的部分写权威结构，未落地的留空，由下一轮交互补 |
| **D. 拒绝写入** | LLM 给出的参数与用户原话明显矛盾 | 不写权威结构，等同情况 B（写未理解信号） |

**禁止动作**：详见 `CLAUDE.md` 触发词速查表。核心原则：代码做的判断若能用一句中文写成 prompt 让 LLM 做，就是 LLM 的活——代码只负责把信息送到 LLM，不替它写结论。

---

## 数据流

```
原始数据
  ▼ 理解字段 → 数据画像 + 字段语义
  ▼ 评估清洗 → 清洗报告 + 清洁数据
  ▼ 跑统计 → 分析结果 + 诊断
  ▼ 写报告 → 双轨 HTML
  ▼ 用户
```

数据传递格式：Parquet + 元数据 JSON。

---

## 存储架构

```
~/.hagoku/
├── config.yaml
├── hagoku.db                     # SQLite 元数据库
└── projects/{name}/
    ├── progress.yaml / context.md / kanban.db
    ├── data/                     # raw/cleaned .parquet
    ├── runs/{run_id}/
    │   ├── run_meta.json / plan.json / events.jsonl
    │   ├── results/ / diagnostics/ / output/
    └── reports/                  # latest.html → runs 的符号链接
```

---

## 可观测性

HaGoKu Studio 全程透明，用户坐副驾驶位：

```
🔍 理解字段 ── ✅ 完成 (12s)
🧹 评估清洗 ── ✅ 完成 (8s)
📊 跑统计   ── 🔄 执行中...
📝 写报告   ── ⏳ 等待中
> Orchestrator（📋 看板驱动 + 阶段消息生成）在后台运行，不显示终端进度。
```

---

## 项目结构

```
hagoku/
├── llm/              # LLM 客户端 (OpenAI-compatible)
├── manager/          # 编排器（LLM 客户端管理 + tool dispatch + WebSocket 桥）
├── agents/           # 唯一 DataAnalystAgent + prompt.md + base/types/constants
├── memory/           # 三层记忆（学术方法 / 成长经验 / 项目记忆）
├── tools/            # 分析工具集（插件架构）
├── guardrails/       # 统计护栏 + 输出解析
├── storage/          # 持久化（kanban/project/artifact/database）
├── observability/    # 事件总线 + 终端显示
├── api/              # FastAPI + WebSocket
└── devtools/         # 交互场景模拟
```

> 前端：`hagoku_web/`（Vite + React + Zustand，固定侧栏/顶栏视图切换）

---

## 技术选型

| 部位 | 选型 | 核心价值 |
|------|------|---------|
| 🧠 大脑 | **Pingouin** + **Statsmodels** | 自动效应量 + 深度诊断 |
| 🧹 手 | **sklearn** + **PyOD** | MICE 填补 + 异常检测（IsolationForest） |
| 📝 嘴 | **Jinja2** + Plotly | 模板渲染 + 交互式图表 |
| 🦿 腿 | **Orchestrator（手动编排）** + **langchain-openai** | Agent 调度 + LLM 适配；CrewAI 为可选适配器（按需创建，非管道路径） |
| 🫀 心脏 | **Instructor** + **Pydantic** | 结构化输出保证 |
| 📊 数据 | **Pandas** + **DuckDB** + **PyArrow** | 数据处理 + SQL + Parquet |
| 🖥 界面 | **Click** + **FastAPI** + **React** | CLI + Web UI |

---

## 版本愿景

- **MVP**：统计分析闭环 — 理解字段 → 评估清洗 → 跑统计 → 写报告 全流程可跑
- **V2**：Web UI + 持续性分析 + 人工介入决策点 + 更多报告模板
- **V3**：因果推断 + 时间序列深度分析 + Agent 扩展接口 + 辩论协作

> 交付物详细勾选见 `DEVELOPMENT_PROMPT.md`

---

## 环境变量

唯一读取 `~/.hagoku/.env`（由 `config.py` 加载）。仓库内只维护 `.env.example` 作模板。

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `HAGOKYU_LLM_BASE_URL` | LLM 服务地址（OpenAI 兼容协议，用户运行时配置） | `<用户配置>` |
| `HAGOKYU_LLM_API_KEY` | API 密钥 | `none` |
| `HAGOKYU_LLM_MODEL` | 默认模型名（用户运行时通过设置功能选择） | `<用户配置>` |
| `HAGOKYU_EMBEDDING_BASE_URL` | Embedding 服务地址 | 空（须自行填写） |
| `HAGOKYU_EMBEDDING_API_KEY` | Embedding API 密钥 | `none` |
| `HAGOKYU_EMBEDDING_MODEL` | Embedding 模型名（用户运行时通过设置功能选择） | `<用户配置>` |
| `HAGOKYU_WORK_DIR` | 工作目录 | `~/.hagoku` |
| `HAGOKYU_PROJECT_DIR` | 项目根目录覆盖 | 同 `WORK_DIR/projects` |

---

## 文档索引

| 文档 | 用途 | 受众 |
|------|------|------|
| **PROJECT.md**（本文件） | 项目灵魂、架构原则、通道完备性十律、唯一真相源 | 所有人 |
| `README.md` | 用户手册（安装、命令、快速开始） | 用户 |
| `DEV.md` | 开发快速上手 | 新贡献者 |
| `docs/DEVELOPMENT.md` | 设计手册（看板/向量/防护/审查） | 开发者 |
| `docs/EXTERNAL_REFERENCES.md` | 外部项目思想参考 | 开发者 |
| `docs/TROUBLESHOOTING.md` | 常见问题排查 | 开发者 |
| `docs/AGENT_INTERACTION_CONTRACT.md` | Agent 交互可执行契约 | 开发者 |
| `docs/INTERACTION_MULTITURN_PLAN.md` | 多轮对齐分期方案 | 开发者 |
| `DEVELOPMENT_PROMPT.md` | 路线图跟踪 + 任务传递 + 审查约定 | 协作者 |
| `docs/COMMAND_SYSTEM.md` | 命令系统完整设计 | 开发者 |
| `CLAUDE.md` | AI 编码助手上下文 | AI 助手 |
| `docs/plans/2026-06-11-meta-layer-v2-brief.md` | Meta v2（Prompt Lab + LessonAuditor + prompt_gate + dev CLIs） | 开发者 |

---

## 项目信息

- **名称**: HaGoKu Studio
- **灵魂**: 让每个小模型都能做专业级商业分析
- **原则**: 精、准、狠
- **许可**: MIT