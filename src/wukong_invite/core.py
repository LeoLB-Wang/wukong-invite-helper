from __future__ import annotations

from dataclasses import dataclass
import json
import re


_CALLBACK_RE = re.compile(r"^\s*[A-Za-z_]\w*\((.*)\)\s*;?\s*$", re.DOTALL)
_IMG_URL_RE = re.compile(
    r"https?://[^\s\"']+\.(?:png|jpg|jpeg|webp)(?:\?[^\s\"']*)?", re.IGNORECASE
)
_IMAGE_ASSET_ID_RE = re.compile(
    r"(\d+)-\d+-tps-\d+-\d+\.(?:png|jpg|jpeg|webp)(?:\?|$)", re.IGNORECASE
)
_INVITE_CODE_PATTERNS = [
    # CJK patterns — invite codes are known to be 5 Chinese characters.
    re.compile(r"当前邀请码\s*[:：]?\s*([\u4e00-\u9fff]{4,8})"),
    re.compile(r"邀请码\s*[:：]?\s*([\u4e00-\u9fff]{4,8})"),
    re.compile(r"当前邀请码[^\n]{0,3}\s*\n\s*([\u4e00-\u9fff]{4,8})"),
    re.compile(r"邀请码[^\n]{0,3}\s*\n\s*([\u4e00-\u9fff]{4,8})"),
    # ASCII patterns — only used as last resort.
    re.compile(r"当前邀请码\s*[:：]?\s*([A-Za-z0-9_-]+)"),
    re.compile(r"邀请码\s*[:：]?\s*([A-Za-z0-9_-]+)"),
]
_TOKEN_RE = re.compile(r"\b[A-Za-z0-9_-]{6,}\b")
_CJK_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{4,8}")
_FRAGMENTED_CJK_SPACES_RE = re.compile(r"(?<=[\u4e00-\u9fff])[ \t]+(?=[\u4e00-\u9fff])")
_READY_INVITE_CODE_RE = re.compile(r"^[\u4e00-\u9fff]{5}$")
_CJK_STOP_WORDS = {
    "限量",
    "已领完",
    "欢迎回来",
    "立即体验",
    "退出登录",
    "刷新验证",
    "客服咨询",
    "悟空官网获得",
    "悟空出世",
}


@dataclass(frozen=True)
class InviteAPIResult:
    """Normalized invite API payload."""

    status: str
    code: str | None
    raw_code: str | None
    next_release_at: str | None


def parse_invite_api_payload(payload: str) -> InviteAPIResult:
    """Parse the direct invite API JSON payload."""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError("Could not parse invite API payload as JSON") from exc

    if not isinstance(data, dict):
        raise ValueError("Invite API payload must be a JSON object")

    raw_code = data.get("code")
    if raw_code is not None and not isinstance(raw_code, str):
        raise ValueError("Invite API code field must be a string")

    next_release_at = data.get("nextReleaseAt")
    if next_release_at is not None and not isinstance(next_release_at, str):
        raise ValueError("Invite API nextReleaseAt field must be a string")

    if isinstance(raw_code, str) and _READY_INVITE_CODE_RE.fullmatch(raw_code):
        return InviteAPIResult(
            status="ready",
            code=raw_code,
            raw_code=raw_code,
            next_release_at=next_release_at,
        )

    return InviteAPIResult(
        status="waiting",
        code=None,
        raw_code=raw_code,
        next_release_at=next_release_at,
    )


def parse_js_payload(payload: str) -> str:
    """Extract the image URL from the JSONP-like response."""
    match = _CALLBACK_RE.match(payload)
    body = match.group(1) if match else payload
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        image_match = _IMG_URL_RE.search(payload)
        if not image_match:
            raise ValueError("Could not parse image URL from payload") from None
        return image_match.group(0)

    for key in ("img_url", "image", "url"):
        value = data.get(key)
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return value
    raise ValueError("Could not find image URL in payload")


def extract_image_asset_id(image_url: str) -> str:
    """Extract the numeric asset id from an invite image URL."""
    match = _IMAGE_ASSET_ID_RE.search(image_url)
    if not match:
        raise ValueError("Could not extract image asset id from image URL")
    return match.group(1)


def extract_invite_code(text: str) -> str:
    """Extract the value following '当前邀请码' from OCR text."""
    normalized = text.replace("\u3000", " ")
    normalized = _FRAGMENTED_CJK_SPACES_RE.sub("", normalized)

    # --- Priority 1: labelled pattern — prefer CJK over ASCII ---
    cjk_matches: list[str] = []
    ascii_matches: list[str] = []
    for pattern in _INVITE_CODE_PATTERNS:
        match = pattern.search(normalized)
        if match:
            val = match.group(1).strip()
            if any("\u4e00" <= ch <= "\u9fff" for ch in val):
                cjk_matches.append(val)
            else:
                ascii_matches.append(val)
    if cjk_matches:
        return cjk_matches[0]
    if ascii_matches:
        return ascii_matches[0]

    # --- Priority 2: single 5-char CJK token ---
    cjk_candidates: list[str] = []
    for token in _CJK_TOKEN_RE.findall(normalized):
        stripped = token.strip()
        if len(stripped) == 5 and stripped not in _CJK_STOP_WORDS:
            cjk_candidates.append(stripped)
    unique_cjk_candidates = list(dict.fromkeys(cjk_candidates))
    if len(unique_cjk_candidates) == 1:
        return unique_cjk_candidates[0]

    # --- Priority 3: mixed alpha-numeric token (≥6 chars) ---
    # Guard: only attempt this when the OCR text contains at least *some*
    # CJK characters, proving the engine captured real content rather than
    # garbage from a faint / unreadable image.
    has_cjk = any("\u4e00" <= c <= "\u9fff" for c in normalized)
    if has_cjk:
        candidates: list[str] = []
        for token in _TOKEN_RE.findall(normalized):
            has_letter = any(ch.isalpha() for ch in token)
            has_digit = any(ch.isdigit() for ch in token)
            if has_letter and has_digit:
                candidates.append(token.strip())
        unique_candidates = list(dict.fromkeys(candidates))
        if len(unique_candidates) == 1:
            return unique_candidates[0]

    raise ValueError("Could not find invite code in OCR text")
