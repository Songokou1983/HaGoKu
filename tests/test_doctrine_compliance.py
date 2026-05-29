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

# 受 doctrine 约束的代码区域（语义判断高发区）。
# 工具实现层（hagoku/tools/）多为统计计算与 IO，不在此范围。
_DOCTRINE_SUBDIRS = ("agents", "manager", "api", "memory", "guardrails")

# 已知合法例外文件（function calling 工具 description 含中文是正常的）
_EXEMPT_FILES: set[str] = set()


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
    "create_quick_client",
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
            violations.append(f"{rel}::{node.name} (line {node.lineno})")

    assert not violations, (
        "\n违反【零硬编码】：函数名暗示 LLM 推断但内部无 LLM 调用\n"
        "如何修复：要么真的调 LLM；要么改名为 _compute_/_resolve_/_parse_ 表明纯运算。\n"
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

_LLM_CALL_HINT_LINES = re.compile(
    r"chat\.completions\.create|create_raw_client|create_quick_client"
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
