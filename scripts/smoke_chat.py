from __future__ import annotations

import argparse
import os
import sys

import httpx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke test the deployed RAG app.")
    parser.add_argument("--base-url", default=os.getenv("SMOKE_BASE_URL", "https://123.59.90.15:8443"))
    parser.add_argument("--username", default=os.getenv("APP_USERNAME", "reviewer"))
    parser.add_argument("--password", default=os.getenv("APP_PASSWORD", ""))
    parser.add_argument("--message", default="软件学院党委书记为2023级本科新生讲党课主要讲述什么？")
    parser.add_argument("--verify", action="store_true", help="Verify TLS certificates.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.password:
        print("APP_PASSWORD or --password is required", file=sys.stderr)
        return 2

    with httpx.Client(base_url=args.base_url, verify=args.verify, timeout=30.0) as client:
        health = client.get("/api/health")
        print(f"health {health.status_code}: {health.text}")
        health.raise_for_status()

        login = client.post(
            "/api/login",
            json={"username": args.username, "password": args.password},
        )
        print(f"login {login.status_code}: {login.text}")
        login.raise_for_status()

        chat = client.post("/api/chat", json={"message": args.message})
        print(f"chat {chat.status_code}: {chat.text[:1000]}")
        chat.raise_for_status()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
