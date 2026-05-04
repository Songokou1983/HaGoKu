"""HaGoKu Knowledge Base — 结构化领域知识库"""

from .knowledge_base import (
    KnowledgeBase,
    get_knowledge_base,
    retrieve_knowledge,
    search_kb_for_method,
)

__all__ = [
    "KnowledgeBase",
    "get_knowledge_base",
    "retrieve_knowledge",
    "search_kb_for_method",
]
