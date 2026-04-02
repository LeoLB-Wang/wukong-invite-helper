from __future__ import annotations

import argparse
import sys
from typing import Literal
from pathlib import Path

from wukong_invite.core import (
    extract_image_asset_id,
    extract_invite_code,
    parse_invite_api_payload,
    parse_js_payload,
)
from wukong_invite.notify import copy_to_clipboard, play_alert


def cmd_parse_js() -> int:
    payload = sys.stdin.read()
    print(parse_js_payload(payload))
    return 0


def cmd_parse_api(field: Literal["code", "status", "next-release", "raw-code"]) -> int:
    """Read invite API JSON from stdin and print a selected field."""
    payload = sys.stdin.read()
    result = parse_invite_api_payload(payload)
    if field == "code":
        if not result.code:
            return 1
        print(result.code)
        return 0
    if field == "status":
        print(result.status)
        return 0
    if field == "next-release":
        if result.next_release_at:
            print(result.next_release_at)
        return 0
    if field == "raw-code":
        if result.raw_code:
            print(result.raw_code)
        return 0
    raise ValueError(f"Unsupported parse-api field: {field}")


def cmd_extract_code(image: str) -> int:
    from wukong_invite.ocr import create_ocr

    project_root = Path(__file__).resolve().parents[2]
    ocr = create_ocr(project_root)
    text = ocr.recognize_text(Path(image), project_root)
    print(extract_invite_code(text))
    return 0


def cmd_image_key(url: str) -> int:
    print(extract_image_asset_id(url))
    return 0


def cmd_notify(code: str, no_clipboard: bool, no_sound: bool, sound_name: str) -> int:
    if not no_clipboard:
        try:
            copy_to_clipboard(code)
        except Exception:
            pass
    if not no_sound:
        try:
            play_alert(sound_name)
        except Exception:
            pass
    return 0


def cmd_fill_app(code: str, no_submit: bool) -> int:
    try:
        from wukong_invite.autofill import fill_and_submit
        fill_and_submit(code, submit=not no_submit)
    except ImportError:
        print(
            "pyautogui is not installed. Install with: pip install wukong-invite-helper[autofill]",
            file=sys.stderr,
        )
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"autofill failed: {exc}", file=sys.stderr)
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Operational helpers for Wukong invite-code fetching.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("parse-js", help="Read JSONP payload from stdin and print the image URL")
    parse_api_parser = subparsers.add_parser(
        "parse-api",
        help="Read invite API JSON from stdin and print a selected field",
    )
    parse_api_parser.add_argument(
        "--field",
        choices=["code", "status", "next-release", "raw-code"],
        required=True,
        help="Which parsed field to print",
    )

    image_key_parser = subparsers.add_parser("image-key", help="Extract the numeric asset id from an invite image URL")
    image_key_parser.add_argument("--url", required=True, help="Invite image URL")

    extract_parser = subparsers.add_parser("extract-code", help="OCR an image and print the invite code")
    extract_parser.add_argument("--image", required=True, help="Path to the invite image")

    notify_parser = subparsers.add_parser("notify", help="Copy code to clipboard and play a sound")
    notify_parser.add_argument("--code", required=True, help="Invite code to copy/announce")
    notify_parser.add_argument("--no-clipboard", action="store_true", help="Do not copy the code to clipboard")
    notify_parser.add_argument("--no-sound", action="store_true", help="Do not play an alert sound")
    notify_parser.add_argument("--sound-name", default="Glass", help="macOS sound file name without extension")

    fill_parser = subparsers.add_parser("fill-app", help="Fill the invite code into Wukong app via keyboard simulation")
    fill_parser.add_argument("--code", required=True, help="Invite code to fill")
    fill_parser.add_argument("--no-submit", action="store_true", help="Fill only, do not click submit")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "parse-js":
        return cmd_parse_js()
    if args.command == "parse-api":
        return cmd_parse_api(args.field)
    if args.command == "extract-code":
        return cmd_extract_code(args.image)
    if args.command == "image-key":
        return cmd_image_key(args.url)
    if args.command == "notify":
        return cmd_notify(args.code, args.no_clipboard, args.no_sound, args.sound_name)
    if args.command == "fill-app":
        return cmd_fill_app(args.code, args.no_submit)
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
