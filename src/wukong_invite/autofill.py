"""Cross-platform autofill via OS-level keyboard simulation.

macOS:  osascript + System Events keystroke (avoids Python dock icon flash).
Windows/Linux:  pyautogui hotkey (requires ``pip install pyautogui``).

Strategy: clipboard copy -> activate window -> Cmd/Ctrl+A -> Cmd/Ctrl+V -> optional Enter.
"""

from __future__ import annotations

import logging
import platform
import subprocess
import time

from wukong_invite.notify import copy_to_clipboard

logger = logging.getLogger(__name__)


def _find_wukong_window() -> int | None:
    """Return the hwnd of the Wukong app window, or None if not found / not visible."""
    if platform.system() != "Windows":
        return None
    try:
        import ctypes

        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        import pygetwindow as gw  # type: ignore[import-untyped]

        all_matches = gw.getWindowsWithTitle("Wukong")
        app_windows = [w for w in all_matches if "Invite Helper" not in (w.title or "")]
        target = app_windows or all_matches
        if not target:
            return None

        hwnd = target[0]._hWnd
        # Check window is visible (not hidden / not zero-size)
        if not user32.IsWindowVisible(hwnd):
            return None
        return hwnd
    except Exception:
        return None


def _set_foreground_win32(hwnd: int) -> bool:
    """Try to bring a window to the foreground using Win32 API directly.

    On Windows, SetForegroundWindow is restricted by UIPI.  We work around it
    by briefly attaching our thread's input to the target window's message queue.
    Returns True on success.
    """
    import ctypes

    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

    # Set argtypes for 64-bit correctness
    user32.IsIconic.argtypes = [ctypes.c_void_p]
    user32.IsIconic.restype = ctypes.c_bool
    user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user32.ShowWindow.restype = ctypes.c_bool
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    user32.GetWindowThreadProcessId.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_ulong),
    ]
    user32.GetWindowThreadProcessId.restype = ctypes.c_ulong
    user32.AttachThreadInput.argtypes = [
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_bool,
    ]
    user32.AttachThreadInput.restype = ctypes.c_bool
    user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
    user32.SetForegroundWindow.restype = ctypes.c_bool
    user32.BringWindowToTop.argtypes = [ctypes.c_void_p]
    user32.BringWindowToTop.restype = ctypes.c_bool
    kernel32.GetCurrentThreadId.restype = ctypes.c_ulong

    SW_SHOW = 5
    SW_RESTORE = 9

    # If minimized, restore first
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
        time.sleep(0.3)

    # Check if already foreground
    fg = user32.GetForegroundWindow()
    if fg == hwnd:
        return True

    # Get target window's thread ID
    target_tid = user32.GetWindowThreadProcessId(hwnd, None)
    our_tid = kernel32.GetCurrentThreadId()

    # Attach input to allow SetForegroundWindow
    attached = user32.AttachThreadInput(our_tid, target_tid, True)

    try:
        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)
        user32.ShowWindow(hwnd, SW_SHOW)
        time.sleep(0.3)
        return user32.GetForegroundWindow() == hwnd
    finally:
        if attached:
            user32.AttachThreadInput(our_tid, target_tid, False)


def activate_wukong_window() -> bool:
    """Bring the Wukong window to the foreground (Windows only).

    Returns True if the window was successfully activated, False otherwise.
    """
    system = platform.system()
    if system != "Windows":
        raise RuntimeError(f"Window activation not supported on {system}")

    hwnd = _find_wukong_window()
    if hwnd is None:
        logger.info("Wukong window not found or not visible — skipping autofill")
        return False

    import pygetwindow as gw  # type: ignore[import-untyped]

    all_matches = gw.getWindowsWithTitle("Wukong")
    app_windows = [w for w in all_matches if "Invite Helper" not in (w.title or "")]
    target = app_windows or all_matches
    logger.info("Found Wukong window: %s (hwnd=%s)", target[0].title, hwnd)

    # Try Win32 API first (more reliable than pygetwindow.activate)
    success = _set_foreground_win32(hwnd)
    if success:
        logger.info("Window activated via Win32 API")
        return True

    # Fallback: pygetwindow activate
    try:
        target[0].activate()
        time.sleep(0.3)
        fg = gw.getActiveWindow()
        if fg and fg._hWnd == hwnd:
            logger.info("Window activated via pygetwindow.activate()")
            return True
    except Exception:
        logger.debug("pygetwindow.activate() also failed")

    logger.warning(
        "Could not activate Wukong window. "
        "Please click on the Wukong app window once to give it focus."
    )
    return False


def _fill_macos(submit: bool) -> None:
    """Activate Wukong and send keystrokes via osascript — no pyautogui needed."""
    enter_line = "\n    delay 0.3\n    keystroke return" if submit else ""
    script = (
        'tell application "Wukong" to activate\n'
        "delay 1.0\n"
        'tell application "System Events"\n'
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


def _send_paste_win32() -> None:
    """Send Ctrl+V via SendInput (more reliable than pyautogui on some systems)."""
    import ctypes

    user32 = ctypes.windll.user32  # type: ignore[attr-defined]

    INPUT_KEYBOARD = 1
    KEYEVENTF_KEYUP = 0x0002
    VK_CONTROL = 0x11
    VK_V = 0x56

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", ctypes.c_ushort),
            ("wScan", ctypes.c_ushort),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class INPUT(ctypes.Structure):
        _fields_ = [
            ("type", ctypes.c_ulong),
            ("ki", KEYBDINPUT),
            ("padding", ctypes.c_ubyte * 8),
        ]

    inputs = (INPUT * 4)()
    # Ctrl down
    inputs[0].type = INPUT_KEYBOARD
    inputs[0].ki.wVk = VK_CONTROL
    # V down
    inputs[1].type = INPUT_KEYBOARD
    inputs[1].ki.wVk = VK_V
    # V up
    inputs[2].type = INPUT_KEYBOARD
    inputs[2].ki.wVk = VK_V
    inputs[2].ki.dwFlags = KEYEVENTF_KEYUP
    # Ctrl up
    inputs[3].type = INPUT_KEYBOARD
    inputs[3].ki.wVk = VK_CONTROL
    inputs[3].ki.dwFlags = KEYEVENTF_KEYUP

    user32.SendInput(4, ctypes.byref(inputs), ctypes.sizeof(INPUT))


def _fill_pyautogui(submit: bool) -> bool:
    """Activate window and send hotkeys.  Returns True on success."""
    sys = platform.system()

    if not activate_wukong_window():
        return False
    time.sleep(0.5)

    if sys == "Windows":
        # Use Win32 keybd_event — more reliable than pyautogui.hotkey
        try:
            import ctypes

            user32 = ctypes.windll.user32  # type: ignore[attr-defined]
            VK_CONTROL = 0x11
            VK_A = 0x41
            KEYEVENTF_KEYUP = 0x0002

            # Ctrl+A (select all)
            user32.keybd_event(VK_CONTROL, 0, 0, 0)
            user32.keybd_event(VK_A, 0, 0, 0)
            user32.keybd_event(VK_A, 0, KEYEVENTF_KEYUP, 0)
            user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
            time.sleep(0.1)

            # Ctrl+V (paste)
            _send_paste_win32()
            time.sleep(0.5)

            if submit:
                VK_RETURN = 0x0D
                user32.keybd_event(VK_RETURN, 0, 0, 0)
                user32.keybd_event(VK_RETURN, 0, KEYEVENTF_KEYUP, 0)
            return True
        except Exception as e:
            logger.warning("Win32 SendInput failed (%s), falling back to pyautogui", e)

    # Fallback: pyautogui (Linux or if SendInput failed)
    import pyautogui  # type: ignore[import-untyped]

    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.1)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.5)

    if submit:
        pyautogui.press("enter")
    return True


def fill_and_submit(code: str, submit: bool = False) -> None:
    """Fill an invite code into the active Wukong input field.

    Safeguards:
    - If the Wukong window is not available (e.g. not logged in), the
      invite code is still copied to the clipboard so the user can paste
      manually, and no keystrokes are sent to other windows.
    - If autofill fails for any reason, the invite code is re-copied to
      the clipboard so it is never lost.
    """
    is_windows = platform.system() == "Windows"

    # --- Pre-check: skip keystrokes if the window doesn't exist / isn't visible ---
    if is_windows and _find_wukong_window() is None:
        logger.info("Wukong window not found — skipping autofill")
        copy_to_clipboard(code)  # still copy so the user can paste manually
        return

    # --- Copy code and attempt autofill ---
    copy_to_clipboard(code)

    try:
        if platform.system() == "Darwin":
            _fill_macos(submit)
        else:
            if not _fill_pyautogui(submit):
                raise RuntimeError("autofill could not activate Wukong window")
    except Exception as e:
        logger.warning("autofill failed: %s — restoring invite code to clipboard", e)
        # Re-copy the invite code so it isn't lost
        try:
            copy_to_clipboard(code)
        except Exception:
            pass
