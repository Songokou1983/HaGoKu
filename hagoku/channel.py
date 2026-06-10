"""通道函数 — 所有 Agent 调用 LLM 时的统一 messages 构造入口。

铁律 11（通道优先律）+ 通道守门（Phase 0）：
禁止任何代码直接构造 messages = [...]。必须通过此模块的函数。
只追加，不筛选、不删减、不重排。
"""

from __future__ import annotations

from typing import Any


def build_messages(
    *,
    query: str,
    user_input: str,
    history: list[dict[str, Any]] | None = None,
    system_extra: str | None = None,
) -> list[dict[str, Any]]:
    """构建发给 LLM 的 messages。

    规则：
    - query 作为第一条 user 消息注入，永不删除
    - history 原样追加（不修改、不筛选、不重排）
    - system_extra 如提供，追加到 system 前缀
    - user_input 作为最后一条 user 消息

    禁止：
    - 从 query/history/user_input 中删除或修改任何内容
    - 派生摘要替换原始内容
    - if-else 分支决定 LLM 看到什么
    """
    msgs: list[dict[str, Any]] = []
    if system_extra:
        msgs.append({"role": "system", "content": system_extra})
    msgs.append({"role": "user", "content": query})
    if history:
        msgs.extend(history)
    msgs.append({"role": "user", "content": user_input})
    return msgs
