#!/usr/bin/env bash
set -euo pipefail

log() {
  printf '[wukong-invite-helper] %s\n' "$*" >&2
}

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# --------------- OS detection ---------------
OS_TYPE="$(uname -s)"
case "$OS_TYPE" in
  Darwin)               IS_MACOS=1 ;;
  MINGW*|MSYS*|CYGWIN*) IS_MACOS=0 ;;
  *)                    IS_MACOS=0 ;;
esac

# --------------- auto-install uv ---------------
if ! command -v uv &>/dev/null; then
  log "uv not found, installing..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  source "$HOME/.local/bin/env" 2>/dev/null || export PATH="$HOME/.local/bin:$PATH"
  if ! command -v uv &>/dev/null; then
    echo "failed to install uv. please install manually: https://docs.astral.sh/uv/" >&2
    exit 1
  fi
fi

# --------------- venv setup ---------------
if [ ! -d .venv ]; then
  mkdir -p .uv-cache
  UV_CACHE_DIR="$ROOT_DIR/.uv-cache" uv venv .venv
fi

if [ -f .venv/Scripts/activate ]; then
  # Windows (Git Bash / MSYS2)
  source .venv/Scripts/activate
else
  source .venv/bin/activate
fi

PYTHON_BIN="$(command -v python)"
if [[ "$PYTHON_BIN" != "$ROOT_DIR/.venv/"* ]]; then
  echo "python is not using project .venv: $PYTHON_BIN" >&2
  exit 1
fi

export PYTHONPATH="$ROOT_DIR/src"

# --------------- config ---------------
JS_URL="${1:-https://hudong.alicdn.com/api/data/v2/438eae9715f945468d599660d2d92aeb.js}"
INTERVAL="${INTERVAL:-1}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-300}"
ENABLE_CLIPBOARD="${ENABLE_CLIPBOARD:-1}"
ENABLE_SOUND="${ENABLE_SOUND:-1}"
SOUND_NAME="${SOUND_NAME:-Glass}"
AUTO_FILL_APP="${AUTO_FILL_APP:-1}"
AUTO_SUBMIT_APP="${AUTO_SUBMIT_APP:-1}"
DEADLINE=$(( $(date +%s) + TIMEOUT_SECONDS ))
ATTEMPT=0

# --------------- seen asset IDs (file-backed) ---------------
SEEN_IDS_FILE="${SEEN_IDS_FILE:-$ROOT_DIR/data/seen_ids.txt}"
mkdir -p "$(dirname "$SEEN_IDS_FILE")"
touch "$SEEN_IDS_FILE"

declare -A SEEN_IDS
_LOADED_COUNT=0
while IFS= read -r _line; do
  _line="${_line%%#*}"
  _line="$(echo "$_line" | tr -d '[:space:]')"
  if [ -n "$_line" ]; then
    SEEN_IDS["$_line"]=1
    _LOADED_COUNT=$((_LOADED_COUNT + 1))
  fi
done < "$SEEN_IDS_FILE"
log "loaded ${_LOADED_COUNT} seen id(s) from $SEEN_IDS_FILE"

# --------------- temp dir helper ---------------
make_tmp_dir() {
  if [ "$IS_MACOS" = "1" ]; then
    mktemp -d /tmp/wukong-invite.XXXXXX
  else
    mktemp -d "${TEMP:-/tmp}/wukong-invite.XXXXXX"
  fi
}

log "starting watcher: interval=${INTERVAL}s timeout=${TIMEOUT_SECONDS}s url=${JS_URL} os=${OS_TYPE}"

# --------------- main loop ---------------
while [ "$(date +%s)" -lt "$DEADLINE" ]; do
  ATTEMPT=$((ATTEMPT + 1))
  log "poll attempt #${ATTEMPT}"
  if PAYLOAD="$(curl -fsSL -H 'Cache-Control: no-cache' "$JS_URL" 2>/dev/null)"; then
    if IMAGE_URL="$(printf '%s' "$PAYLOAD" | python -m wukong_invite.ops parse-js 2>/dev/null)"; then
      if [ -n "$IMAGE_URL" ]; then
        ASSET_ID="$(python -m wukong_invite.ops image-key --url "$IMAGE_URL" 2>/dev/null)" || ASSET_ID=""
        if [ -z "$ASSET_ID" ]; then
          log "failed to extract asset id from image url"
        elif [ -n "${SEEN_IDS[$ASSET_ID]+_}" ]; then
          log "asset id [${ASSET_ID}] already seen"
        else
          log "detected new asset id [${ASSET_ID}]"
          TMP_DIR="$(make_tmp_dir)"
          IMAGE_PATH="$TMP_DIR/invite.png"
          SHOULD_MARK_SEEN=1
          if curl -fsSL -H 'Cache-Control: no-cache' -o "$IMAGE_PATH" "$IMAGE_URL" 2>/dev/null; then
            if CODE="$(python -m wukong_invite.ops extract-code --image "$IMAGE_PATH" 2>/dev/null)"; then
              log "ocr extracted invite code successfully"
              SEEN_IDS["$ASSET_ID"]=1
              echo "$ASSET_ID" >> "$SEEN_IDS_FILE"
              log "saved seen asset id [${ASSET_ID}] to $SEEN_IDS_FILE"
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
            log "ocr did not return a usable invite code"
            SHOULD_MARK_SEEN=0
          else
            log "failed to download invite image"
          fi
          rm -rf "$TMP_DIR"
          if [ "$SHOULD_MARK_SEEN" != "1" ]; then
            log "keeping asset id [${ASSET_ID}] eligible for retry"
          fi
        fi
      else
        log "parsed image url was empty"
      fi
    else
      log "failed to parse image url from payload"
    fi
  else
    log "failed to fetch js payload"
  fi
  sleep "$INTERVAL"
done

log "timeout without invite code"
exit 1
