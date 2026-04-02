from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from wukong_invite.core import parse_invite_api_payload
from wukong_invite.notify import copy_to_clipboard, play_alert
from wukong_invite.ops import cmd_fill_app


DEFAULT_API_URL = (
    "https://ai-table-api.dingtalk.com/v1/wukong/invite-code"
)


def fetch_text(url: str) -> str:
    from wukong_invite.cli import fetch_text as cli_fetch_text

    return cli_fetch_text(url)


def download_file(url: str, target: Path) -> None:
    from wukong_invite.cli import download_file as cli_download_file

    cli_download_file(url, target)


def _best_effort_notify(code: str) -> None:
    try:
        copy_to_clipboard(code)
    except Exception as e:
        print(f"[wukong-invite-helper] clipboard error: {e}", file=sys.stderr)
    try:
        play_alert("Glass")
    except Exception:
        pass
    try:
        result = cmd_fill_app(code, no_submit=True)
        if result != 0:
            raise RuntimeError(f"fill-app exited with status {result}")
    except Exception as e:
        print(f"[wukong-invite-helper] autofill error: {e}", file=sys.stderr)


class InviteWatchService:
    def __init__(
        self,
        project_root: Path,
        seen_ids_file: Path,
        *,
        js_url: str = DEFAULT_API_URL,
        interval: float = 1.0,
        fetch_text_func: Callable[[str], str] = fetch_text,
        download_file_func: Callable[[str, Path], None] = download_file,
        create_ocr_func: Callable[[Path], object] | None = None,
        notify_func: Callable[[str], None] = _best_effort_notify,
    ) -> None:
        self.project_root = project_root
        self.seen_ids_file = seen_ids_file
        self.js_url = js_url
        self.interval = interval
        self.fetch_text = fetch_text_func
        self.download_file = download_file_func
        self.create_ocr = create_ocr_func
        self.notify = notify_func

        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._logs: deque[str] = deque(maxlen=50)
        self._latest_code: str | None = None
        self._latest_asset_id: str | None = None
        self._latest_image_url: str | None = None
        self._next_release_at: str | None = None
        self._last_success_at: str | None = None
        self._last_error: str | None = None
        self._last_result: str = "idle"

        self.seen_ids_file.parent.mkdir(parents=True, exist_ok=True)
        self._seen_ids = self._load_seen_ids()
        self._log(f"loaded {len(self._seen_ids)} seen id(s) from {self.seen_ids_file}")

    def _load_seen_ids(self) -> set[str]:
        ids: set[str] = set()
        if not self.seen_ids_file.exists():
            return ids
        for line in self.seen_ids_file.read_text().splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                ids.add(line)
        return ids

    def _write_seen_ids(self) -> None:
        lines = [f"{asset_id}\n" for asset_id in sorted(self._seen_ids)]
        self.seen_ids_file.write_text("".join(lines))

    def _append_seen_id(self, asset_id: str) -> None:
        if asset_id in self._seen_ids:
            return
        self._seen_ids.add(asset_id)
        self.seen_ids_file.parent.mkdir(parents=True, exist_ok=True)
        with self.seen_ids_file.open("a") as handle:
            handle.write(asset_id + "\n")
        self._log(f"saved seen asset id [{asset_id}] to {self.seen_ids_file}")

    def _log(self, message: str) -> None:
        entry = f"[wukong-invite-helper] {message}"
        with self._lock:
            self._logs.append(entry)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "running": self._thread is not None and self._thread.is_alive(),
                "latest_code": self._latest_code,
                "latest_asset_id": self._latest_asset_id,
                "latest_image_url": self._latest_image_url,
                "next_release_at": self._next_release_at,
                "last_success_at": self._last_success_at,
                "last_error": self._last_error,
                "last_result": self._last_result,
                "interval": self.interval,
                "logs": list(self._logs),
                "seen_ids": sorted(self._seen_ids),
            }

    def clear_seen_id(self, asset_id: str) -> bool:
        with self._lock:
            if asset_id not in self._seen_ids:
                return False
            self._seen_ids.remove(asset_id)
            self._write_seen_ids()
            self._log(f"cleared seen asset id [{asset_id}] from {self.seen_ids_file}")
            return True

    def retry_now(self) -> dict:
        return self._poll_once(force=True)

    def start(self) -> bool:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            self._stop_event = threading.Event()
            self._thread = threading.Thread(
                target=self._run_loop, name="wukong-webui-watch", daemon=True
            )
            self._thread.start()
            self._log("watcher started")
            return True

    def stop(self) -> bool:
        with self._lock:
            thread = self._thread
            if thread is None or not thread.is_alive():
                self._thread = None
                return False
            self._stop_event.set()
        thread.join(timeout=max(self.interval, 1.0) + 1.0)
        with self._lock:
            self._thread = None
            self._log("watcher stopped")
        return True

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            self._poll_once(force=False)
            self._stop_event.wait(self.interval)

    def _poll_once(self, *, force: bool) -> dict:
        try:
            payload = self.fetch_text(self.js_url)
            result = parse_invite_api_payload(payload)
            with self._lock:
                self._next_release_at = result.next_release_at

            if result.code:
                code = result.code
                with self._lock:
                    self._latest_code = code
                    self._last_success_at = time.strftime("%Y-%m-%d %H:%M:%S")
                    self._last_result = "ok"
                    self._last_error = None
                self.notify(code)
                self._log(f"invite code ready [{code}]")
                return {"status": "ok", "code": code}

            message = "invite code not released yet"
            if result.next_release_at:
                message = f"{message}; next release at {result.next_release_at}"
            elif result.raw_code:
                message = f"{message}; current code is {result.raw_code}"
            with self._lock:
                self._latest_code = None
                self._last_result = "waiting"
                self._last_error = None
            self._log(message)
            return {
                "status": "waiting",
                "next_release_at": result.next_release_at,
                "raw_code": result.raw_code,
            }
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self._last_error = str(exc)
                self._last_result = "error"
            self._log(f"processing failed: {exc}")
            return {"status": "error", "error": str(exc)}


def _render_html() -> bytes:
    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Wukong Invite Helper</title>
  <style>
    :root { color-scheme: light; --bg:#f5efe6; --panel:#fffdf8; --ink:#1e1b18; --muted:#6a6258; --line:#d8c9b6; --accent:#b85c38; --ok:#2f7d4a; }
    body { margin:0; font-family: "PingFang SC","Noto Sans SC",sans-serif; background:linear-gradient(180deg,#f1e7d8,#fbf7ef); color:var(--ink); }
    .wrap { max-width: 980px; margin: 0 auto; padding: 24px; }
    .hero { display:grid; gap:16px; margin-bottom:20px; }
    .card { background:var(--panel); border:1px solid var(--line); border-radius:18px; padding:20px; box-shadow:0 10px 30px rgba(65,42,23,.08); }
    .card.wide { grid-column: 1 / -1; }
    h1,h2 { margin:0 0 12px; }
    .muted { color:var(--muted); }
    .row { display:flex; gap:12px; flex-wrap:wrap; }
    .console-panel { padding:16px; border:1px solid #e7d8c6; border-radius:16px; background:linear-gradient(180deg,#fffaf2,#f8efe3); }
    .console-panel + .console-panel { margin-top:12px; }
    .console-actions { display:flex; gap:12px; flex-wrap:wrap; align-items:center; }
    .console-label { margin:0 0 10px; font-size:13px; font-weight:700; letter-spacing:.04em; color:#7c5f45; text-transform:uppercase; }
    button { border:0; border-radius:999px; padding:10px 16px; background:var(--accent); color:white; cursor:pointer; font-weight:600; }
    button.alt { background:#6f7c85; }
    button.warn { background:#8f3b2e; }
    button.loading { opacity:.7; cursor:progress; }
    input { border:1px solid var(--line); border-radius:12px; padding:10px 12px; min-width:220px; }
    .grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(260px,1fr)); gap:16px; }
    pre { margin:0; white-space:pre-wrap; word-break:break-word; font-size:13px; line-height:1.5; max-height:320px; overflow:auto; }
    #logs { min-height:240px; max-height:420px; }
    .code { font-size: 32px; font-weight: 700; letter-spacing: 2px; color: var(--ok); }
    .pill { display:inline-block; padding:4px 10px; border-radius:999px; background:#eee1d0; color:#5a493c; font-size:12px; }
    .status-pill { display:inline-flex; align-items:center; gap:8px; padding:6px 12px; border-radius:999px; font-size:13px; font-weight:700; }
    .status-pill::before { content:''; width:9px; height:9px; border-radius:999px; display:inline-block; }
    .status-running { background:#e7f6ea; color:#205d35; }
    .status-running::before { background:#2f9e5a; box-shadow:0 0 0 4px rgba(47,158,90,.16); }
    .status-stopped { background:#efe5d8; color:#8a5c2f; }
    .status-stopped::before { background:#c5873f; box-shadow:0 0 0 4px rgba(197,135,63,.16); }
    .banner { display:none; margin-top:12px; padding:12px 14px; border-radius:14px; background:#e7f6ea; border:1px solid #b9dfc3; color:#205d35; font-weight:600; }
    .toast { position:fixed; right:20px; bottom:20px; display:none; padding:12px 14px; border-radius:14px; background:#1f4d35; color:#fff; box-shadow:0 10px 30px rgba(0,0,0,.15); }
    .log-line { display:block; padding:2px 0; }
    .log-info { color:#5e554c; }
    .log-success { color:#205d35; }
    .log-warn { color:#8a5a10; }
    .log-error { color:#8f2d20; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <div class="card">
        <h1>Wukong Invite Helper</h1>
        <div class="muted">开始监听、停止监听、手动重试当前邀请码接口。</div>
        <div id="successBanner" class="banner">已发现可用邀请码。</div>
      </div>
    </div>
    <div class="grid">
      <div class="card">
        <h2>控制台</h2>
        <div class="console-panel">
          <div class="console-label">监听控制</div>
          <div class="console-actions">
            <button data-label="开始监听" onclick="post('/api/start', null, this)">开始监听</button>
            <button class="alt" data-label="停止监听" onclick="post('/api/stop', null, this)">停止监听</button>
            <button class="warn" data-label="手动重试" onclick="post('/api/retry', null, this)">手动重试</button>
          </div>
          <div class="muted" style="margin-top:10px">
            开始监听后会按设定间隔持续轮询邀请码接口；停止监听后会结束后台轮询。
          </div>
          <div class="muted" style="margin-top:6px">
            手动重试会立即重新请求当前邀请码接口，不需要等待下一轮轮询，也不受监听是否开启影响。
          </div>
        </div>
      </div>
      <div class="card">
        <h2>当前状态</h2>
        <div>运行状态：<span id="running" class="status-pill status-stopped">已停止</span></div>
        <div style="margin-top:10px">下次刷新：<strong id="countdownValue">-</strong></div>
        <div style="margin-top:10px">下个放量时间：<strong id="nextReleaseAt">-</strong></div>
        <div style="margin-top:10px">最新邀请码：</div>
        <div id="latestCode" class="code">-</div>
        <div class="row" style="margin-top:12px">
          <button class="alt" data-label="复制邀请码" onclick="copyCode(this)">复制邀请码</button>
        </div>
        <div style="margin-top:10px">最近一次成功时间：<span id="lastSuccessAt">-</span></div>
        <div style="margin-top:10px">最新结果：<span id="lastResult">-</span></div>
        <div style="margin-top:10px">最近错误：<span id="lastError" class="muted">-</span></div>
      </div>
      <div class="card wide">
        <h2>最近日志</h2>
        <pre id="logs"></pre>
      </div>
    </div>
  </div>
  <div id="toast" class="toast">已复制邀请码</div>
  <script>
    function setButtonLoading(button, loading) {
      if (!button) return;
      if (!button.dataset.label) button.dataset.label = button.textContent.trim();
      button.disabled = loading;
      button.classList.toggle('loading', loading);
      button.textContent = loading ? `${button.dataset.label}...` : button.dataset.label;
    }
    async function post(path, payload, button) {
      setButtonLoading(button, true);
      try {
        const res = await fetch(path, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: payload ? JSON.stringify(payload) : '{}'
        });
        const data = await res.json();
        await refresh();
        return data;
      } finally {
        setButtonLoading(button, false);
      }
    }
    async function copyCode(button) {
      const code = document.getElementById('latestCode').textContent.trim();
      if (!code || code === '-') return;
      setButtonLoading(button, true);
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(code);
          showBanner(`已复制邀请码：${code}`);
          showToast(`已复制邀请码：${code}`);
          return;
        }
        const input = document.createElement('textarea');
        input.value = code;
        document.body.appendChild(input);
        input.select();
        document.execCommand('copy');
        document.body.removeChild(input);
        showBanner(`已复制邀请码：${code}`);
        showToast(`已复制邀请码：${code}`);
      } finally {
        setButtonLoading(button, false);
      }
    }
    function showBanner(message) {
      const banner = document.getElementById('successBanner');
      banner.textContent = message;
      banner.style.display = 'block';
    }
    function showToast(message) {
      const toast = document.getElementById('toast');
      toast.textContent = message;
      toast.style.display = 'block';
      clearTimeout(showToast._timer);
      showToast._timer = setTimeout(() => {
        toast.style.display = 'none';
      }, 2200);
    }
    function renderNextRefresh(intervalSeconds) {
      if (intervalSeconds == null) {
        document.getElementById('countdownValue').textContent = '-';
        return;
      }
      document.getElementById('countdownValue').textContent = `约 ${Number(intervalSeconds).toFixed(1)} 秒后`;
    }
    function renderLogs(items) {
      const logs = document.getElementById('logs');
      logs.innerHTML = '';
      for (const entry of (items || [])) {
        const line = document.createElement('span');
        line.className = 'log-line log-info';
        const lowered = entry.toLowerCase();
        if (lowered.includes('saved seen asset id') || lowered.includes('invite code ready') || lowered.includes('started') || lowered.includes('stopped')) {
          line.className = 'log-line log-success';
        } else if (lowered.includes('failed') || lowered.includes('error')) {
          line.className = 'log-line log-error';
        } else if (lowered.includes('waiting') || lowered.includes('next release')) {
          line.className = 'log-line log-warn';
        }
        line.textContent = entry;
        logs.appendChild(line);
      }
      logs.scrollTop = logs.scrollHeight;
    }
    async function refresh() {
      const res = await fetch('/api/state');
      const data = await res.json();
      const running = document.getElementById('running');
      running.textContent = data.running ? '监听中' : '已停止';
      running.className = data.running ? 'status-pill status-running' : 'status-pill status-stopped';
      document.getElementById('lastSuccessAt').textContent = data.last_success_at || '-';
      document.getElementById('nextReleaseAt').textContent = data.next_release_at || '-';
      document.getElementById('latestCode').textContent = data.latest_code || '-';
      document.getElementById('lastResult').textContent = data.last_result || '-';
      document.getElementById('lastError').textContent = data.last_error || '-';
      renderLogs(data.logs || []);
      if (data.latest_code) {
        showBanner(`已发现可用邀请码：${data.latest_code}`);
      }
      renderNextRefresh(data.interval || 1.5);
    }
    refresh();
    setInterval(refresh, 1500);
  </script>
</body>
</html>
""".encode("utf-8")


def create_http_server(
    host: str, port: int, service: InviteWatchService
) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/":
                self._send_bytes(200, "text/html; charset=utf-8", _render_html())
                return
            if self.path == "/api/state":
                self._send_json(200, service.snapshot())
                return
            self._send_json(404, {"status": "not_found"})

        def do_POST(self) -> None:  # noqa: N802
            route = urlparse(self.path).path
            payload = self._read_json()
            if route == "/api/start":
                started = service.start()
                self._send_json(
                    200,
                    {"status": "ok", "started": started, "state": service.snapshot()},
                )
                return
            if route == "/api/stop":
                stopped = service.stop()
                self._send_json(
                    200,
                    {"status": "ok", "stopped": stopped, "state": service.snapshot()},
                )
                return
            if route == "/api/retry":
                self._send_json(200, service.retry_now())
                return
            self._send_json(404, {"status": "not_found"})

        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            return

        def _read_json(self) -> dict:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                return {}
            raw = self.rfile.read(length).decode("utf-8")
            if not raw.strip():
                return {}
            return json.loads(raw)

        def _send_json(self, status: int, payload: dict) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._send_bytes(status, "application/json; charset=utf-8", data)

        def _send_bytes(self, status: int, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return ThreadingHTTPServer((host, port), Handler)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the local Web UI for Wukong invite watching."
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind")
    parser.add_argument("--port", type=int, default=8787, help="Port to bind")
    parser.add_argument(
        "--api-url",
        "--js-url",
        dest="js_url",
        default=DEFAULT_API_URL,
        help="Invite code API endpoint",
    )
    parser.add_argument(
        "--interval", type=float, default=1.0, help="Polling interval in seconds"
    )
    parser.add_argument(
        "--seen-ids-file",
        default="data/seen_ids.txt",
        help="Deprecated legacy option; kept for CLI compatibility",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parents[2]
    seen_ids_file = Path(args.seen_ids_file)
    if not seen_ids_file.is_absolute():
        seen_ids_file = project_root / seen_ids_file

    service = InviteWatchService(
        project_root=project_root,
        seen_ids_file=seen_ids_file,
        js_url=args.js_url,
        interval=args.interval,
    )
    server = create_http_server(args.host, args.port, service)
    print(f"Web UI running at http://{args.host}:{args.port}", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        service.stop()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
