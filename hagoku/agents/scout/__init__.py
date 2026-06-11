# Phase D shim — 旧 scout agent 已合并到 DataAnalystAgent
# 此模块仅保留兼容旧 import 路径，Phase E 删除
from hagoku.agents.agent import DataAnalystAgent as ScoutAgent
from hagoku.agents.types import SemanticType, ColumnSemantic, DataContext
