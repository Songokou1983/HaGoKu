"""HaGoKu 工具层"""

from .analysis import (
    anova,
    chi_square,
    correlation,
    kruskal_wallis,
    mann_whitney_u,
    regression,
    ttest,
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
    suggest_cleaning_strategy,
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
from .profiling import (
    generate_full_profile,
    generate_profile,
    suggest_column_roles,
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
    # cleaning
    "CleaningOp",
    "CleaningReport",
    "CleaningStrategy",
    "MissingMechanism",
    "clean_data",
    "detect_missing_mechanism",
    "detect_outliers_iqr",
    "detect_outliers_zscore",
    "suggest_cleaning_strategy",
    # data_io
    "compute_data_hash",
    "get_data_info",
    "load_data",
    "load_sql",
    "save_data",
    # diagnostics
    "diagnose_regression",
    "generate_diagnostic_plots",
    # profiling
    "generate_full_profile",
    "generate_profile",
    "suggest_column_roles",
    # reporting
    "ReportData",
    "ReportGenerator",
    "ReportSection",
    # visualization
    "create_plot",
]
