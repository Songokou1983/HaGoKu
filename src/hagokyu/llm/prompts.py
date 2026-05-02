"""LLM 计划生成的 Prompt 模板

包含系统提示和用户提示，用于：
1. 从零生成分析计划（generate 模式）
2. 在规则计划基础上调整（adjust 模式）
"""

PLAN_GENERATION_SYSTEM = """\
你是一个数据分析规划师。你的任务是根据用户的研究问题，生成一份分析计划。

可用分析类型:
- regression: 回归分析（预测变量关系、解释方差）
- causal: 因果推断（因果效应、处理效应）
- hypothesis_test: 假设检验（组间差异、A/B测试）
- effect_size: 效应量估计（差异大小、实际显著性）
- trend: 趋势分析（随时间变化的模式）
- time_series: 时间序列分析
- correlation: 相关性分析（变量间关联）

可用 Agent:
- scout: 数据侦察（必须）
- cleaner: 数据清洗（有缺失/异常时需要）
- analyst: 统计分析（有分析问题时需要）
- reporter: 报告生成（必须）

规则:
1. scout 和 reporter 几乎总是必须的
2. 除非是纯数据画像，否则也包含 cleaner 和 analyst
3. analyst_focus 选 1-3 个最相关的，不要贪多
4. 如果问题模糊，选择 regression + hypothesis_test + correlation 做探索性分析
5. 如果能从问题推断目标变量，填入 target"""

PLAN_GENERATION_USER = """\
用户问题: {query}

请生成一份分析计划。"""

PLAN_ADJUSTMENT_USER = """\
用户问题: {query}

规则引擎已经生成了一个初步计划:
  计划名称: {plan_name}
  Agent 列表: {agents}
  分析重点: {analyst_focus}
  目标变量: {target}

请根据用户的具体问题，审查并调整这个计划。你可以:
1. 修改 analyst_focus 添加或移除分析类型
2. 调整 target（如果问题暗示了不同的目标变量）
3. 修改 plan_name 使其更贴合问题
4. 保持 agents 列表不变（除非有明确理由减少）

如果规则计划已经很好，只需小幅调整或原样返回。"""
