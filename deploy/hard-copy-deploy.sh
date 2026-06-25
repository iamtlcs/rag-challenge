#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/rag-challenge}"
ENV_FILE="$APP_ROOT/.env"

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing $ENV_FILE. Keep APP_USERNAME, APP_PASSWORD, SESSION_SECRET, and optional OLLAMA_* there." >&2
  exit 1
fi

systemctl stop rag-challenge 2>/dev/null || true
docker compose -f "$APP_ROOT/repo/docker-compose.yml" down 2>/dev/null || true
docker stop tke-rag-chatbot-frontend-1 tke-rag-chatbot-backend-1 2>/dev/null || true

cp "$APP_ROOT/deploy/rag-challenge.service" /etc/systemd/system/rag-challenge.service
cp "$APP_ROOT/deploy/nginx-rag-challenge.conf" /etc/nginx/sites-available/default

systemctl daemon-reload
systemctl enable rag-challenge
systemctl restart rag-challenge
nginx -t
systemctl enable nginx
systemctl restart nginx

systemctl --no-pager -l status rag-challenge
