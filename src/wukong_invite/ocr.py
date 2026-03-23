from __future__ import annotations

import abc
import os
import platform
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageEnhance

# Invite code is known to be exactly 5 CJK characters.
_CJK_5_RE = re.compile(r"[\u4e00-\u9fff]{5}")

_OCR_CJK_STOP_WORDS = {
    "限量邀请码",
    "当前邀请码",
    "欢迎回来吧",
    "立即体验吧",
    "退出登录吧",
    "悟空官网获得",
}

_GRAY_BACKGROUND = 160


def _has_cjk(text: str) -> bool:
    """Return True if *text* contains at least one CJK Unified Ideograph."""
    return any("\u4e00" <= c <= "\u9fff" for c in text)


def _count_cjk5_tokens(text: str) -> int:
    """Count distinct 5-char CJK tokens that are not stop words."""
    tokens = {t for t in _CJK_5_RE.findall(text) if t not in _OCR_CJK_STOP_WORDS}
    return len(tokens)


def _crop_box_for_mode(size: tuple[int, int], mode: str) -> tuple[int, int, int, int]:
    """Return a crop box aligned with the native macOS helper heuristics."""
    width, height = size
    left_ratio = 0.18
    top_ratio = 0.02
    crop_width_ratio = 0.54
    crop_height_ratio = 0.20

    if "tight" in mode:
        left_ratio = 0.20
        crop_width_ratio = 0.46
        crop_height_ratio = 0.18
    elif "wide" in mode:
        left_ratio = 0.12
        top_ratio = 0.01
        crop_width_ratio = 0.62
        crop_height_ratio = 0.24

    left = int(round(width * left_ratio))
    top = int(round(height * top_ratio))
    right = left + int(round(width * crop_width_ratio))
    bottom = top + int(round(height * crop_height_ratio))
    return (left, top, min(right, width), min(bottom, height))


def _mode_parameters(mode: str) -> tuple[float, float, int | None]:
    """Return contrast, brightness and threshold for a preprocessing mode."""
    contrast = 2.6
    brightness = 18.0
    threshold: int | None = None

    if mode == "upper_soft":
        contrast = 1.8
        brightness = 26.0
    elif mode == "upper_contrast":
        contrast = 3.4
        brightness = 8.0
    elif mode.endswith("240"):
        threshold = 240
    elif mode.endswith("245"):
        threshold = 245
    elif mode.endswith("250"):
        threshold = 250

    return contrast, brightness, threshold


def _compose_on_gray_background(image: Image.Image, gray_value: int = _GRAY_BACKGROUND) -> Image.Image:
    """Composite an RGBA image onto a solid gray background."""
    rgba = image.convert("RGBA")
    background = Image.new("RGBA", rgba.size, (gray_value, gray_value, gray_value, 255))
    return Image.alpha_composite(background, rgba)


def _apply_mac_style_mode(image: Image.Image, mode: str) -> tuple[Image.Image, int]:
    """Apply the macOS helper's grayscale enhancement pipeline to an image."""
    contrast, brightness, threshold = _mode_parameters(mode)
    gray = _compose_on_gray_background(image).convert("L")

    if threshold is not None:
        processed = gray.point(lambda p: 255 if p >= threshold else 0)
        return processed, 6

    processed = gray.point(lambda p: max(0, min(255, int(round(((p - 128) * contrast) + 128 + brightness)))))
    return processed, 4


def _preprocess_alpha(image_path: Path, temp_dir: Path) -> list[Path]:
    """Composite RGBA onto black background to reveal semi-transparent white text.

    Returns multiple candidate images; more aggressively enhanced variants are
    appended for Tesseract to cope with faint / low-contrast text on Windows.
    """
    img = Image.open(image_path)
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    w, h = img.size
    candidates: list[Path] = []

    # --- base composites ------------------------------------------------
    black_bg = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    composite = Image.alpha_composite(black_bg, img)
    gray = composite.convert("L")
    inverted = gray.point(lambda p: 255 - p)

    upper_h = int(h * 0.35)
    upper_img = img.crop((0, 0, w, upper_h))
    upper_black = Image.new("RGBA", (w, upper_h), (0, 0, 0, 255))
    upper_comp = Image.alpha_composite(upper_black, upper_img)
    upper_inv = upper_comp.convert("L").point(lambda p: 255 - p)

    # candidate 1: full image composited on black, inverted → dark text on white
    p1 = temp_dir / "alpha_full_inverted.png"
    inverted.save(str(p1))
    candidates.append(p1)

    # candidate 2: upper 35% crop, composited on black, inverted, 2x upscale
    scaled = upper_inv.resize((w * 2, upper_h * 2), Image.LANCZOS)
    p2 = temp_dir / "alpha_upper_inverted_2x.png"
    scaled.save(str(p2))
    candidates.append(p2)

    # candidate 3: full image – high contrast + binarise (helps faint text)
    enhanced = ImageEnhance.Contrast(inverted).enhance(3.0)
    binarized = enhanced.point(lambda p: 255 if p > 100 else 0)
    p3 = temp_dir / "alpha_full_contrast_bin.png"
    binarized.save(str(p3))
    candidates.append(p3)

    # candidate 4: upper crop – high contrast + binarise + 3× upscale
    upper_enh = ImageEnhance.Contrast(upper_inv).enhance(3.0)
    upper_bin = upper_enh.point(lambda p: 255 if p > 100 else 0)
    upper_bin_scaled = upper_bin.resize((w * 3, upper_h * 3), Image.LANCZOS)
    p4 = temp_dir / "alpha_upper_contrast_bin_3x.png"
    upper_bin_scaled.save(str(p4))
    candidates.append(p4)

    upper_source = img.crop(_crop_box_for_mode((w, h), "upper"))
    gray_modes = (
        ("upper", "upper_gray_default_4x.png"),
        ("upper_soft", "upper_gray_soft_4x.png"),
        ("upper_contrast", "upper_gray_contrast_4x.png"),
        ("upper_240", "upper_gray_threshold_240_6x.png"),
        ("upper_245", "upper_gray_threshold_245_6x.png"),
        ("upper_250", "upper_gray_threshold_250_6x.png"),
    )
    for mode, file_name in gray_modes:
        processed, scale = _apply_mac_style_mode(upper_source, mode)
        scaled_candidate = processed.resize(
            (processed.width * scale, processed.height * scale),
            Image.Resampling.LANCZOS,
        )
        candidate_path = temp_dir / file_name
        scaled_candidate.save(str(candidate_path))
        candidates.append(candidate_path)

    return candidates


class OCREngine(abc.ABC):
    """Abstract base for OCR engines."""

    @abc.abstractmethod
    def _recognize(self, image_path: Path) -> str:
        """Run OCR on a single image and return raw text."""

    def recognize_text(self, image_path: Path, project_root: Path) -> str:
        """Preprocess, try every candidate, and return the best result.

        Scoring (highest wins):
          3 — text contains exactly one 5-char CJK token (perfect invite code)
          2 — text contains CJK characters (partially useful)
          1 — text is non-empty but no CJK
          0 — empty

        All candidates are evaluated; we short-circuit only on score 3.
        """
        runtime_dir = project_root / ".cache" / "ocr-runtime"
        runtime_dir.mkdir(parents=True, exist_ok=True)

        best_text: str = ""
        best_score: int = 0

        def _score(text: str) -> int:
            if not text.strip():
                return 0
            n = _count_cjk5_tokens(text)
            if n == 1:
                return 3  # perfect — exactly one invite-code candidate
            if _has_cjk(text):
                return 2  # has CJK but ambiguous
            return 1  # non-empty, no CJK (likely garbage)

        with tempfile.TemporaryDirectory(
            prefix="wukong-preprocess-", dir=runtime_dir
        ) as temp_dir:
            for candidate_path in _preprocess_alpha(image_path, Path(temp_dir)):
                text = self._recognize(candidate_path)
                s = _score(text)
                if s > best_score:
                    best_score = s
                    best_text = text
                if best_score == 3:
                    return best_text  # can't do better

        # Fallback: OCR on original image
        text = self._recognize(image_path)
        s = _score(text)
        if s > best_score:
            best_text = text
        return best_text


class VisionOCR(OCREngine):
    """macOS Vision Framework OCR (Objective-C native binary)."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.binary_path = project_root / ".cache" / "vision_ocr"
        self.module_cache_path = project_root / ".cache" / "clang-module-cache"
        self.source_path = project_root / "tools" / "vision_ocr.m"

    def _compile(
        self, source_path: Path, binary_path: Path, frameworks: list[str]
    ) -> Path:
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
        if (
            self.binary_path.exists()
            and self.binary_path.stat().st_mtime >= self.source_path.stat().st_mtime
        ):
            return self.binary_path
        return self._compile(
            self.source_path, self.binary_path, ["Foundation", "Vision", "AppKit"]
        )

    def _recognize(self, image_path: Path) -> str:
        binary = self.ensure_binary()
        result = subprocess.run(
            [str(binary), str(image_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout

    def recognize_text(self, image_path: Path, project_root: Path | None = None) -> str:
        root = project_root or self.project_root
        return super().recognize_text(image_path, root)


class RapidOCREngine(OCREngine):
    """RapidOCR engine (cross-platform, based on ONNXRuntime).

    Uses PaddleOCR models converted to ONNX format for efficient inference.
    Excellent Chinese text recognition without external dependencies.
    """

    def __init__(self) -> None:
        self._engine = None

    @property
    def engine(self):
        """Lazy initialization of RapidOCR engine."""
        if self._engine is None:
            from rapidocr import RapidOCR

            self._engine = RapidOCR()
        return self._engine

    def _recognize(self, image_path: Path) -> str:
        result = self.engine(str(image_path))
        if result.txts:
            return "\n".join(result.txts)
        return ""


class TesseractOCR(OCREngine):
    """Tesseract-based OCR engine (cross-platform, requires pytesseract + Tesseract binary).

    Defaults to *chi_sim* only (no eng) and ``--psm 7`` (single text line)
    because the invite code is known to be exactly 5 CJK characters.
    """

    def __init__(
        self, lang: str = "chi_sim", psm: int = 7, project_root: Path | None = None
    ) -> None:
        self.lang = lang
        self.config = f"--psm {psm} --oem 3"
        self._setup_tesseract_cmd()
        self._setup_tessdata_prefix(project_root)

    def _setup_tesseract_cmd(self) -> None:
        """Auto-detect tesseract executable path on Windows."""
        import pytesseract

        # Check if tesseract is already in PATH
        if shutil.which("tesseract"):
            return

        # Windows standard installation paths
        if platform.system() == "Windows":
            candidates = [
                Path(os.environ.get("ProgramFiles", "C:\\Program Files"))
                / "Tesseract-OCR"
                / "tesseract.exe",
                Path(os.environ.get("LocalAppData", ""))
                / "Programs"
                / "Tesseract-OCR"
                / "tesseract.exe",
            ]
            for candidate in candidates:
                if candidate.exists():
                    pytesseract.pytesseract.tesseract_cmd = str(candidate)
                    return

    def _setup_tessdata_prefix(self, project_root: Path | None) -> None:
        """Setup TESSDATA_PREFIX for Windows."""
        if platform.system() != "Windows":
            return

        # If environment variable is already set and directory exists, skip
        tessdata_prefix = os.environ.get("TESSDATA_PREFIX")
        if tessdata_prefix and Path(tessdata_prefix).exists():
            return

        # Use user local directory
        local_tessdata = (
            Path(os.environ.get("LOCALAPPDATA", ""))
            / "wukong-invite-helper"
            / "tessdata"
        )
        if local_tessdata.exists():
            os.environ["TESSDATA_PREFIX"] = str(local_tessdata)

    def _recognize(self, image_path: Path) -> str:
        import pytesseract

        img = Image.open(image_path)
        return pytesseract.image_to_string(img, lang=self.lang, config=self.config)


def create_ocr(project_root: Path) -> OCREngine:
    """Factory: return the best OCR engine for the current platform."""
    if platform.system() == "Darwin":
        return VisionOCR(project_root)
    # Try RapidOCR first, fallback to Tesseract if not available
    try:
        import rapidocr

        return RapidOCREngine()
    except ImportError:
        return TesseractOCR(project_root=project_root)
