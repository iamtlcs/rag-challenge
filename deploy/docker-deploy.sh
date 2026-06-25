#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/iamtlcs/rag-challenge.git}"
APP_ROOT="${APP_ROOT:-/opt/rag-challenge}"
REPO_DIR="$APP_ROOT/repo"
ENV_FILE="$APP_ROOT/.env"

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing $ENV_FILE. Create it from .env.example and keep secrets there only." >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  apt-get update
  apt-get install -y docker.io docker-compose-plugin
fi

systemctl stop rag-challenge 2>/dev/null || true
systemctl disable rag-challenge 2>/dev/null || true
systemctl stop nginx 2>/dev/null || true
systemctl disable nginx 2>/dev/null || true

mkdir -p "$APP_ROOT"
if [ -d "$REPO_DIR/.git" ]; then
  git -C "$REPO_DIR" fetch --all --prune
  git -C "$REPO_DIR" checkout main
  git -C "$REPO_DIR" pull --ff-only
else
  rm -rf "$REPO_DIR"
  git clone "$REPO_URL" "$REPO_DIR"
fi

cd "$REPO_DIR"
docker compose build app
docker compose run --rm app python -m scripts.crawl --seeds-from html/questions.html --out data/corpus.jsonl --delay 0.75 --max-pages "${MAX_PAGES:-900}"
docker compose run --rm app python -m scripts.build_index --corpus data/corpus.jsonl --out data/index
docker compose up -d
docker compose ps
