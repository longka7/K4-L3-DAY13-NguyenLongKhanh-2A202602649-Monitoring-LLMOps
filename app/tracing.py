from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any

try:
    from langfuse import get_client, observe, propagate_attributes

    LANGFUSE_SDK_AVAILABLE = True
except ImportError:  # pragma: no cover - chỉ dùng khi chưa cài requirements
    LANGFUSE_SDK_AVAILABLE = False

    def observe(*args: Any, **kwargs: Any):
        def decorator(func):
            return func

        return decorator

    class _DummyClient:
        def update_current_span(self, **kwargs: Any) -> None:
            return None

        def update_current_generation(self, **kwargs: Any) -> None:
            return None

    def get_client():
        return _DummyClient()

    @contextmanager
    def propagate_attributes(**kwargs: Any):
        yield


def get_langfuse_client():
    return get_client()


def tracing_enabled() -> bool:
    return LANGFUSE_SDK_AVAILABLE and bool(
        os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")
    )


class _NoopObservation:
    """Thay thế observation khi client không hỗ trợ (tracing tắt hoặc client giả trong test)."""

    def update(self, **kwargs: Any) -> "_NoopObservation":
        return self


@contextmanager
def child_observation(client: Any, **kwargs: Any):
    """Mở child observation lồng dưới observation hiện tại (Langfuse v4 ``start_as_current_observation``).

    Client không có API này (tracing tắt / test double) thì chạy như no-op để logic nghiệp vụ
    không phụ thuộc vào việc tracing có bật hay không.
    """
    start = getattr(client, "start_as_current_observation", None)
    if not callable(start):
        yield _NoopObservation()
        return
    with start(**kwargs) as observation:
        yield observation
