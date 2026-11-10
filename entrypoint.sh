#!/usr/bin/env sh
set -eu

: "${BOT_TOKEN:?BOT_TOKEN secret is required}"
: "${GEMINI_API_KEY:?GEMINI_API_KEY secret is required}"
: "${TELEGRAM_API_ID:?TELEGRAM_API_ID is required for large media downloads}"
: "${TELEGRAM_API_HASH:?TELEGRAM_API_HASH is required for large media downloads}"

export DATA_DIR="${DATA_DIR:-/data}"
mkdir -p "$DATA_DIR/uploads"

echo "[startup] Starting Bekiuz DubLab with MTProto media downloads..."
exec python /app/bot.py
