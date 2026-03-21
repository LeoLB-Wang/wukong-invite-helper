from __future__ import annotations

import shutil
import subprocess


def copy_to_clipboard(text: str) -> None:
    pbcopy = shutil.which("pbcopy")
    if not pbcopy:
        raise RuntimeError("pbcopy not found")
    subprocess.run([pbcopy], input=text, text=True, check=True)


def play_alert(sound_name: str = "Glass") -> None:
    afplay = shutil.which("afplay")
    if not afplay:
        raise RuntimeError("afplay not found")
    subprocess.run(
        [afplay, f"/System/Library/Sounds/{sound_name}.aiff"],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
