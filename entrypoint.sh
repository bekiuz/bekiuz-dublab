#!/usr/bin/env bash
set -Eeuo pipefail

: "${BOT_TOKEN:?BOT_TOKEN secret is required}"
: "${GEMINI_API_KEY:?GEMINI_API_KEY secret is required}"
: "${TELEGRAM_API_ID:?TELEGRAM_API_ID is required for Local Bot API}"
: "${TELEGRAM_API_HASH:?TELEGRAM_API_HASH is required for Local Bot API}"

export DATA_DIR="${DATA_DIR:-/data}"
export TELEGRAM_API_BASE_URL="${TELEGRAM_API_BASE_URL:-http://127.0.0.1:8081}"
export TELEGRAM_LOCAL_MODE=true
mkdir -p "$DATA_DIR/bot-api" "$DATA_DIR/bot-api-files" "$DATA_DIR/uploads" "$DATA_DIR/tmp"

echo "[startup] Starting Telegram Local Bot API..."
telegram-bot-api \
  --api-id="$TELEGRAM_API_ID" \
  --api-hash="$TELEGRAM_API_HASH" \
  --local \
  --http-ip-address=127.0.0.1 \
  --http-port=8081 \
  --dir="$DATA_DIR/bot-api" \
  --files-dir="$DATA_DIR/bot-api-files" \
  --temp-dir="$DATA_DIR/tmp" &
API_PID=$!
BOT_PID=""

cleanup() {
  trap - EXIT INT TERM
  echo "[shutdown] Stopping Bekiuz DubLab processes..."
  if [[ -n "$BOT_PID" ]]; then kill -TERM "$BOT_PID" 2>/dev/null || true; fi
  kill -TERM "$API_PID" 2>/dev/null || true
  if [[ -n "$BOT_PID" ]]; then wait "$BOT_PID" 2>/dev/null || true; fi
  wait "$API_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "[startup] Waiting for Local Bot API port 8081..."
API_READY=false
for attempt in $(seq 1 90); do
  if (echo > /dev/tcp/127.0.0.1/8081) >/dev/null 2>&1; then
    API_READY=true
    break
  fi
  if ! kill -0 "$API_PID" 2>/dev/null; then
    echo "[startup] Local Bot API exited unexpectedly." >&2
    exit 1
  fi
  sleep 1
done
if [[ "$API_READY" != "true" ]]; then
  echo "[startup] Local Bot API did not become ready within 90 seconds." >&2
  exit 1
fi

if [[ "${TELEGRAM_AUTO_LOGOUT:-false}" == "true" && ! -f "$DATA_DIR/.cloud-api-logged-out" ]]; then
  echo "[startup] Moving bot from Telegram cloud API to Local Bot API (one-time step)..."
  python /app/switch_to_local.py --yes
  touch "$DATA_DIR/.cloud-api-logged-out"
fi

echo "[startup] Starting Bekiuz DubLab polling bot..."
python /app/bot.py &
BOT_PID=$!
wait "$BOT_PID"
