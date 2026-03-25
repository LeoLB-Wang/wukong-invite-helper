from __future__ import annotations

import platform
import shutil
import subprocess


def _copy_to_clipboard_win32(text: str) -> None:
    """Copy text to Windows clipboard via Win32 API (handles Unicode properly)."""
    import ctypes

    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

    # Set argtypes so ctypes passes correct pointer sizes on 64-bit systems
    user32.OpenClipboard.argtypes = [ctypes.c_void_p]
    user32.OpenClipboard.restype = ctypes.c_bool
    user32.EmptyClipboard.restype = ctypes.c_bool
    user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    user32.SetClipboardData.restype = ctypes.c_void_p
    user32.CloseClipboard.restype = ctypes.c_bool
    kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.restype = ctypes.c_bool

    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002

    # Retry OpenClipboard — it can fail when another process holds it
    for _ in range(5):
        if user32.OpenClipboard(None):
            break
        import time as _time

        _time.sleep(0.05)
    else:
        raise RuntimeError("Failed to open clipboard after retries")

    try:
        user32.EmptyClipboard()
        data = text.encode("utf-16-le")
        size = len(data) + 2  # +2 for null terminator
        h_global = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
        if not h_global:
            raise RuntimeError("Failed to allocate global memory")
        p_mem = kernel32.GlobalLock(h_global)
        if not p_mem:
            raise RuntimeError("Failed to lock global memory")
        ctypes.memmove(p_mem, data, len(data))
        ctypes.memmove(p_mem + len(data), b"\x00\x00", 2)
        kernel32.GlobalUnlock(h_global)
        result = user32.SetClipboardData(CF_UNICODETEXT, h_global)
        if not result:
            raise RuntimeError("SetClipboardData failed")
    finally:
        user32.CloseClipboard()


def copy_to_clipboard(text: str) -> None:
    system = platform.system()
    if system == "Darwin":
        pbcopy = shutil.which("pbcopy")
        if not pbcopy:
            raise RuntimeError("pbcopy not found")
        subprocess.run([pbcopy], input=text, text=True, check=True)
    elif system == "Windows":
        _copy_to_clipboard_win32(text)
    else:
        # Linux: try xclip, then xsel
        xclip = shutil.which("xclip")
        if xclip:
            subprocess.run(
                [xclip, "-selection", "clipboard"], input=text, text=True, check=True
            )
            return
        xsel = shutil.which("xsel")
        if xsel:
            subprocess.run(
                [xsel, "--clipboard", "--input"], input=text, text=True, check=True
            )
            return
        raise RuntimeError("No clipboard tool found (xclip or xsel)")


def play_alert(sound_name: str = "Glass") -> None:
    system = platform.system()
    if system == "Darwin":
        afplay = shutil.which("afplay")
        if not afplay:
            raise RuntimeError("afplay not found")
        subprocess.run(
            [afplay, f"/System/Library/Sounds/{sound_name}.aiff"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    elif system == "Windows":
        import winsound

        winsound.MessageBeep(winsound.MB_ICONASTERISK)
    else:
        # Best-effort bell on Linux
        print("\a", end="", flush=True)
