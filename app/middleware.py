from __future__ import annotations

import re
import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from structlog.contextvars import bind_contextvars, clear_contextvars

from .pii import contains_pii

# Chỉ nhận ID ngắn, ký tự an toàn: chặn log injection (xuống dòng, JSON) và ID dài bất thường.
_INCOMING_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,63}")


def new_correlation_id() -> str:
    return f"req-{uuid.uuid4().hex[:8]}"


def resolve_correlation_id(header_value: str | None) -> str:
    """Giữ x-request-id từ upstream nếu hợp lệ (để nối log xuyên service), ngược lại sinh mới."""
    candidate = (header_value or "").strip()
    if candidate and _INCOMING_ID.fullmatch(candidate) and not contains_pii(candidate):
        return candidate
    return new_correlation_id()


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Context của request trước (cùng worker/thread) không được rò sang request này.
        clear_contextvars()
        correlation_id = resolve_correlation_id(request.headers.get("x-request-id"))
        bind_contextvars(correlation_id=correlation_id)

        request.state.correlation_id = correlation_id
        
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
        response.headers["x-request-id"] = correlation_id
        response.headers["x-response-time-ms"] = f"{elapsed_ms:.1f}"
        return response
