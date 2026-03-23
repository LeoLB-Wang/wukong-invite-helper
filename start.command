#!/bin/bash
# ============================================
#  悟空邀请码助手 — macOS 一键启动
#  双击此文件即可运行，无需任何手动配置
# ============================================
set -euo pipefail

cd "$(dirname "$0")"

PORT="${PORT:-8787}"
HOST="${HOST:-127.0.0.1}"

printf '\n'
printf '  ╔══════════════════════════════════════╗\n'
printf '  ║     悟空邀请码助手 · 一键启动        ║\n'
printf '  ╚══════════════════════════════════════╝\n'
printf '\n'

# --------------- auto-install uv ---------------
if ! command -v uv &>/dev/null; then
  printf '[setup] 未检测到 uv，正在自动安装...\n'
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # make uv available in current shell
  source "$HOME/.local/bin/env" 2>/dev/null || export PATH="$HOME/.local/bin:$PATH"
  if ! command -v uv &>/dev/null; then
    printf '[error] uv 安装失败，请手动安装: https://docs.astral.sh/uv/\n'
    printf '按回车键退出...\n'
    read -r
    exit 1
  fi
  printf '[setup] uv 安装完成 ✓\n'
fi

printf '[setup] 正在准备运行环境（首次启动需下载依赖，请稍候）...\n'

# --------------- sync environment ---------------
UV_CACHE_DIR="$PWD/.uv-cache"
UV_LINK_MODE="${UV_LINK_MODE:-copy}"
mkdir -p "$UV_CACHE_DIR"
sync_env() {
  uv sync --link-mode copy --cache-dir "$UV_CACHE_DIR" --no-editable --no-install-project
  return $?
}

if ! sync_env; then
  printf '[warn] First dependency sync failed. Retrying once...\n'
  sleep 2
  sync_env
fi

if [[ ! -x ".venv/bin/python" ]]; then
  printf '[error] .venv/bin/python was not created.\n'
  printf '按回车键退出...\n'
  read -r
  exit 1
fi
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"

# --------------- auto-open browser ---------------
(sleep 2 && open "http://${HOST}:${PORT}") &

printf '[start] Web UI 启动中 → http://%s:%s\n' "$HOST" "$PORT"
printf '[start] 浏览器将自动打开，关闭此窗口即可停止服务\n\n'

# --------------- launch ---------------
# 环境已准备完成，直接使用项目虚拟环境启动
.venv/bin/python -m wukong_invite.webui --host "$HOST" --port "$PORT"
