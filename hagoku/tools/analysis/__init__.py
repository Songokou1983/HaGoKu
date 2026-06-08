# Re-export all analysis functions to maintain backward compatibility
# (from hagoku.tools.analysis import ttest)

from .config import set_analysis_config

from .comparison import ttest, anova, mann_whitney_u, kruskal_wallis, chi_square
from .correlation import correlation
from .regression import regression
from .diagnostics import check_test_assumptions
from .advanced import cross_validate, multiple_comparison_correction, interaction_analysis

__all__ = [
    "set_analysis_config",
    "ttest", "anova", "mann_whitney_u", "kruskal_wallis", "chi_square",
    "correlation", "regression", "check_test_assumptions",
    "cross_validate", "multiple_comparison_correction", "interaction_analysis",
]
