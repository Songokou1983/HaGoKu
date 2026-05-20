"""HaGoKu Studio 分析方法注册表 — 插件化架构

设计原则：
- 新增分析方法 = 注册到表，不改核心代码
- 每个方法自描述：回答什么问题、接受什么数据、返回什么结构
- 方法可组合、可替换、可禁用

用法：
```python
from hagoku.tools.analysis_registry import analysis_registry, AnalysisMethod

@analysis_registry.register
def my_new_analysis(df, context, params):
    return {"test": "my_analysis", "result": "..."}
# 元数据通过装饰器参数或函数属性注入
```

或在 registry.add() 时传入元数据：
```python
analysis_registry.add(
    name="my_analysis",
    func=my_analysis_func,
    keywords=["新问题类型"],
    supported_types=["numeric", "categorical"],
    returns_schema={...},
    description="做什么分析"
)
```
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import pandas as pd


@dataclass
class AnalysisMethod:
    """
    分析方法元数据 + 执行函数
    """
    name: str
    func: Callable[[pd.DataFrame, Any, dict[str, Any]], dict[str, Any] | None]
    keywords: list[str] = field(default_factory=list)
    description: str = ""
    supported_types: list[str] = field(default_factory=list)  # ["numeric", "categorical", "time_series", "business"]
    requires_columns: list[str] = field(default_factory=list)  # 需要的列类型 ["numeric", "categorical"]
    min_rows: int = 0
    returns_schema: dict[str, Any] | None = None
    tags: list[str] = field(default_factory=list)  # ["statistical", "business", "causal", "diagnostic"]
    enabled: bool = True

    def __call__(self, df: pd.DataFrame, context: Any, params: dict[str, Any]) -> dict[str, Any] | None:
        """执行分析方法（带异常处理）"""
        if not self.enabled:
            return None
        if len(df) < self.min_rows:
            return None
        try:
            return self.func(df, context, params)
        except Exception as e:
            return {"error": str(e), "method": self.name}


@dataclass
class RegistryResult:
    """注册表查询结果"""
    methods: list[AnalysisMethod]
    coverage: dict[str, bool]  # 关键词覆盖情况
    suggestions: list[str]  # 缺失能力的提示


# ── 注册表 ──────────────────────────────────────────────────


class AnalysisRegistry:
    """
    分析方法中心注册表

    插件化架构核心：
    - register() / add() 添加方法
    - discover() 自动发现某个目录下的方法
    - find() 根据意图查找适用方法
    - execute() 执行并组合结果
    """

    def __init__(self) -> None:
        self._methods: dict[str, AnalysisMethod] = {}
        self._keywords_index: dict[str, list[str]] = {}  # keyword → [method_names]

    def register(
        self,
        name: str | None = None,
        *,
        keywords: list[str] | None = None,
        description: str = "",
        supported_types: list[str] | None = None,
        requires_columns: list[str] | None = None,
        min_rows: int = 0,
        returns_schema: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> Callable:
        """
        装饰器注册方法

        @analysis_registry.register(
            name="ttest",
            keywords=["对比", "差异", "哪组"],
            description="t 检验",
        )
        def do_ttest(...): ...
        """
        def decorator(func: Callable) -> Callable:
            method_name = name or func.__name__
            method = AnalysisMethod(
                name=method_name,
                func=func,
                keywords=keywords or [],
                description=description or func.__doc__ or "",
                supported_types=supported_types or [],
                requires_columns=requires_columns or [],
                min_rows=min_rows,
                returns_schema=returns_schema,
                tags=tags or [],
            )
            self.add(method)
            return func
        return decorator

    def add(self, method: AnalysisMethod) -> None:
        """手动注册方法"""
        self._methods[method.name] = method
        for kw in method.keywords:
            if kw not in self._keywords_index:
                self._keywords_index[kw] = []
            self._keywords_index[kw].append(method.name)

    def add_from_module(self, module: Any, prefix: str = "") -> int:
        """
        从模块中批量注册函数

        扫描模块中所有名为 do_xxx 或以 _analysis_ 开头的函数，
        自动注册到注册表

        Args:
            module: Python 模块对象
            prefix: 注册名前缀

        Returns:
            注册数量
        """
        import inspect

        count = 0
        for name, obj in inspect.getmembers(module, inspect.isfunction):
            if name.startswith("do_") or name.startswith("_analysis_"):
                method_name = (prefix + name) if prefix else name
                if method_name not in self._methods:
                    doc = inspect.getdoc(obj) or ""
                    method = AnalysisMethod(
                        name=method_name,
                        func=obj,
                        description=doc.split("\n")[0] if doc else "",
                    )
                    self.add(method)
                    count += 1
        return count

    def find(
        self,
        intent: str,
        context: Any | None = None,
        df: pd.DataFrame | None = None,
        tags: list[str] | None = None,
        exclude: list[str] | None = None,
    ) -> list[AnalysisMethod]:
        """
        根据意图查找适用的分析方法

        Args:
            intent: 用户意图关键词
            context: 数据上下文
            df: 数据（用于检查数据量）
            tags: 只返回带这些标签的方法
            exclude: 排除的方法名

        Returns:
            适用的方法列表（按相关性排序）
        """
        matched: dict[str, int] = {}  # method_name → score
        exclude = exclude or []

        # 1. 精确关键词匹配
        for kw, method_names in self._keywords_index.items():
            if kw in intent:
                for mname in method_names:
                    if mname not in exclude and mname not in matched:
                        matched[mname] = 10

        # 2. 标签过滤
        if tags:
            for mname, method in self._methods.items():
                if mname in matched and tags:
                    if not any(t in method.tags for t in tags):
                        matched[mname] -= 5

        # 3. 排序
        results = [
            self._methods[mname]
            for mname, score in sorted(matched.items(), key=lambda x: x[1], reverse=True)
            if mname not in exclude
            and self._methods[mname].enabled
            and (df is None or len(df) >= self._methods[mname].min_rows)
        ]
        return results

    def execute(
        self,
        intent: str,
        df: pd.DataFrame,
        context: Any,
        params: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        max_methods: int = 5,
    ) -> list[dict[str, Any]]:
        """
        根据意图执行最相关的分析方法

        Args:
            intent: 用户意图
            df: 数据
            context: 数据上下文
            params: 额外参数
            tags: 只执行带这些标签的方法
            max_methods: 最多执行几个方法

        Returns:
            各方法的结果列表
        """
        methods = self.find(intent, context, df, tags)
        methods = methods[:max_methods]
        params = params or {}

        results = []
        for method in methods:
            result = method(df, context, params)
            if result and "error" not in result:
                results.append(result)

        return results

    def get(self, name: str) -> AnalysisMethod | None:
        """按名称获取方法"""
        return self._methods.get(name)

    def list_all(self, enabled_only: bool = True) -> list[AnalysisMethod]:
        """列出所有方法"""
        methods = list(self._methods.values())
        if enabled_only:
            methods = [m for m in methods if m.enabled]
        return sorted(methods, key=lambda m: m.name)

    def enable(self, name: str) -> bool:
        """启用方法"""
        if name in self._methods:
            self._methods[name].enabled = True
            return True
        return False

    def disable(self, name: str) -> bool:
        """禁用方法"""
        if name in self._methods:
            self._methods[name].enabled = False
            return True
        return False

    def register_bundled(self) -> None:
        """
        注册 HaGoKu Studio 内置的所有分析方法

        这个方法初始化注册表，包含所有内置分析能力。
        新插件可以通过覆写或扩展此方法来添加能力。
        """
        from . import analysis as analysis_module
        from . import business as business_module

        # 注册统计方法
        self.add_from_module(analysis_module)

        # 注册商业方法
        self.add_from_module(business_module)

        # ── 显式注册关键方法（带完整元数据）────────────

        # t 检验
        self._register_statistical(
            "ttest",
            analysis_module.ttest,
            keywords=["对比", "差异", "哪组", "t检验", "t test"],
            tags=["statistical", "comparison"],
        )

        # ANOVA
        self._register_statistical(
            "anova",
            analysis_module.anova,
            keywords=["多组", "多组对比", "方差分析", "anova"],
            tags=["statistical", "comparison"],
        )

        # Mann-Whitney U
        self._register_statistical(
            "mann_whitney",
            analysis_module.mann_whitney_u,
            keywords=["非参数", "正态", "mann-whitney"],
            tags=["statistical", "comparison"],
        )

        # Kruskal-Wallis
        self._register_statistical(
            "kruskal_wallis",
            analysis_module.kruskal_wallis,
            keywords=["非参数多组", "kruskal"],
            tags=["statistical", "comparison"],
        )

        # 卡方检验
        self._register_statistical(
            "chi_square",
            analysis_module.chi_square,
            keywords=["卡方", "chi", "类别", "比例"],
            tags=["statistical", "comparison"],
        )

        # 相关分析
        self._register_statistical(
            "correlation",
            analysis_module.correlation,
            keywords=["相关", "correlation", "关联", "一起涨", "一起跌"],
            tags=["statistical", "correlation"],
        )

        # 回归
        self._register_statistical(
            "regression",
            analysis_module.regression,
            keywords=["回归", "预测", "regression", "哪些因素", "影响"],
            tags=["statistical", "regression", "causal"],
        )

        # ROI
        self._register_business(
            "calc_roi",
            business_module.calc_roi,
            keywords=["roi", "投资回报", "ROI"],
            tags=["business", "financial"],
        )

        # ROAS
        self._register_business(
            "calc_roas",
            business_module.calc_roas,
            keywords=["roas", "ROAS", "广告回报", "广告效果"],
            tags=["business", "advertising"],
        )

        # LTV
        self._register_business(
            "calc_ltv",
            business_module.calc_ltv,
            keywords=["ltv", "LTV", "用户价值", "生命周期", "clv", "CLV"],
            tags=["business", "user"],
        )

        # CAC
        self._register_business(
            "calc_cac",
            business_module.calc_cac,
            keywords=["cac", "CAC", "获客成本", "拉新成本"],
            tags=["business", "user"],
        )

        # 回本周期
        self._register_business(
            "calc_payback",
            business_module.calc_payback_period,
            keywords=["回本", "回收期", "payback"],
            tags=["business", "financial"],
        )

        # NPV
        self._register_business(
            "calc_npv",
            business_module.calc_npv,
            keywords=["npv", "NPV", "净现值"],
            tags=["business", "financial"],
        )

        # IRR
        self._register_business(
            "calc_irr",
            business_module.calc_irr,
            keywords=["irr", "IRR", "内部收益率"],
            tags=["business", "financial"],
        )

        # 盈亏平衡
        self._register_business(
            "calc_break_even",
            business_module.calc_break_even,
            keywords=["盈亏", "break-even", "平衡点"],
            tags=["business", "financial"],
        )

        # CAGR
        self._register_business(
            "calc_cagr",
            business_module.calc_cagr,
            keywords=["cagr", "CAGR", "复合增长", "年增长"],
            tags=["business", "growth"],
        )

        # 归因
        self._register_business(
            "attribution",
            business_module.attribution_analysis,
            keywords=["归因", "attribution", "渠道贡献", "触达"],
            tags=["business", "attribution"],
        )

        # 漏斗
        self._register_business(
            "funnel",
            business_module.funnel_analysis,
            keywords=["漏斗", "转化", "funnel", "转化率", "流失"],
            tags=["business", "funnel"],
        )

    def _register_statistical(
        self,
        name: str,
        func: Callable,
        keywords: list[str],
        tags: list[str],
    ) -> None:
        self.add(AnalysisMethod(
            name=name,
            func=func,
            keywords=keywords,
            tags=tags,
            description=func.__doc__.split("\n")[0] if func.__doc__ else name,
        ))

    def _register_business(
        self,
        name: str,
        func: Callable,
        keywords: list[str],
        tags: list[str],
    ) -> None:
        self.add(AnalysisMethod(
            name=name,
            func=func,
            keywords=keywords,
            tags=tags,
            description=func.__doc__.split("\n")[0] if func.__doc__ else name,
        ))

    def summary(self) -> dict[str, Any]:
        """注册表概览"""
        all_methods = self.list_all()
        by_tag: dict[str, int] = {}
        for m in all_methods:
            for t in m.tags:
                by_tag[t] = by_tag.get(t, 0) + 1
        return {
            "total_methods": len(all_methods),
            "by_tag": by_tag,
            "methods": [m.name for m in all_methods],
        }


# ── 全局单例 ──────────────────────────────────────────────


analysis_registry = AnalysisRegistry()
# 注册内置方法
analysis_registry.register_bundled()


# ── 扩展点：用户自定义分析方法 ─────────────────────────────


def load_plugins(registry: AnalysisRegistry | None = None) -> AnalysisRegistry:
    """
    加载用户自定义分析方法插件

    扩展点：用户可在 ~/.hagoku/plugins/ 目录下放置 Python 文件，
    HaGoKu Studio 会自动扫描并注册其中的分析方法。

    插件文件命名规范：*_plugin.py
    插件中每个分析函数名为 do_xxx

    示例：~/.hagoku/plugins/marketing_plugin.py
    ```python
    from hagoku.tools.analysis_registry import analysis_registry

    @analysis_registry.register(
        name="marketing_mix",
        keywords=["营销组合", "marketing mix", "media mix"],
        tags=["business", "marketing"],
    )
    def do_marketing_mix(df, context, params):
        # 用户自定义分析逻辑
        return {"metric": "marketing_mix", ...}
    ```
    """
    import importlib.util
    from pathlib import Path

    reg = registry or analysis_registry
    plugin_dir = Path.home() / ".hagoku" / "plugins"

    if not plugin_dir.exists():
        return reg

    count = 0
    for plugin_file in plugin_dir.glob("*_plugin.py"):
        spec = importlib.util.spec_from_file_location(plugin_file.stem, plugin_file)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(module)
                n = reg.add_from_module(module, prefix=f"{plugin_file.stem}_")
                count += n
            except Exception:
                pass  # 静默跳过加载失败的插件

    return reg
