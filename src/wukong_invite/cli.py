from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path
from typing import Final
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from wukong_invite.core import (
    extract_image_asset_id,
    extract_invite_code,
    parse_js_payload,
)
from wukong_invite.notify import copy_to_clipboard, play_alert
from wukong_invite.ops import cmd_fill_app
from wukong_invite.ocr import OCREngine, create_ocr


DEFAULT_JS_URL: Final[str] = (
    "https://hudong.alicdn.com/api/data/v2/438eae9715f945468d599660d2d92aeb.js"
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
    request = Request(
        url, headers={"User-Agent": USER_AGENT, "Cache-Control": "no-cache"}
    )
    try:
        with urlopen(request, timeout=20) as response:
            target.write_bytes(response.read())
    except (HTTPError, URLError, OSError) as exc:
        raise RuntimeError(f"request failed for {url}: {exc}") from exc


def run_once(js_url: str, ocr: OCREngine, project_root: Path) -> str:
    payload = fetch_text(js_url)
    image_url = parse_js_payload(payload)
    with tempfile.TemporaryDirectory(prefix="wukong-invite-") as temp_dir:
        image_path = Path(temp_dir) / "invite.png"
        download_file(image_url, image_path)
        text = ocr.recognize_text(image_path, project_root)
    return extract_invite_code(text)


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
        cmd_fill_app(code, no_submit=False)
    except Exception as e:
        _log(f"autofill error: {e}")


def watch(
    js_url: str,
    interval: float,
    timeout_seconds: int,
    project_root: Path,
    seen_ids_file: Path,
) -> int:
    ocr = create_ocr(project_root)
    deadline = time.time() + timeout_seconds
    seen_ids_file.parent.mkdir(parents=True, exist_ok=True)
    seen_ids = _load_seen_ids(seen_ids_file)
    last_error = None

    while time.time() < deadline:
        asset_id = None
        try:
            payload = fetch_text(js_url)
            image_url = parse_js_payload(payload)
            asset_id = extract_image_asset_id(image_url)
            if asset_id not in seen_ids:
                with tempfile.TemporaryDirectory(prefix="wukong-invite-") as temp_dir:
                    image_path = Path(temp_dir) / "invite.png"
                    download_file(image_url, image_path)
                    text = ocr.recognize_text(image_path, project_root)
                code = extract_invite_code(text)
                seen_ids.add(asset_id)
                _append_seen_id(seen_ids_file, asset_id)
                _log(f"saved seen asset id [{asset_id}] to {seen_ids_file}")
                _best_effort_notify(code)
                print(code)
                return 0
        except (ValueError, RuntimeError) as exc:
            last_error = exc

        time.sleep(interval)

    if last_error:
        print(f"timeout without invite code: {last_error}", file=sys.stderr)
    else:
        print("timeout without invite code", file=sys.stderr)
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch and extract the current Wukong invite code."
    )
    parser.add_argument(
        "--js-url",
        default=DEFAULT_JS_URL,
        help="JSONP endpoint that returns the image URL",
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
        help="File to persist seen asset IDs (one per line)",
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
