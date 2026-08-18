#!/usr/bin/env python3
"""Phase D 真 LLM 冒烟 — 用 DataAnalystAgent 走 S1-S5"""
import os, json, sys
os.environ['HAGOKU_DUMP_LLM'] = '1'

import pandas as pd
from hagoku.config import HaGoKuConfig
from hagoku.observability.event_bus import EventBus
from hagoku.agents.agent import DataAnalystAgent
from hagoku.context.session import Session

cfg = HaGoKuConfig.load()
df = pd.read_csv(sys.argv[1] if len(sys.argv) > 1 else 'tests/fixtures/smoke_demo.csv')
query = sys.argv[2] if len(sys.argv) > 2 else '哪个渠道ROI最高'
bus = EventBus()
session = Session(analysis_goal=query)

agent = DataAnalystAgent(cfg.llm, bus)

# S1: 首波字段推断
print('=== S1: infer_field_semantics ===')
results = agent.infer_field_semantics(df, query)
print(f'  {len(results)} fields inferred')
for r in results:
    print(f'    {r["column_name"]}: {r.get("display_name","?")}')

# S2: 工具调用 — cleaner assess
print()
print('=== S2: cleaner assess ===')
rules = agent._load_cleaning_rules()
ctx = {'_session': session, 'query': query, 'column_semantics': results}
assessment = agent.assess(df, ctx, rules)
print(f'  assessment: {assessment.get("summary","")[:80]}...')

# S3: route_to — cleaner → analyst
print()
print('=== S3: route_to cleaner→analyst ===')
ctx['_cleaning_rules'] = rules
ctx['_phase_id'] = '【当前阶段：数据清洗评估】'
r = agent.run_step(ctx, df, '开始分析，可以进入分析阶段了')
rt = r.get('route_to')
sa = r.get('submit_assessment')
print(f'  route_to: {rt.get("stage") if rt else "NONE"}')
print(f'  submit_assessment: {sa}')

# S5: analyst run_step
print()
print('=== S5: analyst run_step ===')
a_ctx = {'_session': session, 'query': query, 'column_semantics': results}
agent._df = df
ar = agent.run_step(a_ctx, df, '用 t 检验分析 ROI 差异')
print(f'  text: {ar.get("text","")[:100]}')
print(f'  submit_analysis: {ar.get("submit_analysis")}')

dumps = len(os.listdir(os.path.expanduser('~/.hagoku/llm_dumps')))
print(f'\n=== DONE: {dumps} dumps ===')
