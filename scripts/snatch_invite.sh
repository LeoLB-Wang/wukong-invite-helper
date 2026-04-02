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
API_URL="${1:-https://ai-table-api.dingtalk.com/v1/wukong/invite-code}"
INTERVAL="${INTERVAL:-1}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-300}"
ENABLE_CLIPBOARD="${ENABLE_CLIPBOARD:-1}"
ENABLE_SOUND="${ENABLE_SOUND:-1}"
SOUND_NAME="${SOUND_NAME:-Glass}"
AUTO_FILL_APP="${AUTO_FILL_APP:-1}"
AUTO_SUBMIT_APP="${AUTO_SUBMIT_APP:-1}"
DEADLINE=$(( $(date +%s) + TIMEOUT_SECONDS ))
ATTEMPT=0

log "starting watcher: interval=${INTERVAL}s timeout=${TIMEOUT_SECONDS}s url=${API_URL} os=${OS_TYPE}"

# --------------- main loop ---------------
while [ "$(date +%s)" -lt "$DEADLINE" ]; do
  ATTEMPT=$((ATTEMPT + 1))
  log "poll attempt #${ATTEMPT}"
  if PAYLOAD="$(curl -fsSL -H 'Cache-Control: no-cache' "$API_URL" 2>/dev/null)"; then
    if CODE="$(printf '%s' "$PAYLOAD" | python -m wukong_invite.ops parse-api --field code 2>/dev/null)"; then
      log "invite code ready [${CODE}]"
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
      exit 0
    else
      NEXT_RELEASE_AT="$(printf '%s' "$PAYLOAD" | python -m wukong_invite.ops parse-api --field next-release 2>/dev/null || true)"
      RAW_CODE="$(printf '%s' "$PAYLOAD" | python -m wukong_invite.ops parse-api --field raw-code 2>/dev/null || true)"
      if [ -n "$NEXT_RELEASE_AT" ]; then
        log "invite code not released yet; next release at ${NEXT_RELEASE_AT}"
      elif [ -n "$RAW_CODE" ]; then
        log "invite code not released yet; current code is ${RAW_CODE}"
      else
        log "invite code not released yet"
      fi
    fi
  else
    log "failed to fetch invite api payload"
  fi
  sleep "$INTERVAL"
done

log "timeout without invite code"
exit 1
