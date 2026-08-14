"""파일명 만들기 — 경로 탈출 방지 + 한글 보존.

파일명 규칙: {제목}_{품질}.{확장자}
"""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import quote

# Windows/macOS/Linux 어디서든 문제되는 문자
_FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
# 제어문자 계열과 이름 앞뒤 공백/점
_TRIM = re.compile(r"^[.\s]+|[.\s]+$")
# Windows 예약어
_RESERVED = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}

MAX_STEM_BYTES = 120  # 대부분의 파일시스템이 255바이트 제한


def sanitize_component(raw: str, *, fallback: str = "제목없음") -> str:
    """파일명 한 조각을 안전하게 만든다. 경로 구분자와 상위 이동(..)을 모두 제거한다."""
    text = unicodedata.normalize("NFC", raw or "")
    text = _FORBIDDEN.sub("_", text)
    text = re.sub(r"\s+", " ", text)
    # 앞뒤 점/공백을 먼저 털어낸 뒤에 상위 이동(..)을 없앤다. 순서가 바뀌면
    # "  ...파일" 이 "_.파일" 처럼 남는다.
    text = _TRIM.sub("", text)
    text = text.replace("..", "_")
    if text.lower() in _RESERVED:
        text = f"_{text}"
    if not text:
        return fallback

    # 바이트 기준으로 자른다 (한글은 UTF-8에서 3바이트)
    encoded = text.encode("utf-8")
    if len(encoded) > MAX_STEM_BYTES:
        text = encoded[:MAX_STEM_BYTES].decode("utf-8", errors="ignore").rstrip()
    return text or fallback


QUALITY_LABELS = {
    "44100-16": "44.1kHz16bit",
    "48000-24": "48kHz24bit",
}


def build_filename(title: str, quality: str, extension: str) -> str:
    """{제목}_{품질}.{확장자}"""
    stem = sanitize_component(title)
    quality_part = sanitize_component(QUALITY_LABELS.get(quality, quality), fallback="기본")
    ext = re.sub(r"[^a-z0-9]", "", (extension or "bin").lower()) or "bin"
    return f"{stem}_{quality_part}.{ext}"


def content_disposition(filename: str) -> str:
    """RFC 5987 — 한글 파일명이 깨지지 않게 filename* 를 함께 보낸다.

    ASCII 전용 클라이언트를 위한 filename= 폴백도 같이 넣는다.
    """
    ascii_fallback = filename.encode("ascii", errors="replace").decode("ascii")
    ascii_fallback = ascii_fallback.replace("?", "_").replace('"', "_").replace("\\", "_")
    if not ascii_fallback.strip("_. "):
        ascii_fallback = "download"
    encoded = quote(filename, safe="")
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{encoded}"
