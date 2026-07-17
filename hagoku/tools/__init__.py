"""HaGoKu Studio 工具层"""

# 工具注册表（全局，所有 Agent 共享）
from .registry import AgentTools, Tool, agent_tools
from . import agent_tool_defs  # 导入即完成工具注册

from .analysis import (
    anova,
    chi_square,
    correlation,
    kruskal_wallis,
    mann_whitney_u,
    regression,
    ttest,
)
from .business import (
    attribution_analysis,
    calc_break_even,
    calc_cac,
    calc_cagr,
    calc_growth_rate,
    calc_irr,
    calc_ltv,
    calc_ltv_cac_ratio,
    calc_npv,
    calc_payback_period,
    calc_roas,
    calc_roi,
    funnel_analysis,
)
from .cleaning import (
    CleaningOp,
    CleaningReport,
    CleaningStrategy,
    MissingMechanism,
    clean_data,
    detect_missing_mechanism,
    detect_outliers_iqr,
    detect_outliers_zscore,
)
from .data_io import (
    compute_data_hash,
    get_data_info,
    load_data,
    load_sql,
    save_data,
)
from .diagnostics import (
    diagnose_regression,
    generate_diagnostic_plots,
)
from .power_analysis import (
    assess_power_for_data,
    interpret_effect_size,
    power_anova,
    power_correlation,
    power_regression,
    power_ttest,
    required_n_anova,
    required_n_correlation,
    required_n_regression,
    required_n_ttest,
)
from .profiling import (
    generate_full_profile,
    generate_profile,
)
from .reporting import (
    ReportData,
    ReportGenerator,
    ReportSection,
)
from .visualization import create_plot

__all__ = [
    # analysis
    "anova",
    "chi_square",
    "correlation",
    "kruskal_wallis",
    "mann_whitney_u",
    "regression",
    "ttest",
    # business
    "attribution_analysis",
    "calc_break_even",
    "calc_cac",
    "calc_cagr",
    "calc_growth_rate",
    "calc_irr",
    "calc_ltv",
    "calc_ltv_cac_ratio",
    "calc_npv",
    "calc_payback_period",
    "calc_roi",
    "calc_roas",
    "funnel_analysis",
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
