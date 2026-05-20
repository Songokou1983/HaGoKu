# 外部项目思想参考

HaGoKu Studio 设计的核心理念受以下项目启发，并在此基础上做了适应性重构。

---

## Hermes Agent Kanban

**来源**：本地 LLM 服务项目 Hermes 中的 Agent 看板架构

**借鉴点**：
- Agent 间不直接对话，通过看板（Kanban）交换信息
- 看板状态机：`triage → todo → ready → running → blocked → done`
- 父子任务依赖链（上游完成自动晋升下游）
- Claim 锁机制防止多 Agent 重复执行同一任务

**HaGoKu Studio 差异化**：
- Hermes 面向通用 Agent 协作，HaGoKu Studio 特化为**4 Agent 数据分析流水线**
- 看板局限于单项目内部，不跨项目整合
- 增加 Scribe Agent 作为后台仲裁器，监听 EventBus 驱动看板状态变更

> 看板实现：`hagoku/storage/kanban.py`  
> Scribe Agent：`hagoku/agents/_scribe/agent.py`

---

## CrewAI — 多 Agent 协作框架

**来源**：[crewAI](https://github.com/crewAIInc/crewAI)

**借鉴点**：
- Agent 角色划分（定义 role/goal/backstory）
- 顺序执行（Sequential Process）流水线
- Task 对象绑定 Agent + 预期输出格式
- 工具注入到 Agent 上下文

**HaGoKu Studio 差异化**：
- Agent 不自由选择工具——工具由**代码根据 LLM 决策**执行
- 不依赖 CrewAI 内置的 LLM 对话循环，LLM 仅做一次判定
- 编排权收回：`Orchestrator` 控制阶段顺序和暂停点，Agent 不做自主跳转

---

## Instructor — 结构化输出

**来源**：[instructor](https://github.com/jxnl/instructor)

**借鉴点**：
- Pydantic 模型定义 LLM 输出结构
- `response_model` 保证 JSON 契约
- 重试机制处理格式不符

**HaGoKu Studio 差异化**：
- 每个 Agent 输出的 Pydantic Schema 经过领域专门化（如 `AnalyzerStructuredResult` 含统计检验字段）
- 护栏引擎逐字段校验 LLM 输出（p 值/效应量/置信区间完整性），不完全依赖 Instructor 的格式校验

---

## Pingouin + Statsmodels — 统计分析

**来源**：[Pingouin](https://pingouin-stats.org/) / [Statsmodels](https://www.statsmodels.org/)

**借鉴点**：
- Pingouin：自动效应量 + 完整统计表格（p 值/效应量/CI 一体）
- Statsmodels：回归诊断（残差图/Q-Q/杠杆/VIF）

**HaGoKu Studio 差异化**：
- 将 LLM 的方法选择与代码的统计计算解耦：LLM 选方法，代码跑计算
- 护栏自动校验每个分析结果是否含必需统计量
- 诊断图表集成到报告双轨输出

---

## sqlite_vec — 向量检索

**来源**：[sqlite_vec](https://github.com/asg017/sqlite-vec)

**借鉴点**：
- SQLite 扩展实现向量存储和 KNN 搜索
- 零额外服务依赖（无需 pgvector/Pinecone）

**HaGoKu Studio 差异化**：
- YAML 作为知识条目 truth source，sqlite_vec 数据库作为向量索引（可重建）
- `use_count` 仅写入 YAML，不写入向量库
- embedding API 不可用时自动降级（`recall()` 返回空列表）

---

## Plotly — 交互式可视化

**来源**：[Plotly](https://plotly.com/python/)

**借鉴点**：
- 交互式图表内嵌 HTML
- 统计图表类型丰富（箱线图/小提琴/残差/QQ）

**HaGoKu Studio 差异化**：
- 图表由代码渲染（非 LLM 生成代码再执行）
- 报告模板中的图表通过 Jinja2 注入，不做动态图表生成

---

## langchain-openai — LLM 适配层

**来源**：[langchain-openai](https://github.com/langchain-ai/langchain)

**借鉴点**：
- OpenAI 兼容 API 调用封装
- Chat 消息标准化

**HaGoKu Studio 差异化**：
- 仅使用 `ChatOpenAI` 客户端做 API 适配，不使用 LangChain 的 Chain/Agent/记忆等功能
- 上下文组装由 `Orchestrator` 和 `Scribe` 手动拼接，不依赖 LangChain 的 prompt 模板系统
- 知识检索不使用 LangChain 的向量存储抽象

---

## 核心理念交叉索引

| 理念 | 启发来源 | 在 HaGoKu Studio 中的体现 |
|------|---------|-------------------|
| 壳子/架构/通道三分 | 函数式编程 + Unix 管道哲学 | LLM 做语义理解，代码做机械执行 |
| Agent 看板协作 | Hermes Agent Kanban | 父子任务链 + Claim 锁 + Scribe 仲裁 |
| 结构化输出 | Instructor | Pydantic Schema + 护栏逐字段校验 |
| 统计第一 | Pingouin/Statsmodels | 每结论配检验 + 效应量 + CI |
| 最小依赖 | sqlite_vec | 零外部服务向量检索 |
| 双轨报告 | 严谨学术风格 + 现代信息设计 | 吸引力层 + 核心价值层 |