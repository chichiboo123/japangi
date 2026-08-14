"""yt-dlp Python API 래퍼.

CLI 서브프로세스가 아니라 라이브러리를 직접 쓴다 — 메타데이터 접근이 훨씬 정확하다.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError, ExtractorError

from .config import settings

logger = logging.getLogger("japangi.ytdl")

# 조용히, 그리고 진행률은 우리가 직접 hook 으로 받는다.
BASE_OPTS: dict[str, Any] = {
    "quiet": True,
    "no_warnings": True,
    "noprogress": True,
    "no_color": True,
    "noplaylist": True,  # 재생목록 링크여도 영상 하나만
    "ignoreerrors": False,
    "retries": 5,
    "fragment_retries": 5,
    "extractor_retries": 3,
    "socket_timeout": 30,
    "geo_bypass": True,
    # 서버 IP 가 봇으로 찍히는 걸 조금이라도 줄인다.
    "extractor_args": {"youtube": {"player_client": ["default", "web_safari", "android_vr"]}},
}


def build_opts(**overrides: Any) -> dict[str, Any]:
    opts = dict(BASE_OPTS)
    if settings.cookies_enabled:
        opts["cookiefile"] = settings.cookies_file
    opts.update(overrides)
    return opts


def extract_info(url: str, **overrides: Any) -> dict[str, Any]:
    """download=False 로 메타데이터만 받아온다 (동기 — 스레드에서 호출할 것)."""
    opts = build_opts(**overrides)
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    if info is None:
        raise ExtractorError("unable to extract any media", expected=True)

    # 재생목록/채널 링크가 들어오면 첫 항목을 쓴다.
    if info.get("_type") in ("playlist", "multi_video"):
        entries = [e for e in (info.get("entries") or []) if e]
        if not entries:
            raise ExtractorError("no video formats found in playlist", expected=True)
        info = entries[0]

    return info


def download(
    url: str,
    *,
    format_selector: str,
    outtmpl: str,
    progress_hook: Callable[[dict[str, Any]], None] | None = None,
    postprocessor_hook: Callable[[dict[str, Any]], None] | None = None,
    merge_output_format: str | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    """실제 다운로드. 반환값은 다운로드된 항목의 info_dict."""
    opts = build_opts(
        format=format_selector,
        outtmpl={"default": outtmpl},
        progress_hooks=[progress_hook] if progress_hook else [],
        postprocessor_hooks=[postprocessor_hook] if postprocessor_hook else [],
        overwrites=True,
        # 컨테이너가 다른 트랙을 머지할 때 쓸 확장자
        **({"merge_output_format": merge_output_format} if merge_output_format else {}),
        **overrides,
    )
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if info is None:
            raise DownloadError("download produced no result")
        if info.get("_type") in ("playlist", "multi_video"):
            entries = [e for e in (info.get("entries") or []) if e]
            if not entries:
                raise DownloadError("download produced no result")
            info = entries[0]
        return ydl.sanitize_info(info)


def resolved_filepath(info: dict[str, Any]) -> str | None:
    """머지/후처리까지 끝난 최종 파일 경로."""
    downloads = info.get("requested_downloads") or []
    for item in downloads:
        path = item.get("filepath") or item.get("_filename")
        if path:
            return path
    return info.get("filepath") or info.get("_filename")
