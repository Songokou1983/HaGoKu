"""HaGoKu Studio 工具层 — 懒加载：handler 内部按需 import，避免冷启动加载全部科学计算栈。"""

# 工具注册表（全局，所有 Agent 共享）
from .registry import AgentTools, Tool, agent_tools
from . import agent_tool_defs  # 导入即完成工具注册

__all__ = [
    # registry
    "AgentTools",
    "Tool",
    "agent_tools",
    # analysis
    "anova",
    "chi_square",
    "correlation",
    "kruskal_wallis",
    "mann_whitney_u",
    "regression",
    "ttest",
    # cleaning
    "CleaningOp",
    "CleaningReport",
    "CleaningStrategy",
    "MissingMechanism",
    "clean_data",
    "detect_missing_mechanism",
    "detect_outliers_iqr",
    "detect_outliers_zscore",
    # data_io
    "compute_data_hash",
    "get_data_info",
    "load_data",
    "load_sql",
    "save_data",
    # diagnostics
    "diagnose_regression",
    "generate_diagnostic_plots",
    # power
    "assess_power_for_data",
    "interpret_effect_size",
    "power_anova",
    "power_correlation",
    "power_regression",
    "power_ttest",
    "required_n_anova",
    "required_n_correlation",
    "required_n_regression",
    "required_n_ttest",
    # profiling
    "generate_full_profile",
    "generate_profile",
    # reporting
    "ReportData",
    "ReportGenerator",
    "ReportSection",
    # visualization
    "create_plot",
]
