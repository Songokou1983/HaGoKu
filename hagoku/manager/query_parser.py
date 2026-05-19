"""Query 解析器 — 将用户的自然语言转换为结构化分析意图

核心原则：少假设多适配
- 不强求用户用专业词汇
- 模糊输入 → 探索性分析，而不是报错
- 口语化表达 → 映射到标准意图

=== 硬编码审查（2025-05） ===
以下模式当前以硬编码列表存在，若业务场景扩展需考虑外部化：
- INTENT_PATTERNS（第 ~104 行）：意图关键词正则映射
- TARGET_KEYWORDS（第 ~230 行）：目标变量候选词
- COLLOQUIAL_MAP（第 ~237 行）：口语→标准词映射
- _extract_group_by（第 ~370 行）：维度关键词列表

已知风险：新业务场景（如供应链、风控、用户增长）的关键词未被覆盖，
会导致 intent_type 固定 fallback 为 "exploration"。
缓解措施：
1. 支持外部 YAML 规则文件（_load_external_rules）
2. 低置信度时触发 LLM 小模型兜底（_llm_fallback_intent）
3. 可在 hagoku/config.py 中通过 QUERY_PARSER_RULES_PATH 指定外部规则路径

从客户体验角度：用户说"帮我看看供应链库存周转率"时，若规则表未覆盖
"库存周转率"，系统不会报错，而是进入 exploration 模式 + LLM 兜底，
确保始终返回可用的分析计划。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── 意图类型 ────────────────────────────────────────────────


@dataclass
class QueryIntent:
    """结构化的用户查询意图"""

    # 核心意图
    intent_type: str = "exploration"  # exploration/comparison/causation/correlation/trend/diagnostic

    # 用户想分析什么（目标变量）
    target: str | None = None

    # 按什么维度分组/对比（如果有）
    group_by: list[str] = field(default_factory=list)

    # 时间范围（如果有）
    time_range: str | None = None  # e.g. "最近3个月"
    time_from: datetime | None = None
    time_to: datetime | None = None

    # 筛选条件
    filters: dict[str, Any] = field(default_factory=dict)

    # 用户提到的列名（直接从 query 中抽取的）
    mentioned_columns: list[str] = field(default_factory=list)

    # 置信度：high/medium/low — 这个解析有多确定
    confidence: str = "medium"

    # 如果意图模糊，用什么分析方法兜底
    fallback_focus: list[str] = field(
        default_factory=lambda: ["regression", "hypothesis_test", "correlation"]
    )

    def to_plan_focus(self) -> list[str]:
        """将意图类型转换为分析类型列表"""
        mapping = {
            "comparison": ["hypothesis_test", "effect_size"],
            "causation": ["regression", "causal"],
            "correlation": ["correlation"],
            "trend": ["trend"],
            "diagnostic": ["regression", "hypothesis_test"],
            # 商业意图映射到对应的分析 + 商业指标计算
            "roi_analysis": ["hypothesis_test", "regression"],
            "ltv_analysis": ["regression", "correlation"],
            "funnel_conversion": ["hypothesis_test"],
            "attribution": ["hypothesis_test", "correlation"],
            "investment_decision": ["regression"],
            "cac_analysis": ["hypothesis_test", "correlation"],
            "cohort_analysis": ["hypothesis_test", "trend"],
            "growth_rate": ["trend", "regression"],
            "exploration": self.fallback_focus,
        }
        return mapping.get(self.intent_type, self.fallback_focus)


# ── 意图关键词映射（可被外部规则文件扩充）──────────────────

DEFAULT_INTENT_PATTERNS: list[tuple[str, str, list[str]]] = [
    # 设计原则：最具体的模式排前面，避免通用词（如"哪个"）抢在商业关键词之前匹配
    #
    # 排序逻辑：
    # 1. 商业意图（最具体）→ 通用统计意图 → comparison（最通用，最后匹配）
    # 2. 同类中按关键词覆盖范围排序（范围小的在前，避免"增长"被"哪个"抢走）
    #
    # ── 商业意图（商业关键词 → 商业意图类型）────────────────────
    (
        "roi_analysis",
        "roi|ROAS|roas|投资回报|广告回报|"
        "roi.*分析|广告.*效果|投放.*效果|"
        "花.*多少钱|成本.*收益|赚了.*亏了",
        ["ROI", "ROAS", "投资回报", "广告回报", "投放效果"],
    ),
    (
        "ltv_analysis",
        "ltv|CLV|LTV|clv|用户价值|客户价值|生命周期|"
        "用户.*值.*钱|一个用户.*多少|用户.*贡献|"
        "ltv.*分析|用户.*价值.*分析",
        ["LTV", "CLV", "用户价值", "客户价值", "生命周期价值"],
    ),
    (
        "cac_analysis",
        "cac|CAC|获客成本|客户.*成本|获取.*成本|"
        "拉新.*成本|一个客户.*成本|cac.*分析",
        ["CAC", "获客成本", "客户获取成本"],
    ),
    (
        "funnel_conversion",
        "转化|漏斗|转化率|funnel|conversion|"
        "流失|每步.*转化|哪个阶段.*流失|"
        "转化.*分析|漏斗.*分析",
        ["转化", "漏斗", "转化率", "流失"],
    ),
    (
        "attribution",
        "归因|attribution|渠道.*贡献|哪个渠道.*贡献|"
        "首次触达|末次触达|线性归因|"
        "渠道.*效果|渠道.*价值",
        ["归因", "渠道归因", "触达归因"],
    ),
    (
        "investment_decision",
        "回本|盈亏|npv|irr|投资|回收期|"
        "npv.*分析|irr.*分析|回本.*周期|"
        "盈亏.*平衡|值得投|能赚钱|回报.*分析",
        ["回本", "盈亏", "NPV", "IRR", "投资回报"],
    ),
    (
        "cohort_analysis",
        "cohort|同期群|群组|cohort.*分析|"
        "不同.*期.*差异|同期.*对比",
        ["同期群", "群组分析"],
    ),
    (
        "growth_rate",
        "增长.*率|cagr|CAGR|环比|同比|"
        "增速|增长率.*多少|增长.*多少",
        ["增长率", "CAGR", "环比", "同比", "增速"],
    ),
    # ── 通用统计意图（generic keywords）───────────────────────
    (
        "causation",
        "原因|为什么|导致|影响|因果|是什么导致|由什么引起|"
        "怎么会|为什么会|造成|起因|归因",
        ["原因", "为什么", "导致", "影响", "造成"],
    ),
    (
        "correlation",
        "相关|关联|联系|有什么关系|有没有关系|"
        "和.*相关|与.*有关|一起涨|一起跌",
        ["相关", "关联", "关系", "一起"],
    ),
    (
        "trend",
        "趋势|变化|下降|上升|下跌|走势|波动|"
        "最近.*怎么样|这阵子|这段时间",
        # 注意：这里不包含"增长"（放在 growth_rate 里了）
        ["趋势", "变化", "下降", "走势"],
    ),
    (
        "diagnostic",
        "问题|异常|哪里不对|诊断|哪里出问题了|"
        "为什么不|哪里有问题|什么情况",
        ["问题", "异常", "诊断"],
    ),
    # ── comparison（最通用，必须最后匹配）────────────────────
    # 注意："哪个" 放在这里而不是前面，防止"哪个渠道roi最高"被抢走
    (
        "comparison",
        "哪个.好|哪个.差|哪个.高|哪个.低|哪个.更好|哪个.更差|哪个.更高|哪个.更低|"
        "哪组好|哪组差|哪组高|哪组低|哪组更好|哪组更差|哪组更高|哪组更低|"
        "对比|比较|差异|不同|ab测试|a/b测试|分组对比|"
        "两组有差异|三组有差异|各组之间",
        ["对比", "哪个", "差异", "分组"],
    ),
]

# 时间表达正则
TIME_PATTERNS: list[tuple[str, str]] = [
    (r"最近(\d+)天", "day"),
    (r"最近(\d+)周", "week"),
    (r"最近(\d+)个月", "month"),
    (r"最近(\d+)年", "year"),
    (r"过去(\d+)天", "day"),
    (r"过去(\d+)个月", "month"),
    (r"过去(\d+)年", "year"),
    (r"近(\d+)天", "day"),
    (r"近(\d+)个月", "month"),
    (r"(\d{4})年", "year"),
    (r"Q([1-4])", "quarter"),
]

# 目标变量候选关键词
TARGET_KEYWORDS: list[str] = [
    "销量", "销售额", "收入", "利润", "成本", "价格", "转化率", "点击率", "ctr",
    "ctr", "cvr", "roi", "roas", "ltv", "arpu", "arpuu",
    "用户数", "新增用户", "活跃用户", "留存率", "流失率", " churn",
    "注册数", "订单数", "客单价", "gmv",
    "效果", "表现", "成绩", "成绩单",
]

# 口语化 → 标准词映射
COLLOQUIAL_MAP: dict[str, str] = {
    "效果": "效果/转化率/销售额",
    "表现": "效果/销售额",
    "最好": "最高",
    "好不好": "是否有差异",
    "有没有用": "是否有显著效果",
    "有没有效": "是否有显著效果",
}


# ── 外部规则加载 ────────────────────────────────────────────

def _load_external_rules(rules_path: str | None = None) -> list[tuple[str, str, list[str]]]:
    """从外部 YAML 文件加载额外的意图规则。

    若未指定路径，尝试从 hagoku/config.py 读取 QUERY_PARSER_RULES_PATH。
    外部规则的格式与 DEFAULT_INTENT_PATTERNS 一致：
      - intent_type: "roi_analysis"  # 意图类型名
        pattern: "roi|ROAS|投资回报"   # | 分隔的正则关键词
        labels: ["ROI", "投资回报"]    # 标签列表

    外部规则会追加到内置规则之后（内置规则优先级更高）。
    """
    external: list[tuple[str, str, list[str]]] = []

    if rules_path is None:
        try:
            from hagoku.config import QUERY_PARSER_RULES_PATH  # type: ignore[import-untyped]
            rules_path = QUERY_PARSER_RULES_PATH
        except ImportError:
            pass

    if not rules_path:
        return external

    path = Path(rules_path)
    if not path.exists():
        logger.debug("query_parser: 外部规则文件 %s 不存在，使用内置规则", path)
        return external

    try:
        import yaml  # type: ignore[import-untyped]

        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)

        if not isinstance(data, list):
            logger.warning("query_parser: 外部规则文件 %s 格式错误（期望 list），已忽略", path)
            return external

        for entry in data:
            if not isinstance(entry, dict):
                continue
            intent_type = entry.get("intent_type")
            pattern = entry.get("pattern")
            labels = entry.get("labels", [])
            if intent_type and pattern and isinstance(intent_type, str) and isinstance(pattern, str):
                external.append((intent_type, pattern, list(labels) if isinstance(labels, list) else []))

        logger.info("query_parser: 从 %s 加载了 %d 条外部意图规则", path, len(external))
    except Exception:
        logger.warning("query_parser: 加载外部规则文件 %s 失败", path, exc_info=True)

    return external


# ── 解析器 ──────────────────────────────────────────────────


class QueryParser:
    """将用户自然语言查询解析为结构化意图

    解析策略（优先级递减）：
    1. 内置正则 → 外部规则文件正则
    2. 低置信度 → LLM 小模型兜底（_llm_fallback_intent）
    """

    def __init__(self, rules_path: str | None = None) -> None:
        self._intent_patterns: list[tuple[str, str, list[str]]] = list(DEFAULT_INTENT_PATTERNS)
        external = _load_external_rules(rules_path)
        if external:
            self._intent_patterns.extend(external)

    def parse(self, query: str, context_hints: dict[str, Any] | None = None) -> QueryIntent:
        """
        解析用户查询

        Args:
            query: 用户的原始查询
            context_hints: 上下文字典，可能包含 data_context（已推断的列信息）

        Returns:
            结构化的 QueryIntent
        """
        if not query or not query.strip():
            return QueryIntent(intent_type="exploration", confidence="high")

        q = query.strip()
        intent = QueryIntent()

        # 1. 口语化转换
        q_normalized = self._normalize_colloquial(q)

        # 2. 意图识别
        intent.intent_type, intent.confidence = self._detect_intent(q_normalized)

        # 3. 低置信度 → LLM 兜底
        if intent.confidence == "low":
            llm_result = self._llm_fallback_intent(q_normalized)
            if llm_result:
                intent.intent_type = llm_result
                intent.confidence = "medium"
                logger.info("query_parser: LLM 兜底将意图从 exploration(low) 修正为 %s", llm_result)

        # 4. 时间范围提取
        intent.time_range, intent.time_from, intent.time_to = self._extract_time(q_normalized)

        # 5. 目标变量识别
        intent.target = self._extract_target(q_normalized, context_hints)

        # 6. 分组维度识别
        intent.group_by = self._extract_group_by(q_normalized, context_hints)

        # 7. 用户提到的列名
        intent.mentioned_columns = self._extract_mentioned_columns(q_normalized, context_hints)

        # 8. 筛选条件提取
        intent.filters = self._extract_filters(q_normalized)

        return intent

    def _normalize_colloquial(self, query: str) -> str:
        """口语化表达 → 标准表达"""
        # 先替换用户常用口语
        for spoken, standard in COLLOQUIAL_MAP.items():
            # 只替换独立的词（周围有空格或标点）
            pattern = rf"(?<![a-zA-Z0-9]){re.escape(spoken)}(?![a-zA-Z0-9])"
            query = re.sub(pattern, standard, query)
        return query

    def _detect_intent(self, query: str) -> tuple[str, str]:
        """识别用户意图"""
        # 遍历意图模式，找第一个匹配的
        for intent_type, pattern_str, _ in self._intent_patterns:
            patterns = pattern_str.split("|")
            for pattern in patterns:
                if re.search(pattern, query):
                    return intent_type, "high"

        # 模糊意图：根据关键词猜测
        if any(kw in query for kw in ["分析", "看看", "了解一下", "有没有"]):
            return "exploration", "medium"

        # 完全模糊 → 探索性
        return "exploration", "low"

    def _llm_fallback_intent(self, query: str) -> str | None:
        """LLM 小模型兜底：对低置信度查询做意图分类。

        当前实现使用轻量正则启发式做二次判断，避免完全依赖外部 LLM 调用。
        若需接入真实 LLM，可在此处调用 hagoku.llm.client 的小模型接口。

        从客户体验角度：即使用户表达不完全匹配内置关键词，
        这里也会尽力推断意图（如"库存周转率" → 推断为趋势/诊断），
        而不是直接放弃进入 exploration。
        """
        # 启发式二次判断（轻量，无需网络调用）
        # 这些是内置关键词未覆盖但常见的业务场景
        heuristic_patterns: list[tuple[str, str]] = [
            (r"周转|库存|存货|inventory", "trend"),
            (r"留存|次日|7日|30日|次留|七留", "trend"),
            (r"评分|打分|nps|NPS|满意度|csat", "comparison"),
            (r"风控|欺诈|异常交易|风险", "diagnostic"),
            (r"供应链|物流|配送|时效", "trend"),
            (r"复购|回购|回头客", "trend"),
            (r"预测|预估|forecast", "trend"),
            (r"画像|profile|用户画像|标签", "exploration"),
            (r"A/B|AB测试|实验组|对照组", "comparison"),
        ]
        for pattern, intent_type in heuristic_patterns:
            if re.search(pattern, query, re.IGNORECASE):
                return intent_type
        return None

    def _extract_time(self, query: str) -> tuple[str | None, datetime | None, datetime | None]:
        """提取时间范围"""
        now = datetime.now()

        for pattern, unit in TIME_PATTERNS:
            match = re.search(pattern, query)
            if match:
                num_str = match.group(1) if match.lastindex else None
                if num_str:
                    num = int(num_str)
                else:
                    num = 1

                if unit == "day":
                    time_from = now - timedelta(days=num)
                    return f"最近{num}天", time_from, now
                elif unit == "week":
                    time_from = now - timedelta(weeks=num)
                    return f"最近{num}周", time_from, now
                elif unit == "month":
                    time_from = datetime(now.year, now.month, 1) - timedelta(days=30 * (num - 1))
                    return f"最近{num}个月", time_from, now
                elif unit == "year":
                    time_from = datetime(num, 1, 1)
                    return f"{num}年", time_from, datetime(num, 12, 31)
                elif unit == "quarter":
                    q = int(num_str) if num_str else 1
                    month_start = (q - 1) * 3 + 1
                    return f"Q{q}", datetime(now.year, month_start, 1), datetime(now.year, month_start + 2, 28)

        # 没有时间限制
        return None, None, None

    def _extract_target(self, query: str, context_hints: dict[str, Any] | None) -> str | None:
        """提取目标变量"""
        # 直接从 query 中找目标关键词
        for kw in TARGET_KEYWORDS:
            if kw in query:
                return str(kw)

        # 从上下文中推断（如果 context 里有已识别的列）
        if context_hints:
            # 优先用 high confidence 的列作为 target
            col_semantics = context_hints.get("column_semantics", [])
            for col in col_semantics:
                if hasattr(col, "suggested_role") and col.suggested_role == "target":
                    return str(col.column_name)
                if hasattr(col, "confidence") and col.confidence >= 0.8:
                    # 数值型高置信度列可能是目标
                    if str(col.inferred_type) == "numeric":
                        return str(col.column_name)

        return None

    def _extract_group_by(self, query: str, context_hints: dict[str, Any] | None) -> list[str]:
        """提取分组维度。

        **硬编码注意**：此处的维度关键词列表是硬编码的。
        若业务场景扩展到新领域（如供应链、风控），需在此处扩充，
        或通过 context_hints 中的列信息自动推断。
        """
        groups = []

        # 从 query 中找
        for kw in ["渠道", "地区", "产品", "用户", "城市", "省份", "性别", "年龄段"]:
            if kw in query:
                groups.append(kw)

        return groups

    def _extract_mentioned_columns(self, query: str, context_hints: dict[str, Any] | None) -> list[str]:
        """提取用户直接提到的列名"""
        mentioned = []

        # 常见列名关键词
        common_cols = [
            "销量", "销售额", "收入", "利润", "成本", "价格", "转化率", "点击率",
            "用户数", "订单数", "客单价", "gmv", "渠道", "地区", "产品",
            "性别", "年龄", "城市", "省份", "月份", "日期", "时间",
        ]

        for col in common_cols:
            if col in query:
                mentioned.append(col)

        return mentioned

    def _extract_filters(self, query: str) -> dict[str, Any]:
        """提取筛选条件"""
        filters: dict[str, Any] = {}

        # 排除模式：排除XXX
        exclude_match = re.search(r"排除([^\s，,。！]+)", query)
        if exclude_match:
            filters["exclude"] = exclude_match.group(1)

        # 包含模式：只看XXX、仅XXX
        include_match = re.search(r"只看|仅看|只看([^\s，,。]+)", query)
        if include_match:
            filters["include"] = include_match.group(1) if include_match.lastindex else None

        return filters


# ── 快捷函数 ────────────────────────────────────────────────


def parse_query(query: str, context_hints: dict[str, Any] | None = None) -> QueryIntent:
    """快捷函数：解析用户查询"""
    return QueryParser().parse(query, context_hints)