"""Doctrine 合规测试 — 机器化的"零硬编码"守门人

每个 PR 提交前必须跑过此文件。如果其中任一断言变红，
意味着你（AI 实现者）违反了 HaGoKu 项目的核心铁律。

参考：
  - AGENTS.md §「你必须每次提交前跑的命令」
  - PROJECT.md §「代码层合法动作清单」
  - PROJECT.md §「通道完备性十律」

本测试不是"防止所有硬编码"——硬编码的伪装无穷尽。
但它能拦下最常见的 4 类模式，让 AI 实现者无法装作没看见。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

HAGOKU_ROOT = Path(__file__).resolve().parent.parent / "hagoku"


# ─────────────────────────────────────────────────────────────────────────────
# 工具：枚举受检文件，排除生成物 / 备份 / 兼容层
# ─────────────────────────────────────────────────────────────────────────────

# F-057 修复：扫全仓 hagoku/，不再限定子目录白名单。
# 原 _DOCTRINE_SUBDIRS 只覆盖 5/14 子目录（"memory" 死指向不存在目录），
# 漏了 storage/tools/context/llm/observability 等 P0/P1 高发地。
_DOCTRINE_SUBDIRS = ("agents", "manager", "api", "guardrails", "storage", "context", "llm", "observability", "tools", "services", "repository", "memory")

# 已知合法例外文件（纯 IO / 纯计算 / 不含业务语义判断的模块）
_EXEMPT_FILES: set[str] = {
    "__init__.py",          # 包初始化，只含 import
    "log.py",               # 纯日志配置
    "config.py",            # 纯配置加载
}


def _scanned_files() -> list[Path]:
    out: list[Path] = []
    for sub in _DOCTRINE_SUBDIRS:
        d = HAGOKU_ROOT / sub
        if not d.exists():
            continue
        for p in d.rglob("*.py"):
            name = p.name
            # 跳过备份、缓存、空 __init__
            if "UI_CHANGELOG_backup" in name or "__pycache__" in str(p):
                continue
            if name in _EXEMPT_FILES:
                continue
            out.append(p)
    return out


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# 守门 1：业务关键词字面量列表
# ─────────────────────────────────────────────────────────────────────────────
#
# 业务概念（"收入"、"销售额"、"营收"、"客流量"）的同义判断必须由 LLM 完成。
# 代码以 list/tuple/set 形式枚举多个业务关键词，等同于"我替 LLM 做语义分类"。
# 工具 description 中的中文字符串属于 LLM 教学材料，不在此范围。

# 业务关键词集合 — 任何 .py 文件中以字符串字面量形式同时出现 ≥2 个，视为违规
_BUSINESS_KEYWORDS = [
    "收入", "营收", "销售额", "销售", "客流", "客流量", "订单",
    "毛利", "利润", "成本", "周次", "店铺", "门店",
]


def test_doctrine_无业务关键词字面量集合() -> None:
    """禁止在受检代码中以字面量形式同时枚举 ≥2 个业务关键词。

    若必须传给 LLM 一组业务概念示例，请写在 system prompt 字符串里
    （**整段中文 prompt** 不算违规——单一字符串中包含多个业务词是 LLM 教学）。
    本检查只盯紧 list/tuple/set/dict 形式的枚举。
    """
    violations: list[str] = []

    for path in _scanned_files():
        try:
            tree = ast.parse(_read(path), filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            # 只看 List / Tuple / Set 字面量
            if not isinstance(node, (ast.List, ast.Tuple, ast.Set)):
                continue
            string_consts = [
                e.value for e in node.elts
                if isinstance(e, ast.Constant) and isinstance(e.value, str)
            ]
            if not string_consts:
                continue
            hits = [s for s in string_consts if s in _BUSINESS_KEYWORDS]
            if len(hits) >= 2:
                rel = path.relative_to(HAGOKU_ROOT)
                line = getattr(node, "lineno", "?")
                violations.append(f"{rel}:{line}  字面量集合含业务关键词 {hits}")

    assert not violations, (
        "\n违反【零硬编码】：业务关键词字面量集合（业务语义判断应由 LLM 完成）\n"
        "如何修复：删除该集合。LLM 拿到分析目标和数据后自己会判断，不需要代码替它做业务分类。\n"
        "  ----  违规位置  ----\n"
        + "\n".join(f"  {v}" for v in violations)
    )


# ─────────────────────────────────────────────────────────────────────────────
# 守门 2：中文语义正则
# ─────────────────────────────────────────────────────────────────────────────
#
# 例：re.search(r"收入|营收|销售", text) — 用代码识别业务概念变体，是 LLM 的活。
# 单一中文短语字面量匹配（如 r"是"）作为分隔符切割勉强允许，但用 | 连接多个业务
# 短语就是语义分类。

_CHINESE_ALT_REGEX_PATTERN = re.compile(
    r"""re\.(?:search|match|findall|finditer|sub|split|compile)\s*\(
        \s*r?["']            # 正则字符串开始
        [^"']*               # 任意前缀
        [\u4e00-\u9fa5]+     # 中文短语 1
        \|                   # 或
        [^"']*[\u4e00-\u9fa5]+  # 中文短语 2 / 更多
    """,
    re.VERBOSE,
)


def test_doctrine_无中文语义正则分支() -> None:
    """禁止用 re.* 配合带 `|` 的中文短语做语义分类。

    `re.search(r"收入|营收|销售", text)` → 让 LLM 判断业务概念。
    `re.split(r"是|代表|意为", text)` → 同上，自然语言动词分支。
    """
    violations: list[str] = []
    for path in _scanned_files():
        text = _read(path)
        for i, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if _CHINESE_ALT_REGEX_PATTERN.search(line):
                rel = path.relative_to(HAGOKU_ROOT)
                violations.append(f"{rel}:{i}  {stripped[:120]}")

    assert not violations, (
        "\n违反【零硬编码】：中文语义正则分支（自然语言概念分类应由 LLM 完成）\n"
        "如何修复：删除该正则，把识别任务交给 LLM，参数通过 tool schema 落地。\n"
        "  ----  违规位置  ----\n"
        + "\n".join(f"  {v}" for v in violations)
    )


# ─────────────────────────────────────────────────────────────────────────────
# 守门 3：中文字符串值的 if-elif 分支链
# ─────────────────────────────────────────────────────────────────────────────
#
# 例：
#   if intent == "预测": method = "regression"
#   elif intent == "对比": method = "ttest"
#   elif intent == "趋势": method = "timeseries"
# 这是把"用户意图分类"硬编码进代码——本应由 LLM 看 prompt 后调对应工具。

_CHINESE_RE = re.compile(r"[\u4e00-\u9fa5]")


def _is_chinese_str_compare(node: ast.AST) -> bool:
    """判断一个比较节点是否在比较"某变量 == '中文字符串'"。"""
    if not isinstance(node, ast.Compare):
        return False
    if len(node.ops) != 1 or not isinstance(node.ops[0], (ast.Eq, ast.In)):
        return False
    for cand in node.comparators:
        if isinstance(cand, ast.Constant) and isinstance(cand.value, str):
            if _CHINESE_RE.search(cand.value):
                return True
        # `x in ("中文1", "中文2")` 也算
        if isinstance(cand, (ast.Tuple, ast.List, ast.Set)):
            for e in cand.elts:
                if (isinstance(e, ast.Constant) and isinstance(e.value, str)
                        and _CHINESE_RE.search(e.value)):
                    return True
    return False


def test_doctrine_无中文字符串if_elif分支链() -> None:
    """禁止 if x == "中文" elif x == "另一中文" 形式的语义分类分支链（≥3 分支）。

    这是把"用户意图分类"硬接管。LLM 主导原则下，分类应由 LLM 调对应 tool 落地。
    """
    violations: list[str] = []

    for path in _scanned_files():
        try:
            tree = ast.parse(_read(path), filename=str(path))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.If):
                continue
            # 数 if + elif 链长度
            chain_count = 0
            cur: ast.If | None = node
            while isinstance(cur, ast.If):
                if _is_chinese_str_compare(cur.test):
                    chain_count += 1
                # 看 elif（即 orelse 是单 If）
                if len(cur.orelse) == 1 and isinstance(cur.orelse[0], ast.If):
                    cur = cur.orelse[0]
                else:
                    break
            if chain_count >= 3:
                rel = path.relative_to(HAGOKU_ROOT)
                violations.append(
                    f"{rel}:{node.lineno}  if/elif 链含 {chain_count} 个中文字符串分支"
                )

    assert not violations, (
        "\n违反【零硬编码】：中文字符串 if/elif 语义分类分支链\n"
        "如何修复：删除分支链，让 LLM 通过 tool_call 表达意图，代码 dispatch tool 调用。\n"
        "  ----  违规位置  ----\n"
        + "\n".join(f"  {v}" for v in violations)
    )


# ─────────────────────────────────────────────────────────────────────────────
# 守门 4：名义 LLM 实则规则的函数
# ─────────────────────────────────────────────────────────────────────────────
#
# 函数名以 _infer_ / _detect_ / _classify_ / _understand_ / _recognize_ 开头，
# 暗示了"语义推断"。这类函数体内必须出现 LLM 客户端调用关键词。
# 否则属于"假装在调用 LLM 实则跑规则"——隐性硬编码的高发区。

_LLM_CALL_MARKERS = (
    "chat.completions.create",
    "create_raw_client",
    "create_llm_client",
    "instructor",
    "llm_client",  # 参数名出现也算"通过外部传入 LLM"
    "self._llm_client",
)

_SEMANTIC_FUNC_PREFIXES = (
    "_infer_",
    "_detect_",
    "_classify_",
    "_understand_",
    "_recognize_",
    "_interpret_",
)


def test_doctrine_语义函数必须含LLM调用标记() -> None:
    """函数名以 _infer_/_detect_/_classify_/... 开头时，函数体或参数表必须含 LLM 标记。

    若你想写"_infer_xxx"但不想调 LLM，请改名为：
      - _compute_xxx（纯计算）
      - _resolve_xxx（机械映射）
      - _parse_xxx（结构化解析）
    保留 _infer_ 名而不调 LLM 是欺骗代码读者的高发硬编码模式。
    """
    violations: list[str] = []

    for path in _scanned_files():
        try:
            tree = ast.parse(_read(path), filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.name.startswith(_SEMANTIC_FUNC_PREFIXES):
                continue
            try:
                src = ast.unparse(node)
            except Exception:
                continue
            if any(marker in src for marker in _LLM_CALL_MARKERS):
                continue
            rel = path.relative_to(HAGOKU_ROOT)
            key = f"{rel}::{node.name} (line {node.lineno})"
            if key in _KNOWN_SEMANTIC_FUNC_VIOLATIONS:
                continue  # F-057 扩展扫描范围后发现的历史债务
            violations.append(key)

    assert not violations, (
        "\n违反【零硬编码】：函数名暗示 LLM 推断但内部无 LLM 调用\n"
        "如何修复：要么真的调 LLM；要么改名为 _compute_/_resolve_/_parse_ 表明纯运算。\n"
        "若是历史债务，加入 _KNOWN_SEMANTIC_FUNC_VIOLATIONS 白名单。\n"
        "  ----  违规位置  ----\n"
        + "\n".join(f"  {v}" for v in violations)
    )


# ─────────────────────────────────────────────────────────────────────────────
# 守门 5（防御性）：兜底默认值的常见反模式（轻量启发式）
# ─────────────────────────────────────────────────────────────────────────────
#
# 例：`except Exception: return []`、`except: return None` 紧跟 LLM 调用——
# 这是路径 1（应 raise RuntimeError）/路径 3（应写 _last_understanding_failure）的违规。
# 这条检查可能误伤——故只在 LLM 调用上下文附近触发。
#
# 历史债务白名单：仓库中已存在的 5 处违规，待 docs/plans/doctrine-violations-cleanup.md
# 推进修复后从此清单移除。新增任何违规会立即被本测试拦下。

_KNOWN_LLM_EXCEPT_VIOLATIONS: set[str] = set()

# F-057 扩展扫描范围后发现的预存违规（纯计算函数用 _detect_/_infer_ 前缀但不调 LLM）。
# 待后续改名（_detect_→_compute_ / _infer_→_resolve_）后从此清单移除。
_KNOWN_SEMANTIC_FUNC_VIOLATIONS: set[str] = {
    "tools/diagnostics.py::_detect_residual_pattern (line 145)",
    "tools/profiling.py::_infer_type (line 175)",
}

_LLM_CALL_HINT_LINES = re.compile(
    r"chat\.completions\.create|create_raw_client"
)


def test_doctrine_LLM调用except块不得静默吞() -> None:
    """LLM 调用所在函数若含 `except ...: return []` / `return None` 而无 raise / 未理解信号，
    属于路径 1/路径 3 的违规——必须 raise RuntimeError 或写 _last_understanding_failure。
    """
    violations: list[str] = []
    for path in _scanned_files():
        text = _read(path)
        if not _LLM_CALL_HINT_LINES.search(text):
            continue
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError:
            continue

        for func in ast.walk(tree):
            if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            try:
                func_src = ast.unparse(func)
            except Exception:
                continue
            if not _LLM_CALL_HINT_LINES.search(func_src):
                continue

            for handler in ast.walk(func):
                if not isinstance(handler, ast.ExceptHandler):
                    continue
                try:
                    h_src = ast.unparse(handler)
                except Exception:
                    continue

                # 合法应对：raise RuntimeError 或写未理解信号
                legal = (
                    "raise" in h_src
                    or "_last_understanding_failure" in h_src
                    or "RuntimeError" in h_src
                )
                if legal:
                    continue

                # 违规模式：直接 return 空值 / None
                bad = re.search(
                    r"return\s+(?:\[\]|\{\}|None|''|\"\")",
                    h_src,
                )
                if bad:
                    rel = path.relative_to(HAGOKU_ROOT)
                    key = f"{rel}::{func.name}:{handler.lineno}"
                    if key in _KNOWN_LLM_EXCEPT_VIOLATIONS:
                        continue  # 历史债务白名单豁免
                    violations.append(
                        f"{key}  静默返回 {bad.group(0)}"
                    )

    assert not violations, (
        "\n违反【代码层合法动作清单】：LLM 调用 except 块静默吞失败\n"
        "如何修复：\n"
        "  - LLM 不可达 → raise RuntimeError(...)（路径 1）\n"
        "  - LLM 给出无效输出 → ctx['_last_understanding_failure'] = {...}（路径 3）\n"
        "若是已知历史债务，请加入 _KNOWN_LLM_EXCEPT_VIOLATIONS（同时记入\n"
        "docs/plans/doctrine-violations-cleanup.md 安排修复）。\n"
        "  ----  违规位置  ----\n"
        + "\n".join(f"  {v}" for v in violations)
    )


# ─────────────────────────────────────────────────────────────────────────────
# 守门 5b：LLM 模块 except 块不得构造"假响应"对象
# ─────────────────────────────────────────────────────────────────────────────
#
# 守门 5 只查 `return <空字面量>`（`[]` / `{}` / `None` / `''` / `""`），
# 但 silent fallback 经常升级为"构造一个看起来合理的假响应"——
# 例：`return QueryIntent(intent_type="exploration", confidence="low")`。
# 这种"假响应"比空值更隐蔽：用户以为 AI 答了一个低置信度的 fallback，
# 实际 AI 没答。
#
# 检测双条件：
#   1. except handler 含 LLM-shaped 字段赋值（如 `intent_type=`, `confidence=`）
#   2. except handler 出现构造调用（`return ClassName(...)` 或 `return self.method(...)`）
# 只在 LLM 模块（模块内有任何 LLM 调用）检查。
#
# 合规例外（带 fallback 标记的）：
#   - Scribe.recover_field_descriptions 用 `_scribe_fallback=True` 标记占位
#   - Cleaner 顶层 except 用 `bias_risk="high" + bias_risk_reason=str(e)` 暴露
#   - Agent 的 `_done()` / `ReportData(...)` 是 agent 自己的返回状态，不是 LLM 假响应
#   - `Path(...)` / `OpenAI(...)` 是 stdlib/external 客户端对象，不是响应

# LLM-shaped 字段名（出现这些 = 构造的是 LLM 响应形状的对象）
_FAKE_RESPONSE_FIELDS = (
    "intent_type", "confidence", "refine_type", "analysis_focus",
    "guidance", "raw_text", "target", "operations", "strategy",
    "verdict", "approach", "method",
)
_FAKE_FIELD_PATTERN = re.compile(
    r"\b(?:" + "|".join(_FAKE_RESPONSE_FIELDS) + r")\s*="
)
_FAKE_CONSTRUCTOR_PATTERN = re.compile(
    r"return\s+(?:[A-Z][A-Za-z0-9_]*\s*\(|self\._?\w+\s*\()"
)


def test_doctrine_LLM模块except块不得构造假响应() -> None:
    """守门 5b：扫描所有 LLM 模块的 except handler，禁止构造 LLM-shaped 假响应。

    双条件检测：
      1. except handler 含 LLM-shaped 字段赋值（最隐蔽的 fake response 特征）
      2. except handler 同时出现构造调用（`return ClassName(...)` 或 `self.method(...)`）

    与守门 5 互补：5 查 `return <空字面量>`，本测试查"看起来像 LLM 响应"的构造。
    """
    violations: list[str] = []
    for path in _scanned_files():
        text = _read(path)
        if not _LLM_CALL_HINT_LINES.search(text):
            continue
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError:
            continue

        for func in ast.walk(tree):
            if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for handler in ast.walk(func):
                if not isinstance(handler, ast.ExceptHandler):
                    continue
                try:
                    h_src = ast.unparse(handler)
                except Exception:
                    continue

                # 合法应对：raise RuntimeError 或写未理解信号
                legal = (
                    "raise" in h_src
                    or "_last_understanding_failure" in h_src
                    or "RuntimeError" in h_src
                )
                if legal:
                    continue

                # 条件 1：含 LLM-shaped 字段
                if not _FAKE_FIELD_PATTERN.search(h_src):
                    continue
                # 条件 2：含构造调用
                m = _FAKE_CONSTRUCTOR_PATTERN.search(h_src)
                if not m:
                    continue

                rel = path.relative_to(HAGOKU_ROOT)
                key = f"{rel}::{func.name}:{handler.lineno}"
                if key in _KNOWN_LLM_EXCEPT_VIOLATIONS:
                    continue
                violations.append(
                    f"{key}  except 块构造 LLM-shaped 假响应：{m.group(0).strip()}"
                )

    assert not violations, (
        "\n违反【铁律 7 失败在场律】：LLM 模块 except 块构造假响应\n"
        "如何修复：\n"
        "  - LLM 不可达 → raise RuntimeError(...)（铁律 2 路径 A）\n"
        "  - LLM 给出无效输出 → ctx['_last_understanding_failure'] = {...}（铁律 2 路径 B）\n"
        "  - 不许构造'看起来合理'的假响应让 LLM 失败消失在数据里\n"
        "若是带 fallback 标记的合规降级（如 _scribe_fallback=True），\n"
        "请在 _KNOWN_LLM_EXCEPT_VIOLATIONS 加白名单并加注释说明。\n"
        "  ----  违规位置  ----\n"
        + "\n".join(f"  {v}" for v in violations)
    )


def test_meta_假响应探测器自检() -> None:
    """元测试：确保双条件探测器不会误报也不会漏报。"""
    # 应该被 flag（构造 + LLM-shaped 字段）
    bad_cases = [
        "return QueryIntent(intent_type='exploration', confidence='low')",
        "return RefinementIntent(refine_type='unknown', confidence='low', guidance='...')",
    ]
    for bad in bad_cases:
        assert _FAKE_FIELD_PATTERN.search(bad), (
            f"字段探测器失效：连 {bad!r} 都不识别"
        )
        assert _FAKE_CONSTRUCTOR_PATTERN.search(bad), (
            f"构造探测器失效：连 {bad!r} 都不识别"
        )

    # 不应该被 flag（合规模式）
    ok_cases = [
        # agent 自己的返回状态
        "return self._done()",
        "return ReportData(...)",
        # stdlib / external 客户端对象
        "return Path(os.path.expanduser('~/.hagoku'))",
        "return OpenAI(base_url=..., api_key=...)",
        # raise 不是 return
        "raise RuntimeError(...)",
        # 不含 LLM-shaped 字段的构造（即便有构造调用）
        "return self._build_unknown_intent(feedback)",  # 内层调用，无字段
    ]
    for ok in ok_cases:
        # 至少一个条件不满足即可（字段 OR 构造）
        has_field = bool(_FAKE_FIELD_PATTERN.search(ok))
        has_construct = bool(_FAKE_CONSTRUCTOR_PATTERN.search(ok))
        assert not (has_field and has_construct), (
            f"守门 5b 双条件误报：{ok!r} 不应同时满足两个条件"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 元测试：守门测试本身能正常工作
# ─────────────────────────────────────────────────────────────────────────────

def test_meta_受检文件清单非空() -> None:
    """元测试：确保 _scanned_files 真的扫到了核心受检目录。"""
    files = _scanned_files()
    assert len(files) > 5, f"受检文件太少（{len(files)}），扫描配置可能错了"
    # 核心目录应该被扫到
    paths_str = " ".join(str(p) for p in files)
    assert "agents" in paths_str
    assert "manager" in paths_str


def test_meta_中文正则探测器自检() -> None:
    """元测试：确保中文语义正则的探测器真的会触发。"""
    bad = 're.search(r"收入|营收|销售", text)'
    assert _CHINESE_ALT_REGEX_PATTERN.search(bad), (
        "守门 2 探测器失效：连示例都识别不出"
    )
    # 单一中文不应触发
    ok = 're.search(r"是", text)'
    assert not _CHINESE_ALT_REGEX_PATTERN.search(ok), (
        "守门 2 探测器误报：单一中文短语不应判违规"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 守门 6：prompt 构造代码中不得含结论式规则
# ─────────────────────────────────────────────────────────────────────────────

# 检测 prompt 拼接代码中替 LLM 写结论的模式
# 注意：这些模式只检测「结论式规则」，不检测 Python 控制流和流程描述
_PROMPT_RULE_PATTERNS: list[tuple[str, str]] = [
    # 「role → value」格式的结论映射（如「identifier → false」「feature → true」）
    (r"(?:identifier|ignore|time_index|feature|target)\s*[→\->]\s*(?:true|false|参与|不参与)", "role→value 结论映射"),
    # 「必须判为 X 角色」的强制性角色分配（在 prompt 字符串内）
    (r"必须(?:判为|设为)\s*(?:feature|target|identifier|ignore)", "必须角色结论"),
    # 「规则：xxx → yyy」格式的硬性规则声明（在 prompt 字符串内）
    (r"[\"'].{0,20}(?:硬性规则|判断规则|映射规则).{0,50}[\"']", "规则声明"),
    # F-073 扩展：反欺骗 / 强制执行动词（「不要只用文字」「不可 X」「必须调 Y」「唯一有效操作是 Z」）
    (r"(?:不要只用文字|不可只用|必须调\s+\w+|唯一有效操作)", "反欺骗强制动词"),
    # F-073 扩展：结论式动词（「设为」「默认」「应该」「优先」——替 LLM 做选择）
    (r"[\"'](?:\s*设为\s+\w+|\s*默认\s+\w+|\s*应该\s+\w+|\s*优先\s+\w+)", "结论式动词"),
    # F-073 扩展：条件式阈值（「空值率 < 20%」「ratio > 3x」——业务判断数字固定在 prompt 中）
    (r"(?:空值率|比例|阈值|ratio|threshold)\s*[<>=]+\s*\d+%?", "条件式阈值"),
]


def test_doctrine_prompt中不得写结论式规则() -> None:
    """守门 6：扫描 prompt 构造代码，检测是否在替 LLM 写结论。

    合法：角色定义（feature=分组维度）、分析目标、调用引导
    违规：identifier→false、必须判为feature、硬性规则等

    这是对「铁律 0 事前刹车」的机器化补充——
    即使忘了写自检，代码也会被拦住。
    """
    violations: list[str] = []
    for path in _scanned_files():
        text = _read(path)
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            # 只检查函数内的字符串常量（这些更可能是 prompt 拼接）
            if not isinstance(node, ast.FunctionDef):
                continue
            try:
                func_src = ast.unparse(node)
            except Exception:
                continue

            # 检查函数是否在构造 prompt（含 chat.completions 或 system_prompt 或 analysis_goal 等）
            if not re.search(
                r"(system_prompt|analysis_goal|user_prompt|messages|prompt)",
                func_src,
                re.IGNORECASE,
            ):
                continue

            for pattern, desc in _PROMPT_RULE_PATTERNS:
                matches = list(re.finditer(pattern, func_src))
                for m in matches:
                    # 排除注释中的匹配（以 # 开头的行）
                    line_start = func_src.rfind("\n", 0, m.start()) + 1
                    line = func_src[line_start:m.end() + 20]
                    if line.strip().startswith("#"):
                        continue
                    # 排除合法的角色定义（如「feature — 分组维度」）
                    if "—" in m.group() and "→" not in m.group():
                        continue
                    rel = path.relative_to(HAGOKU_ROOT)
                    ctx = func_src[max(0, m.start() - 30):m.end() + 30]
                    violations.append(
                        f"{rel}::{node.name}:{node.lineno}  {desc}: …{ctx}…"
                    )

    assert not violations, (
        "\n违反【prompt 不得写结论】：prompt 构造代码中含替 LLM 做判断的规则式指令\n"
        "如何修复：\n"
        "  - 删掉映射规则（id→false 之类），LLM 自己能判断\n"
        "  - 删掉强制性结论（必须判为 X），改为角色定义（feature = 分组维度）\n"
        "  - 流程可以说，结论不能说\n"
        "  ----  违规位置  ----\n"
        + "\n".join(f"  {v}" for v in violations)
    )


def test_doctrine_无_session_messages_残留():
    """阶段 2 完工后，_session_messages 字面量不得在 hagoku/ 中出现。"""
    violations = []
    for path in HAGOKU_ROOT.rglob("*.py"):
        if "_session_messages" in _read(path):
            violations.append(str(path.relative_to(HAGOKU_ROOT)))
    assert not violations, (
        f"_session_messages 残留（应全部替换为 Session）:\n"
        + "\n".join(f"  {v}" for v in violations)
    )


def test_doctrine_无_conversation_history_残留():
    """任务 F 完工后，_conversation_history 不得在 cleaner/manager 中作为功能引用。"""
    violations = []
    for path in HAGOKU_ROOT.rglob("*.py"):
        rel = str(path.relative_to(HAGOKU_ROOT))
        # Only check agent and manager dirs
        if not rel.startswith("hagoku/agents/") and not rel.startswith("hagoku/manager/"):
            continue
        text = _read(path)
        if '_conversation_history"' in text or "'_conversation_history'" in text:
            violations.append(rel)
    assert not violations, (
        f"_conversation_history 残留（应退役）:\n"
        + "\n".join(f"  {v}" for v in violations)
    )


# ─────────────────────────────────────────────────────────────────────────────
# 守门 7：提示词层禁止预设业务结论（铁律 11）
# ─────────────────────────────────────────────────────────────────────────────
#
# 铁律 1 限制的是代码层硬编码，但实现者经常把"硬编码"搬到提示词里——
# 在 prompt.md / prompts.py / system_extra 字符串中写明:
#   "你必须把这个字段判断为 target"
#   "如果用户说 X，你应该理解成 Y"
#   "只关注以下字段：A, B, C"
# 这类句子替 LLM 做业务判断，和代码里的 if-elif 本质相同，但更难被代码扫描发现。
#
# 合法 vs 违规判断标准：
#   合法：告诉 LLM 当前阶段、数据背景、工具用法、输出格式
#   违规：替 LLM 预设业务结论（字段角色、用户意图解读、分析方法选择）
#
# 白名单：prompt.md 中用于"解释角色定义"的合法描述（不是结论，是背景）
_PROMPT_FILES = [
    HAGOKU_ROOT / "agents" / "prompt.md",
    HAGOKU_ROOT / "agents" / "analyst" / "prompt.md",
    HAGOKU_ROOT / "agents" / "scout" / "prompt.md",
    HAGOKU_ROOT / "agents" / "cleaner" / "prompt.md",
    HAGOKU_ROOT / "agents" / "reporter" / "prompt.md",
    HAGOKU_ROOT / "llm" / "prompts.py",
]

# 违规模式：替 LLM 预设业务结论的命令式指令
_PROMPT_VERDICT_PATTERNS: list[tuple[str, str]] = [
    # 强制性字段角色分配（"你必须把 X 判断为 target"）
    (r"你必须(?:把|将).{0,20}判(?:断|定)为", "强制性字段角色分配"),
    # 强制性用户意图解读（"如果用户说 X，你应该理解成 Y"）
    (r"如果用户(?:说|提到|输入).{0,30}你(?:应该|必须)(?:理解成|判断为|视为)", "强制性意图解读"),
    # 预设分析方法选择（"遇到 X 问题必须用 Y 方法"）
    (r"遇到.{0,20}(?:问题|情况|场景).{0,10}必须(?:用|使用|选择)", "预设分析方法"),
    # 禁止性字段过滤（"不要分析/不要关注 X 字段"——代码应通过 used_in_analysis 控制，不应写死在 prompt）
    (r"不(?:要|能|许|可以)(?:分析|关注|考虑).{0,20}(?:字段|列|变量)", "禁止性字段过滤"),
    # 强制性数值阈值结论（"p 值小于 0.05 就必须下结论 X"——阈值解释是 LLM 的活）
    (r"p\s*[值值]\s*[<＜]\s*0\.\d+\s*(?:就|则)(?:必须|应该|要)", "强制性数值阈值结论"),
    # 用户输入直接映射（"用户说'收入'就等于字段 X"——字段映射是 LLM 的活）
    (r"用户说.{0,15}就等于.{0,15}字段", "用户输入直接映射"),
    # 强制保留/排除特定字段名（直接命名真实业务字段）
    (r"(?:只(?:分析|关注|保留)|排除|忽略)\s+[\u4e00-\u9fa5A-Za-z_]{2,}(?:\s*[、,，]\s*[\u4e00-\u9fa5A-Za-z_]{2,}){2,}", "强制字段集合"),
    # 业务字段名作为判定示例（"'Inc1' 就是收入/费用"——具体字段含义是 LLM 的活）
    (r"[\"'].{2,10}[\"'].{0,10}(?:就是|是|代表|=).{0,20}(?:费用|收入|目标|特征|标识)", "字段名判定示例"),
]

# 白名单：这些句式在 prompt 里属于"角色/阶段说明"，不是业务结论
_PROMPT_VERDICT_WHITELIST = [
    "关注点",   # "关注点 1: 理解字段" 是阶段说明，不是结论
    "##",       # 章节标题行
    "例如",     # 举例说明
    "比如",     # 举例说明
    "示例",     # 示例行
    "三要素",   # 分析框架说明
    "tool_call",  # 工具调用说明
]

# 已知合规例外（历史 prompt 中确认合规的片段）
_PROMPT_VERDICT_KNOWN_OK: set[str] = set()


def _read_prompt_files() -> list[tuple[Path, str]]:
    """读取所有需要审计的 prompt 文件。"""
    result = []
    for p in _PROMPT_FILES:
        if p.exists():
            result.append((p, p.read_text(encoding="utf-8")))
    # 同时扫描 agents/ 下所有 prompt.md
    for p in (HAGOKU_ROOT / "agents").rglob("prompt.md"):
        if p not in [f for f, _ in result]:
            result.append((p, p.read_text(encoding="utf-8")))
    return result


def test_doctrine_提示词层禁止预设业务结论() -> None:
    """守门 7（铁律 11）：扫描所有 prompt.md 和 prompts.py，检测是否替 LLM 预设了业务结论。

    合法：阶段定义、工具说明、输出格式要求、分析目标背景
    违规：强制性字段角色分配、强制性意图解读、禁止性字段过滤、预设分析方法

    提示词层的硬编码比代码层更隐蔽——因为写提示词的人通常认为"这只是在引导模型"，
    实际上是在替模型做语义判断，破坏了上下文驱动的核心原则。
    """
    violations: list[str] = []

    for path, content in _read_prompt_files():
        for lineno, line in enumerate(content.splitlines(), 1):
            stripped = line.strip()
            # 跳过空行、注释行、白名单行
            if not stripped:
                continue
            if any(wl in stripped for wl in _PROMPT_VERDICT_WHITELIST):
                continue

            for pattern, desc in _PROMPT_VERDICT_PATTERNS:
                m = re.search(pattern, stripped)
                if not m:
                    continue
                key = f"{path.name}:{lineno}"
                if key in _PROMPT_VERDICT_KNOWN_OK:
                    continue
                ctx_snippet = stripped[:120]
                violations.append(f"{path.relative_to(HAGOKU_ROOT)}:{lineno}  [{desc}] {ctx_snippet}")

    assert not violations, (
        "\n违反【铁律 11 — 提示词层禁止预设业务结论】\n"
        "提示词里可以说：当前阶段是什么、工具怎么用、输出格式要求\n"
        "提示词里不能说：字段必须是 X 角色、用户说 A 就等于 B、不要分析 C 字段\n"
        "如何修复：删掉该结论式指令，改为向 LLM 提供背景信息，让它自行判断\n"
        "若确认该行合规，加入 _PROMPT_VERDICT_KNOWN_OK 白名单并附注释说明原因\n"
        "  ----  违规位置  ----\n"
        + "\n".join(f"  {v}" for v in violations)
    )


def test_meta_提示词违规探测器自检() -> None:
    """元测试：确保守门 7 的正则探测器能识别典型违规，且不误报合法 prompt 内容。"""
    bad_cases = [
        ("你必须把这个字段判断为 target", "强制性字段角色分配"),
        ("如果用户说收入，你应该理解成 Inc1 字段", "强制性意图解读"),
        ("不要分析 BU 字段，这个字段不重要", "禁止性字段过滤"),
        ("遇到分组对比问题必须用 t-test 方法", "预设分析方法"),
    ]
    for text, desc in bad_cases:
        matched = any(re.search(p, text) for p, _ in _PROMPT_VERDICT_PATTERNS)
        assert matched, f"守门 7 探测器失效：未识别违规案例「{text}」（{desc}）"

    ok_cases = [
        "## 关注点 1: 理解字段",
        "你的任务是理解每个字段的业务含义",
        "输出格式：调用 update_field_understanding 工具",
        "分析目标：{query}",
        "当前字段状态：{fields}",
        "每条结论必须包含 [发现] / [统计依据] / [局限或解读] 三要素",
    ]
    for text in ok_cases:
        matched = any(re.search(p, text) for p, _ in _PROMPT_VERDICT_PATTERNS)
        assert not matched, f"守门 7 探测器误报：合法 prompt 内容「{text}」被错误标记为违规"


# ─────────────────────────────────────────────────────────────────────────────
# 守门 5：代码层语义默认值 — 禁止 setdefault / .get() 预设业务结论
# ─────────────────────────────────────────────────────────────────────────────
#
# 代码中通过 setdefault 或 .get(key, literal_default) 为业务语义字段设置
# 字面量默认值（True/False/"feature"/"target" 等），等同于"我替 LLM 做业务判断"。
# LLM 没给的值，代码不准填。

# 业务语义字段名——这些字段的值必须由 LLM 产生
_SEMANTIC_FIELD_NAMES = {
    "used_in_analysis",
    "needs_user_input",
    "suggested_role",
    "display_name",
    "chinese_name",
    "description",
    "evidence",
    "inferred_type",
}

# 检测 .setdefault("语义字段", 字面量) 或 .get("语义字段", 字面量默认值)
_SETDEFAULT_PATTERN = re.compile(
    r"\.setdefault\s*\(\s*[\"'](" + "|".join(_SEMANTIC_FIELD_NAMES) + r")[\"']\s*,"
)
_GET_DEFAULT_PATTERN = re.compile(
    r"\.get\s*\(\s*[\"'](" + "|".join(_SEMANTIC_FIELD_NAMES) + r")[\"']\s*,\s*[^Nn]"
)

# .get("key", None) 或 .get("key", "") 不含业务语义，豁免
_GET_DEFAULT_OK = re.compile(
    r"\.get\s*\(\s*[\"'](" + "|".join(_SEMANTIC_FIELD_NAMES) + r")[\"']\s*,\s*(None|\[\]|\{\}|\"\"|''|0|1\.0)"
)


def _line_has_setdefault_violation(line: str) -> bool:
    m = _SETDEFAULT_PATTERN.search(line)
    if not m:
        return False
    field = m.group(1)
    # 提取 setdefault 的第二个参数（默认值）
    rest = line[m.end():].strip()
    if rest.startswith("None") or rest.startswith("[]") or rest.startswith("{}") or rest.startswith('""') or rest.startswith("''"):
        return False
    return True


def _line_has_getdefault_violation(line: str) -> bool:
    m = _GET_DEFAULT_PATTERN.search(line)
    if not m:
        return False
    # .get("key", None/[]/{}/"") 不含语义，豁免
    if _GET_DEFAULT_OK.search(line):
        return False
    return True


def test_doctrine_无代码层语义默认值() -> None:
    """禁止通过 setdefault 或 .get() 为业务语义字段设置字面量默认值。

    LLM 是字段语义的唯一权威。代码不准预设 used_in_analysis=True、
    suggested_role="feature" 等业务结论。
    """
    violations: list[str] = []

    for path in _scanned_files():
        lines = _read(path).splitlines()
        for lineno, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if _line_has_setdefault_violation(stripped):
                violations.append(f"{path.relative_to(HAGOKU_ROOT)}:{lineno}  setdefault 语义默认值 → {stripped[:100]}")
            elif _line_has_getdefault_violation(stripped):
                violations.append(f"{path.relative_to(HAGOKU_ROOT)}:{lineno}  .get() 语义默认值 → {stripped[:100]}")

    assert not violations, (
        "\n违反【铁律 1 — 零硬编码】代码层语义默认值\n"
        "代码通过 setdefault 或 .get() 为业务字段预设了字面量默认值\n"
        "（如 used_in_analysis=True、suggested_role='feature'）\n"
        "LLM 是字段语义的唯一权威——LLM 没给的值，代码不准填\n"
        "修复：删除 setdefault 行，或改为 .get(key)（无默认值）\n"
        f"违规行：\n" + "\n".join(violations)
    )
