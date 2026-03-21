from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image


class VisionOCR:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.binary_path = project_root / ".cache" / "vision_ocr"
        self.module_cache_path = project_root / ".cache" / "clang-module-cache"
        self.source_path = project_root / "tools" / "vision_ocr.m"

    def _compile(self, source_path: Path, binary_path: Path, frameworks: list[str]) -> Path:
        clang = shutil.which("clang")
        if not clang:
            raise RuntimeError("clang not found; cannot build native helper")

        binary_path.parent.mkdir(parents=True, exist_ok=True)
        self.module_cache_path.mkdir(parents=True, exist_ok=True)

        command = [clang, "-fmodules"]
        for framework in frameworks:
            command.extend(["-framework", framework])
        command.extend([str(source_path), "-o", str(binary_path)])
        env = os.environ.copy()
        env["CLANG_MODULE_CACHE_PATH"] = str(self.module_cache_path)
        subprocess.run(command, check=True, env=env)
        return binary_path

    def ensure_binary(self) -> Path:
        if self.binary_path.exists() and self.binary_path.stat().st_mtime >= self.source_path.stat().st_mtime:
            return self.binary_path
        return self._compile(self.source_path, self.binary_path, ["Foundation", "Vision", "AppKit"])

    def _recognize_vision(self, image_path: Path) -> str:
        binary = self.ensure_binary()
        result = subprocess.run(
            [str(binary), str(image_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout

    def _preprocess_alpha(self, image_path: Path, temp_dir: Path) -> list[Path]:
        """Composite RGBA onto black background to reveal semi-transparent white text."""
        img = Image.open(image_path)
        if img.mode != "RGBA":
            img = img.convert("RGBA")

        w, h = img.size
        candidates: list[Path] = []

        # candidate 1: full image composited on black, inverted → dark text on white
        black_bg = Image.new("RGBA", (w, h), (0, 0, 0, 255))
        composite = Image.alpha_composite(black_bg, img)
        gray = composite.convert("L")
        inverted = gray.point(lambda p: 255 - p)
        p1 = temp_dir / "alpha_full_inverted.png"
        inverted.save(str(p1))
        candidates.append(p1)

        # candidate 2: upper 35% crop, composited on black, inverted, 2x upscale
        upper_h = int(h * 0.35)
        upper_img = img.crop((0, 0, w, upper_h))
        upper_black = Image.new("RGBA", (w, upper_h), (0, 0, 0, 255))
        upper_comp = Image.alpha_composite(upper_black, upper_img)
        upper_inv = upper_comp.convert("L").point(lambda p: 255 - p)
        scaled = upper_inv.resize((w * 2, upper_h * 2), Image.LANCZOS)
        p2 = temp_dir / "alpha_upper_inverted_2x.png"
        scaled.save(str(p2))
        candidates.append(p2)

        return candidates

    def recognize_text(self, image_path: Path) -> str:
        runtime_dir = self.project_root / ".cache" / "ocr-runtime"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="wukong-preprocess-", dir=runtime_dir) as temp_dir:
            for candidate_path in self._preprocess_alpha(image_path, Path(temp_dir)):
                text = self._recognize_vision(candidate_path)
                if text.strip():
                    return text

        # Fallback: Vision OCR on original image
        return self._recognize_vision(image_path)
