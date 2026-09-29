from __future__ import annotations

import hashlib
import re

# Thứ tự có ý nghĩa: pattern dài/cụ thể chạy trước để không bị pattern ngắn "cắt" mất một phần
# (vd 16 số thẻ không bị nhận nhầm thành CCCD/điện thoại rồi để lộ phần còn lại).
PII_PATTERNS: dict[str, str] = {
    "credit_card": r"(?<!\d)\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}(?!\d)",
    "email": r"[\w\.+-]+@[\w-]+(?:\.[\w-]+)*\.[A-Za-z]{2,}",
    "cccd": r"(?<!\d)\d{12}(?!\d)",
    "phone_vn": r"(?<!\d)(?:\+84|0)(?:[ .-]?\d){9}(?!\d)",
    # Hộ chiếu Việt Nam: 1 chữ cái in hoa + 7 chữ số (vd B1234567)
    "passport_vn": r"\b[A-Z]\d{7}\b",
}
_COMPILED = {name: re.compile(pattern) for name, pattern in PII_PATTERNS.items()}


def scrub_text(text: str) -> str:
    safe = text
    for name, pattern in _COMPILED.items():
        safe = pattern.sub(f"[REDACTED_{name.upper()}]", safe)
    return safe


def contains_pii(text: str) -> bool:
    return any(pattern.search(text) for pattern in _COMPILED.values())


def summarize_text(text: str, max_len: int = 80) -> str:
    safe = scrub_text(text).strip().replace("\n", " ")
    return safe[:max_len] + ("..." if len(safe) > max_len else "")


def hash_user_id(user_id: str) -> str:
    return hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:12]
