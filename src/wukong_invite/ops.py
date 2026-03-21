from __future__ import annotations

import argparse
import platform
import subprocess
import sys
from pathlib import Path

from wukong_invite.core import extract_invite_code, parse_js_payload
from wukong_invite.notify import copy_to_clipboard, play_alert
from wukong_invite.ocr import create_ocr


def cmd_parse_js() -> int:
    payload = sys.stdin.read()
    print(parse_js_payload(payload))
    return 0


def cmd_extract_code(image: str) -> int:
    project_root = Path(__file__).resolve().parents[2]
    ocr = create_ocr(project_root)
    text = ocr.recognize_text(Path(image), project_root)
    print(extract_invite_code(text))
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
    if platform.system() != "Darwin":
        print("fill-app is only supported on macOS", file=sys.stderr)
        return 1

    submit_line = (
        """
        repeat 20 times
            if exists (first button of front window whose name is "立即体验") then
                exit repeat
            end if
            delay 0.2
        end repeat
        click (first button of front window whose name is "立即体验")
        """
        if not no_submit
        else ""
    )

    script = f"""
on run argv
set inviteCode to item 1 of argv
set the clipboard to inviteCode
tell application "Wukong" to activate
delay 0.8
tell application "System Events"
    tell process "DingTalkReal"
        set frontmost to true
        repeat 20 times
            if exists front window then
                exit repeat
            end if
            delay 0.2
        end repeat
        repeat 20 times
            if (count of text fields of front window) > 0 then
                exit repeat
            end if
            delay 0.2
        end repeat
        set targetField to text field 1 of front window
        click targetField
        delay 0.3
        keystroke "a" using command down
        delay 0.2
        key code 51
        delay 0.2
        keystroke "v" using command down
        delay 0.4
{submit_line}
    end tell
end tell
end run
"""
    subprocess.run(["osascript", "-e", script, code], check=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Operational helpers for Wukong invite-code fetching.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("parse-js", help="Read JSONP payload from stdin and print the image URL")

    extract_parser = subparsers.add_parser("extract-code", help="OCR an image and print the invite code")
    extract_parser.add_argument("--image", required=True, help="Path to the invite image")

    notify_parser = subparsers.add_parser("notify", help="Copy code to clipboard and play a sound")
    notify_parser.add_argument("--code", required=True, help="Invite code to copy/announce")
    notify_parser.add_argument("--no-clipboard", action="store_true", help="Do not copy the code to clipboard")
    notify_parser.add_argument("--no-sound", action="store_true", help="Do not play an alert sound")
    notify_parser.add_argument("--sound-name", default="Glass", help="macOS sound file name without extension")

    fill_parser = subparsers.add_parser("fill-app", help="Fill the invite code into Wukong.app (macOS only)")
    fill_parser.add_argument("--code", required=True, help="Invite code to fill")
    fill_parser.add_argument("--no-submit", action="store_true", help="Fill only, do not click submit")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "parse-js":
        return cmd_parse_js()
    if args.command == "extract-code":
        return cmd_extract_code(args.image)
    if args.command == "notify":
        return cmd_notify(args.code, args.no_clipboard, args.no_sound, args.sound_name)
    if args.command == "fill-app":
        return cmd_fill_app(args.code, args.no_submit)
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
