"""Quản lý prompt `day13-chat` trong project Langfuse cá nhân (docs/PROMPT_VERSIONING.md).

    python scripts/prompt_versions.py status            # liệt kê version + labels
    python scripts/prompt_versions.py create            # tạo v1 (baseline, production) và v2 (candidate)
    python scripts/prompt_versions.py promote 2         # gắn label production cho version 2
    python scripts/prompt_versions.py promote 1         # rollback production về version 1

Đọc key từ .env; không in key ra màn hình.
"""
from __future__ import annotations

import argparse
import os

from dotenv import load_dotenv

load_dotenv(".env")

from langfuse import get_client  # noqa: E402  (cần load .env trước khi tạo client)

NAME = os.getenv("LANGFUSE_PROMPT_NAME", "day13-chat")

# Giữ nguyên 3 biến {{feature}}, {{docs}}, {{message}} ở mọi version (prompt contract).
V1 = "Feature={{feature}}\nDocs={{docs}}\nQuestion={{message}}"
V2 = (
    "Feature={{feature}}\nDocs={{docs}}\nQuestion={{message}}\n"
    "Answer in at most 3 short bullet points, only from Docs."
)


def _version_labels(client, max_version: int = 10) -> list[tuple[int, list[str]]]:
    rows = []
    for version in range(1, max_version + 1):
        try:
            prompt = client.get_prompt(NAME, version=version, cache_ttl_seconds=0, max_retries=0)
        except Exception:
            break
        rows.append((prompt.version, list(prompt.labels)))
    return rows


def status(client) -> None:
    rows = _version_labels(client)
    if not rows:
        print(f"Chưa có prompt '{NAME}'.")
    for version, labels in rows:
        print(f"{NAME} v{version}: labels={labels}")


def create(client) -> None:
    if _version_labels(client):
        print("Prompt đã tồn tại, không tạo lại:")
        return status(client)
    v1 = client.create_prompt(
        name=NAME, prompt=V1, type="text", labels=["baseline", "production"],
        commit_message="v1: baseline template",
    )
    v2 = client.create_prompt(
        name=NAME, prompt=V2, type="text", labels=["candidate"],
        commit_message="v2: giới hạn 3 bullet, chỉ dùng Docs",
    )
    print(f"Tạo v{v1.version} (baseline, production) và v{v2.version} (candidate).")
    status(client)


def promote(client, version: int) -> None:
    current = client.get_prompt(NAME, version=version, cache_ttl_seconds=0, max_retries=0)
    # "latest" do Langfuse tự gán cho version mới nhất — gửi kèm sẽ bị API trả 400.
    labels = sorted((set(current.labels) | {"production"}) - {"latest"})
    # Langfuse chuyển label production khỏi version cũ khi gán cho version mới.
    client.update_prompt(name=NAME, version=version, new_labels=labels)
    print(f"production -> v{version}")
    status(client)


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("create")
    promote_parser = sub.add_parser("promote")
    promote_parser.add_argument("version", type=int)
    args = parser.parse_args()

    client = get_client()
    {"status": status, "create": create}.get(args.cmd, lambda c: promote(c, args.version))(client)
    client.flush()


if __name__ == "__main__":
    main()
