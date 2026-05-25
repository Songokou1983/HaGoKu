"""API 认证 / 速率限制中间件

M4 修复：FastAPI 中间件栈，提供
1. API Key 认证（基于 HAGOKU_API_KEY 环境变量）
2. 内存速率限制器（滑动窗口，默认 60 req/min）
3. 健康检查端点豁免

环境变量：
  HAGOKU_API_KEY         — API 密钥（不设则跳过认证）
  HAGOKU_RATE_LIMIT      — 速率限制 req/min（默认 60）
  HAGOKU_ENV             — production 时启用认证，否则跳过
"""

from __future__ import annotations

import os
import time
import logging
from collections import defaultdict
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

_log = logging.getLogger("hagoku.api.middleware")

# ── 配置 ──
_API_KEY = os.environ.get("HAGOKU_API_KEY", "").strip()
_rate_limit_str = os.environ.get("HAGOKU_RATE_LIMIT", "60").strip()
_RATE_LIMIT = max(1, int(_rate_limit_str) if _rate_limit_str.isdigit() else 60)
_ENV = os.environ.get("HAGOKU_ENV", "").strip().lower()
_AUTH_ENABLED = bool(_API_KEY) and _ENV in ("production", "prod")

# ── 速率限制状态（进程内） ──
_window_start: float = time.monotonic()
_window_requests: defaultdict[str, int] = defaultdict(int)

# 豁免端点
_EXEMPT_PATHS: list[str] = ["/api/health"]


class ApiAuthMiddleware(BaseHTTPMiddleware):
    """
    API 认证 + 速率限制中间件。

    认证：从 X-API-Key 头读取密钥，与 HAGOKU_API_KEY 比较。
    速率限制：滑动窗口，默认每客户端 60 req/min，通过 X-Forwarded-For
              或 client host 识别客户端。
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        _log.info(
            "API middleware: auth=%s, rate_limit=%d req/min",
            _AUTH_ENABLED,
            _RATE_LIMIT,
        )

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        # ── 豁免路径 ──
        if request.url.path in _EXEMPT_PATHS:
            return await call_next(request)

        # ── 认证检查 ──
        if _AUTH_ENABLED:
            api_key = request.headers.get("X-API-Key", "")
            if api_key != _API_KEY:
                _log.warning("Auth failed for %s", _client_id(request))
                return JSONResponse(
                    status_code=401,
                    content={"detail": "无效的 API 密钥"},
                )

        # ── 速率限制 ──
        if not _check_rate_limit(_client_id(request)):
            _log.warning("Rate limit exceeded for %s", _client_id(request))
            return JSONResponse(
                status_code=429,
                content={
                    "detail": f"速率限制 ({_RATE_LIMIT} req/min)。请稍等重试。"
                },
            )

        return await call_next(request)


def _client_id(request: Request) -> str:
    """从请求中提取客户端标识符。"""
    # 优先 X-Forwarded-For
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    # 回退 client.host
    host = request.client.host if request.client else "unknown"
    return host


def _check_rate_limit(client_id: str) -> bool:
    """滑动窗口速率限制检查。"""
    global _window_start, _window_requests

    now = time.monotonic()
    # 窗口过期，重置
    if now - _window_start >= 60.0:
        _window_start = now
        _window_requests.clear()

    count = _window_requests[client_id]
    if count >= _RATE_LIMIT:
        return False

    _window_requests[client_id] = count + 1
    return True