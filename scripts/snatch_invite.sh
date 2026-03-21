#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -d .venv ]; then
  mkdir -p .uv-cache
  UV_CACHE_DIR="$ROOT_DIR/.uv-cache" uv venv .venv
fi

source .venv/bin/activate
PYTHON_BIN="$(command -v python)"
if [[ "$PYTHON_BIN" != "$ROOT_DIR/.venv/"* ]]; then
  echo "python is not using project .venv: $PYTHON_BIN" >&2
  exit 1
fi

export PYTHONPATH="$ROOT_DIR/src"

JS_URL="${1:-https://hudong.alicdn.com/api/data/v2/438eae9715f945468d599660d2d92aeb.js}"
INTERVAL="${INTERVAL:-1}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-300}"
ENABLE_CLIPBOARD="${ENABLE_CLIPBOARD:-1}"
ENABLE_SOUND="${ENABLE_SOUND:-1}"
SOUND_NAME="${SOUND_NAME:-Glass}"
AUTO_FILL_APP="${AUTO_FILL_APP:-1}"
AUTO_SUBMIT_APP="${AUTO_SUBMIT_APP:-0}"
DEADLINE=$(( $(date +%s) + TIMEOUT_SECONDS ))
LAST_IMAGE_URL=""

while [ "$(date +%s)" -lt "$DEADLINE" ]; do
  if PAYLOAD="$(curl -fsSL -H 'Cache-Control: no-cache' "$JS_URL" 2>/dev/null)"; then
    if IMAGE_URL="$(printf '%s' "$PAYLOAD" | python -m wukong_invite.ops parse-js 2>/dev/null)"; then
      if [ -n "$IMAGE_URL" ] && [ "$IMAGE_URL" != "$LAST_IMAGE_URL" ]; then
        LAST_IMAGE_URL="$IMAGE_URL"
        TMP_DIR="$(mktemp -d /tmp/wukong-invite.XXXXXX)"
        IMAGE_PATH="$TMP_DIR/invite.png"
        if curl -fsSL -H 'Cache-Control: no-cache' -o "$IMAGE_PATH" "$IMAGE_URL" 2>/dev/null; then
          if CODE="$(python -m wukong_invite.ops extract-code --image "$IMAGE_PATH" 2>/dev/null)"; then
            NOTIFY_ARGS=(--code "$CODE" --sound-name "$SOUND_NAME")
            if [ "$ENABLE_CLIPBOARD" != "1" ]; then
              NOTIFY_ARGS+=(--no-clipboard)
            fi
            if [ "$ENABLE_SOUND" != "1" ]; then
              NOTIFY_ARGS+=(--no-sound)
            fi
            python -m wukong_invite.ops notify "${NOTIFY_ARGS[@]}" >/dev/null 2>&1 || true
            if [ "$AUTO_FILL_APP" = "1" ]; then
              FILL_ARGS=(--code "$CODE")
              if [ "$AUTO_SUBMIT_APP" != "1" ]; then
                FILL_ARGS+=(--no-submit)
              fi
              python -m wukong_invite.ops fill-app "${FILL_ARGS[@]}" >/dev/null 2>&1 || true
            fi
            printf '%s\n' "$CODE"
            rm -rf "$TMP_DIR"
            exit 0
          fi
        fi
        rm -rf "$TMP_DIR"
      fi
    fi
  fi
  sleep "$INTERVAL"
done

echo "timeout without invite code" >&2
exit 1
