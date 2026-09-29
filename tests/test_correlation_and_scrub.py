from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import httpx

from app import logging_config
from app.logging_config import scrub_event
from app.main import app
from app.middleware import resolve_correlation_id

ID_FORMAT = re.compile(r"^req-[0-9a-f]{8}$")


def _post(headers: dict | None = None, **body) -> httpx.Response:
    payload = {"user_id": "student-01", "session_id": "s-01", "feature": "qa",
               "message": "Explain observability"} | body

    async def send() -> httpx.Response:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            return await c.post("/chat", json=payload, headers=headers or {})

    return asyncio.run(send())


def test_sinh_id_dung_dinh_dang_khi_khong_co_header() -> None:
    assert ID_FORMAT.match(resolve_correlation_id(None))
    assert ID_FORMAT.match(resolve_correlation_id(""))


def test_giu_id_hop_le_tu_upstream() -> None:
    assert resolve_correlation_id("req-deadbeef") == "req-deadbeef"


def test_tu_choi_id_nguy_hiem_hoac_chua_pii() -> None:
    for bad in ('x"\n{"event":"fake"}', "a" * 200, "student@vinuni.edu.vn", "0901234567"):
        assert ID_FORMAT.match(resolve_correlation_id(bad)), bad


def test_response_tra_id_va_thoi_gian(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(logging_config, "LOG_PATH", tmp_path / "logs.jsonl")
    res = _post(headers={"x-request-id": "req-0badc0de"})
    assert res.headers["x-request-id"] == "req-0badc0de"
    assert res.json()["correlation_id"] == "req-0badc0de"
    assert float(res.headers["x-response-time-ms"]) >= 0


def test_khong_ro_context_giua_hai_request(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)
    first = _post(user_id="u-first", session_id="s-first")
    second = _post(user_id="u-second", session_id="s-second", feature="summary")
    events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    by_id: dict[str, set[str]] = {}
    for e in events:
        if e.get("service") == "api":
            by_id.setdefault(e["correlation_id"], set()).add(e["session_id"])
    assert first.headers["x-request-id"] != second.headers["x-request-id"]
    assert by_id[first.headers["x-request-id"]] == {"s-first"}
    assert by_id[second.headers["x-request-id"]] == {"s-second"}
    for e in events:
        if e.get("service") == "api":
            assert {"user_id_hash", "session_id", "feature", "model", "env"} <= e.keys()
            assert "u-first" not in json.dumps(e) and "u-second" not in json.dumps(e)


def test_scrub_moi_truong_ke_ca_long_nhau() -> None:
    event = {"ts": "2026-09-29T00:00:00Z", "level": "error", "event": "request_failed",
             "error_detail": "lien he 0901234567",
             "payload": {"detail": "student@vinuni.edu.vn", "items": ["4111 1111 1111 1111"]}}
    out = json.dumps(scrub_event(None, "error", event), ensure_ascii=False)
    for raw in ("0901234567", "student@vinuni.edu.vn", "4111 1111 1111 1111"):
        assert raw not in out
