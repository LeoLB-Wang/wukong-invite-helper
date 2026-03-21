"""Cross-platform autofill via OS-level keyboard simulation.

macOS:  osascript + System Events keystroke (avoids Python dock icon flash).
Windows/Linux:  pyautogui hotkey (requires ``pip install pyautogui``).

Strategy: clipboard copy -> activate window -> Cmd/Ctrl+A -> Cmd/Ctrl+V -> optional Enter.
"""
from __future__ import annotations

import platform
import subprocess
import time

from wukong_invite.notify import copy_to_clipboard


def activate_wukong_window() -> None:
    """Bring the Wukong window to the foreground (Windows only)."""
    system = platform.system()
    if system == "Windows":
        import pygetwindow as gw  # type: ignore[import-untyped]

        windows = gw.getWindowsWithTitle("Wukong")
        if windows:
            windows[0].activate()
        else:
            raise RuntimeError("Wukong window not found")
    else:
        raise RuntimeError(f"Window activation not supported on {system}")


def _fill_macos(submit: bool) -> None:
    """Activate Wukong and send keystrokes via osascript — no pyautogui needed."""
    enter_line = (
        "\n    delay 0.3\n    keystroke return" if submit else ""
    )
    script = (
        'tell application "Wukong" to activate\n'
        "delay 1.0\n"
        "tell application \"System Events\"\n"
        '    keystroke "a" using command down\n'
        "    delay 0.1\n"
        '    keystroke "v" using command down'
        f"{enter_line}\n"
        "end tell"
    )
    subprocess.run(
        ["osascript", "-e", script],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _fill_pyautogui(submit: bool) -> None:
    """Activate window and send hotkeys via pyautogui (Windows/Linux)."""
    import pyautogui  # type: ignore[import-untyped]

    activate_wukong_window()
    time.sleep(1.0)

    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.1)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.5)

    if submit:
        pyautogui.press("enter")


def fill_and_submit(code: str, submit: bool = False) -> None:
    """Fill an invite code into the active Wukong input field.

    1. Copy *code* to the system clipboard.
    2. Activate the Wukong window.
    3. Select-all + paste via OS-level keystrokes.
    4. Optionally press Enter to submit.
    """
    copy_to_clipboard(code)

    if platform.system() == "Darwin":
        _fill_macos(submit)
    else:
        _fill_pyautogui(submit)
