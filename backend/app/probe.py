"""상품 확인 — 링크 하나로 제목/썸네일/재생시간/포맷별 예상 용량을 만들어낸다."""
from __future__ import annotations

from typing import Any

from . import formats, ytdl
from .config import settings
from .errors import FriendlyError
from .urls import ParsedTarget


def _thumbnail(info: dict[str, Any]) -> str | None:
    thumb = info.get("thumbnail")
    if thumb:
        return thumb
    candidates = [t for t in (info.get("thumbnails") or []) if t.get("url")]
    if not candidates:
        return None
    best = max(candidates, key=lambda t: (t.get("preference") or 0, t.get("width") or 0))
    return best.get("url")


def probe(target: ParsedTarget) -> dict[str, Any]:
    info = ytdl.extract_info(target.url)

    if info.get("is_live"):
        raise FriendlyError(
            "진행 중인 라이브는 받을 수 없어요. 방송이 끝난 뒤에 다시 시도해 주세요",
            code="live",
        )

    duration = info.get("duration")
    if duration and duration > settings.max_duration_seconds:
        limit_hours = settings.max_duration_seconds / 3600
        raise FriendlyError(
            f"{limit_hours:g}시간이 넘는 콘텐츠는 자판기가 받을 수 없어요",
            code="too_long",
        )

    index = formats.index_formats(info)
    audio_options = formats.build_audio_options(index)
    video_options = formats.build_video_options(index)

    if not any(o.available for o in audio_options + video_options):
        raise FriendlyError(
            "이 링크에서는 받을 수 있는 영상이나 음원을 찾지 못했어요",
            code="no_media",
        )

    return {
        "title": info.get("title") or "제목 없음",
        "uploader": info.get("uploader") or info.get("channel") or info.get("uploader_id") or "",
        "duration": int(duration) if duration else None,
        "thumbnail": _thumbnail(info),
        "source": target.source,
        "webpageUrl": info.get("webpage_url") or target.url,
        "options": {
            "audio": [o.to_json() for o in audio_options],
            "video": [o.to_json() for o in video_options],
        },
    }
