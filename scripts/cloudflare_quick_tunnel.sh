#!/usr/bin/env bash
set -euo pipefail

PORT="${PORT:-8000}"
SERVICE_URL="http://localhost:${PORT}"

echo "Starting Cloudflare Quick Tunnel to ${SERVICE_URL}"
echo "Copy the https://*.trycloudflare.com URL from the output."
echo "Then set APP_BASE_URL in .env to that URL."
echo
exec cloudflared tunnel --url "${SERVICE_URL}"
