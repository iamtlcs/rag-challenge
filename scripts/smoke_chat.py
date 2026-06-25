from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Callable
from typing import TypeVar

import httpx


T = TypeVar("T")


def print_line(message: str, *, stream=None) -> None:
    target = stream or sys.stdout
    try:
        print(message, file=target)
    except UnicodeEncodeError:
        encoding = getattr(target, "encoding", None) or "utf-8"
        safe = message.encode(encoding, errors="replace").decode(encoding, errors="replace")
        print(safe, file=target)


def request_with_retries(
    operation: Callable[[], T],
    *,
    attempts: int = 10,
    delay: float = 1.0,
) -> T:
    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            return operation()
        except httpx.TransportError as exc:
            last_error = exc
            if delay:
                time.sleep(delay)
    if last_error:
        raise last_error
    return operation()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke test the deployed RAG app.")
    parser.add_argument("--base-url", default=os.getenv("SMOKE_BASE_URL", "https://123.59.90.15:8443"))
    parser.add_argument("--username", default=os.getenv("APP_USERNAME", "reviewer"))
    parser.add_argument("--password", default=os.getenv("APP_PASSWORD", ""))
    parser.add_argument("--message", default="软件学院党委书记为2023级本科新生讲党课主要讲述什么？")
    parser.add_argument("--verify", action="store_true", help="Verify TLS certificates.")
    parser.add_argument("--retries", type=int, default=10)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.password:
        print("APP_PASSWORD or --password is required", file=sys.stderr)
        return 2

    with httpx.Client(base_url=args.base_url, verify=args.verify, timeout=30.0) as client:
        health = request_with_retries(lambda: client.get("/api/health"), attempts=args.retries)
        print_line(f"health {health.status_code}: {health.text}")
        health.raise_for_status()

        login = client.post(
            "/api/login",
            json={"username": args.username, "password": args.password},
        )
        print_line(f"login {login.status_code}: {login.text}")
        login.raise_for_status()

        chat = client.post("/api/chat", json={"message": args.message})
        print_line(f"chat {chat.status_code}: {chat.text[:1000]}")
        chat.raise_for_status()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
