"""HaGoKu Studio 统一日志模块"""

from __future__ import annotations

import logging


def get_logger(name: str) -> logging.Logger:
    """
    获取 HaGoKu Studio 模块日志器

    Args:
        name: 模块名（如 "analysis", "visualization"）

    Returns:
        配置好的 Logger 实例
    """
    logger = logging.getLogger(f"hagoku.{name}")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            "[%(name)s] %(levelname)s: %(message)s"
        ))
        logger.addHandler(handler)
        logger.setLevel(logging.WARNING)
    return logger
