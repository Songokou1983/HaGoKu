"""
命令解析器。

将用户输入中的 /命令 格式解析为结构化的 command + args，
供 orchestrator 路由到对应阶段 LLM。

不以 "/" 开头的输入不是命令，返回 None。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Union


@dataclass
class ParsedCommand:
    """解析后的命令结构。"""
    command: str
    # goal → 自然语言字符串；rename → list[(str, str)]；use → list[str]
    args: Union[str, list[tuple[str, str]], list[str]]

    @classmethod
    def goal(cls, text: str) -> "ParsedCommand":
        return cls(command="goal", args=text.strip())

    @classmethod
    def rename(cls, pairs: list[tuple[str, str]]) -> "ParsedCommand":
        return cls(command="rename", args=pairs)

    @classmethod
    def use(cls, columns: list[str]) -> "ParsedCommand":
        return cls(command="use", args=columns)


def parse(raw: str) -> Optional[ParsedCommand]:
    """
    解析用户输入。不是命令则返回 None。

    支持的命令：
      /goal <自然语言文本>
      /rename <原始列名>=<中文名称> [, ...]
      /use <列名1>, <列名2>, ...
    """
    text = raw.strip()
    if not text.startswith("/"):
        return None

    # 提取命令名
    parts = text.split(None, 1)
    cmd = parts[0][1:]  # 去掉前面的 /
    remainder = parts[1].strip() if len(parts) > 1 else ""

    if cmd == "goal":
        return ParsedCommand.goal(remainder)

    if cmd == "rename":
        return _parse_rename(remainder)

    if cmd == "use":
        return _parse_use(remainder)

    # 未知命令：作为自然语言
    return None


def _parse_rename(text: str) -> ParsedCommand:
    """解析 /rename 参数：Code=店铺编号, Amt=收入金额"""
    pairs: list[tuple[str, str]] = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            continue
        key, _, value = part.partition("=")
        pairs.append((key.strip(), value.strip()))
    return ParsedCommand.rename(pairs)


def _parse_use(text: str) -> ParsedCommand:
    """解析 /use 参数：收入, 客流, 日期"""
    columns = [col.strip() for col in text.split(",") if col.strip()]
    return ParsedCommand.use(columns)