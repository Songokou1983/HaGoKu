"""HaGoKu 知识库 — 结构化领域知识，可检索，供 Agent 和用户共同使用"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

KB_DIR = Path(__file__).parent


class KnowledgeBase:
    """知识库管理器"""

    def __init__(self, kb_dir: Path = KB_DIR) -> None:
        self.kb_dir = kb_dir
        self._registry: list[dict[str, Any]] = []
        self._load_registry()

    def _load_registry(self) -> None:
        registry_path = self.kb_dir / "_registry.yaml"
        if not registry_path.exists():
            return
        with open(registry_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        self._registry = data.get("entries", [])

    def _load_entry_content(self, filename: str) -> str:
        """加载单个知识条目的正文内容"""
        path = self.kb_dir / filename
        if not path.exists():
            return ""
        with open(path, encoding="utf-8") as f:
            content = f.read()
        # 去掉 frontmatter
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                content = parts[2].strip()
        return content.strip()

    # ── 检索接口 ────────────────────────────────────────

    def retrieve(
        self,
        *,
        category: str | None = None,
        keywords: list[str] | None = None,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        """
        按类别和关键词检索知识条目

        Returns:
            [{"title", "category", "tags", "summary", "content"}, ...]
        """
        results = []
        for entry in self._registry:
            # 类别过滤
            if category and entry.get("category") != category:
                continue

            # 关键词匹配（标题/标签/摘要）
            if keywords:
                text = " ".join([
                    entry.get("title", ""),
                    " ".join(entry.get("tags", [])),
                    entry.get("summary", ""),
                ]).lower()
                if not any(kw.lower() in text for kw in keywords):
                    continue

            entry_with_content = {
                "title": entry["title"],
                "category": entry.get("category", ""),
                "tags": entry.get("tags", []),
                "summary": entry.get("summary", ""),
                "content": self._load_entry_content(entry.get("filename", "")),
            }
            results.append(entry_with_content)

            if len(results) >= limit:
                break

        return results

    def retrieve_by_context(self, context: str, limit: int = 3) -> list[dict[str, Any]]:
        """
        按分析场景描述检索最相关的知识条目。
        简单实现：提取中文 2-gram + 英文词后匹配。
        后期升级：Embedding 语义检索。
        """
        # 提取中文 2-gram 和 3-gram
        chinese_chars = re.findall(r"[一-鿿]+", context)
        keywords = []
        for chunk in chinese_chars:
            for i in range(len(chunk) - 1):
                keywords.append(chunk[i : i + 2])
                if i + 2 < len(chunk):
                    keywords.append(chunk[i : i + 3])
        # 英文词
        english = re.findall(r"[a-zA-Z]{3,}", context.lower())
        keywords.extend(english)
        # 去重
        keywords = list(set(k for k in keywords if len(k) >= 2))
        if not keywords:
            return []
        return self.retrieve(keywords=keywords, limit=limit)

    def get_by_category(self, category: str) -> list[dict[str, Any]]:
        """获取指定类别的所有条目（不含正文）"""
        return [
            {
                "title": e["title"],
                "category": e.get("category", ""),
                "tags": e.get("tags", []),
                "summary": e.get("summary", ""),
            }
            for e in self._registry
            if e.get("category") == category
        ]

    def all_entries(self) -> list[dict[str, Any]]:
        """获取所有条目索引（不含正文，用于侧边栏列表）"""
        return [
            {
                "title": e["title"],
                "category": e.get("category", ""),
                "tags": e.get("tags", []),
                "summary": e.get("summary", ""),
            }
            for e in self._registry
        ]

    def categories(self) -> list[str]:
        """获取所有类别"""
        cats = sorted(set(e.get("category", "") for e in self._registry))
        return cats


# 全局单例
_kb: KnowledgeBase | None = None


def get_knowledge_base() -> KnowledgeBase:
    global _kb
    if _kb is None:
        _kb = KnowledgeBase()
    return _kb


def retrieve_knowledge(
    context: str | None = None,
    category: str | None = None,
    keywords: list[str] | None = None,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """快捷函数：检索知识条目

    Agent 调用示例：
        from hagokyu.kb import retrieve_knowledge
        kb_results = retrieve_knowledge(context="用户留存分析怎么做", limit=2)
        # 返回 [{"title": "...", "content": "...", "tags": [...], ...}, ...]
    """
    kb = get_knowledge_base()
    if context:
        return kb.retrieve_by_context(context, limit=limit)
    return kb.retrieve(category=category, keywords=keywords, limit=limit)


def search_kb_for_method(method_hint: str) -> dict[str, Any] | None:
    """根据方法提示词搜索对应的知识条目（供 Agent 直接使用）

    Args:
        method_hint: 如 "t检验", "回归", "ROI", "AB测试"

    Returns:
        匹配的知识条目（含正文），未找到返回 None
    """
    results = retrieve_knowledge(keywords=[method_hint], limit=1)
    return results[0] if results else None
