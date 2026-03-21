from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Final

from wukong_invite.core import extract_invite_code, parse_js_payload
from wukong_invite.ocr import OCREngine, create_ocr


DEFAULT_JS_URL: Final[str] = "https://hudong.alicdn.com/api/data/v2/438eae9715f945468d599660d2d92aeb.js"
USER_AGENT: Final[str] = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"
)


def fetch_text(url: str) -> str:
    result = subprocess.run(
        [
            "curl",
            "-fsSL",
            "-A",
            USER_AGENT,
            "-H",
            "Cache-Control: no-cache",
            url,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def download_file(url: str, target: Path) -> None:
    subprocess.run(
        [
            "curl",
            "-fsSL",
            "-A",
            USER_AGENT,
            "-H",
            "Cache-Control: no-cache",
            "-o",
            str(target),
            url,
        ],
        check=True,
    )


def run_once(js_url: str, ocr: OCREngine, project_root: Path) -> str:
    payload = fetch_text(js_url)
    image_url = parse_js_payload(payload)
    with tempfile.TemporaryDirectory(prefix="wukong-invite-") as temp_dir:
        image_path = Path(temp_dir) / "invite.png"
        download_file(image_url, image_path)
        text = ocr.recognize_text(image_path, project_root)
    return extract_invite_code(text)


def watch(js_url: str, interval: float, timeout_seconds: int, project_root: Path) -> int:
    ocr = create_ocr(project_root)
    deadline = time.time() + timeout_seconds
    seen_image_url = None
    last_error = None

    while time.time() < deadline:
        try:
            payload = fetch_text(js_url)
            image_url = parse_js_payload(payload)
            if image_url != seen_image_url:
                seen_image_url = image_url
                with tempfile.TemporaryDirectory(prefix="wukong-invite-") as temp_dir:
                    image_path = Path(temp_dir) / "invite.png"
                    download_file(image_url, image_path)
                    text = ocr.recognize_text(image_path, project_root)
                code = extract_invite_code(text)
                print(code)
                return 0
        except (ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
            last_error = exc

        time.sleep(interval)

    if last_error:
        print(f"timeout without invite code: {last_error}", file=sys.stderr)
    else:
        print("timeout without invite code", file=sys.stderr)
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch and extract the current Wukong invite code.")
    parser.add_argument("--js-url", default=DEFAULT_JS_URL, help="JSONP endpoint that returns the image URL")
    parser.add_argument("--interval", type=float, default=1.0, help="Polling interval in seconds")
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=300,
        help="How long to keep polling before giving up",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parents[2]
    return watch(
        js_url=args.js_url,
        interval=args.interval,
        timeout_seconds=args.timeout_seconds,
        project_root=project_root,
    )


if __name__ == "__main__":
    raise SystemExit(main())
