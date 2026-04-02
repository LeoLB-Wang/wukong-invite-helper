from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Final
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from wukong_invite.core import parse_invite_api_payload
from wukong_invite.notify import copy_to_clipboard, play_alert
from wukong_invite.ops import cmd_fill_app


DEFAULT_API_URL: Final[str] = (
    "https://ai-table-api.dingtalk.com/v1/wukong/invite-code"
)
USER_AGENT: Final[str] = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"
)


def fetch_text(url: str) -> str:
    request = Request(
        url, headers={"User-Agent": USER_AGENT, "Cache-Control": "no-cache"}
    )
    try:
        with urlopen(request, timeout=20) as response:
            encoding = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(encoding)
    except (HTTPError, URLError, OSError) as exc:
        raise RuntimeError(f"request failed for {url}: {exc}") from exc


def download_file(url: str, target: Path) -> None:
    """Download a binary payload to disk."""
    request = Request(
        url, headers={"User-Agent": USER_AGENT, "Cache-Control": "no-cache"}
    )
    try:
        with urlopen(request, timeout=20) as response:
            target.write_bytes(response.read())
    except (HTTPError, URLError, OSError) as exc:
        raise RuntimeError(f"request failed for {url}: {exc}") from exc


def run_once(api_url: str) -> str:
    """Fetch the current invite code once from the direct JSON API."""
    payload = fetch_text(api_url)
    result = parse_invite_api_payload(payload)
    if result.code:
        return result.code
    next_release_at = result.next_release_at or "unknown"
    raw_code = result.raw_code or "<missing>"
    raise RuntimeError(
        f"invite code not released yet: raw_code={raw_code} next_release_at={next_release_at}"
    )


def _load_seen_ids(path: Path) -> set[str]:
    """Load seen asset IDs from file (one per line, # comments allowed)."""
    ids: set[str] = set()
    if not path.exists():
        return ids
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            ids.add(line)
    return ids


def _append_seen_id(path: Path, asset_id: str) -> None:
    """Append a single asset ID to the seen-ids file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(asset_id + "\n")


def _log(message: str) -> None:
    print(f"[wukong-invite-helper] {message}", file=sys.stderr)


def _best_effort_notify(code: str) -> None:
    try:
        copy_to_clipboard(code)
    except Exception as e:
        _log(f"clipboard error: {e}")
    try:
        play_alert("Glass")
    except Exception:
        pass
    try:
        result = cmd_fill_app(code, no_submit=False)
        if result != 0:
            raise RuntimeError(f"fill-app exited with status {result}")
    except Exception as e:
        _log(f"autofill error: {e}")


def _build_wait_message(next_release_at: str | None, raw_code: str | None) -> str:
    """Describe why the invite code is not usable yet."""
    if next_release_at:
        return f"invite code not released yet; next release at {next_release_at}"
    if raw_code:
        return f"invite code not released yet; current code is {raw_code}"
    return "invite code not released yet"


def watch(
    js_url: str,
    interval: float,
    timeout_seconds: int,
    project_root: Path,
    seen_ids_file: Path,
) -> int:
    deadline = time.time() + timeout_seconds
    last_error = None
    last_wait_message = None

    while time.time() < deadline:
        try:
            payload = fetch_text(js_url)
            result = parse_invite_api_payload(payload)
            if result.code:
                code = result.code
                _log(f"invite code ready [{code}]")
                _best_effort_notify(code)
                print(code)
                return 0
            last_wait_message = _build_wait_message(
                result.next_release_at, result.raw_code
            )
            _log(last_wait_message)
        except (ValueError, RuntimeError) as exc:
            last_error = exc

        time.sleep(interval)

    if last_error:
        print(f"timeout without invite code: {last_error}", file=sys.stderr)
    elif last_wait_message:
        print(f"timeout without invite code: {last_wait_message}", file=sys.stderr)
    else:
        print("timeout without invite code", file=sys.stderr)
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch and extract the current Wukong invite code."
    )
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
        "--timeout-seconds",
        type=int,
        default=300,
        help="How long to keep polling before giving up",
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
    return watch(
        js_url=args.js_url,
        interval=args.interval,
        timeout_seconds=args.timeout_seconds,
        project_root=project_root,
        seen_ids_file=seen_ids_file,
    )


if __name__ == "__main__":
    raise SystemExit(main())
