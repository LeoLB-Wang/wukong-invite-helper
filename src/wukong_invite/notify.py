from __future__ import annotations

import platform
import shutil
import subprocess


def copy_to_clipboard(text: str) -> None:
    system = platform.system()
    if system == "Darwin":
        pbcopy = shutil.which("pbcopy")
        if not pbcopy:
            raise RuntimeError("pbcopy not found")
        subprocess.run([pbcopy], input=text, text=True, check=True)
    elif system == "Windows":
        subprocess.run(["clip.exe"], input=text, text=True, check=True)
    else:
        # Linux: try xclip, then xsel
        xclip = shutil.which("xclip")
        if xclip:
            subprocess.run([xclip, "-selection", "clipboard"], input=text, text=True, check=True)
            return
        xsel = shutil.which("xsel")
        if xsel:
            subprocess.run([xsel, "--clipboard", "--input"], input=text, text=True, check=True)
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
