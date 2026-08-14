"""실제 yt-dlp extract_info 출력 형태를 본뜬 테스트 픽스처."""
from __future__ import annotations

from typing import Any


def _video(height: int, vcodec: str, ext: str, tbr: float, filesize: int | None = None, **extra) -> dict[str, Any]:
    fmt = {
        "format_id": f"{height}-{vcodec}",
        "ext": ext,
        "height": height,
        "width": int(height * 16 / 9),
        "vcodec": vcodec,
        "acodec": "none",
        "tbr": tbr,
        "fps": 30,
        "protocol": "https",
    }
    if filesize is not None:
        fmt["filesize"] = filesize
    fmt.update(extra)
    return fmt


def _audio(abr: float, acodec: str, ext: str, filesize: int | None = None, **extra) -> dict[str, Any]:
    fmt = {
        "format_id": f"audio-{acodec}-{int(abr)}",
        "ext": ext,
        "vcodec": "none",
        "acodec": acodec,
        "abr": abr,
        "tbr": abr,
        "audio_channels": 2,
        "asr": 48000,
        "protocol": "https",
    }
    if filesize is not None:
        fmt["filesize"] = filesize
    fmt.update(extra)
    return fmt


DURATION = 213  # 3분 33초


def youtube_full() -> dict[str, Any]:
    """흔한 유튜브 영상: 4K 는 VP9/AV1 만, H.264 는 1080p 까지."""
    return {
        "id": "dQw4w9WgXcQ",
        "title": "테스트 영상 — 자판기 점검용",
        "uploader": "치수쌤",
        "duration": DURATION,
        "thumbnail": "https://i.ytimg.com/vi/x/maxresdefault.jpg",
        "webpage_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "formats": [
            _audio(49.0, "opus", "webm", filesize=1_300_000),
            _audio(129.0, "mp4a.40.2", "m4a", filesize=3_430_000),
            _audio(160.0, "opus", "webm", filesize=4_260_000),
            _video(360, "avc1.4d401e", "mp4", 400.0, filesize=10_650_000),
            _video(360, "vp09.00.21.08", "webm", 250.0, filesize=6_650_000),
            _video(720, "avc1.64001f", "mp4", 1200.0, filesize=31_950_000),
            _video(720, "vp09.00.31.08", "webm", 800.0, filesize=21_300_000),
            _video(1080, "avc1.640028", "mp4", 2800.0, filesize=74_550_000),
            _video(1080, "vp09.00.40.08", "webm", 1900.0, filesize=50_590_000),
            # 4K 는 VP9/AV1 만 — H.264 없음 (유튜브의 실제 동작)
            _video(2160, "vp09.00.50.08", "webm", 12000.0, filesize=319_500_000),
            _video(2160, "av01.0.12M.08", "mp4", 9000.0, filesize=239_600_000),
            # 스토리보드 — 걸러져야 한다
            {"format_id": "sb0", "ext": "mhtml", "protocol": "mhtml", "vcodec": "none", "acodec": "none"},
        ],
    }


def youtube_low() -> dict[str, Any]:
    """최대 480p 짜리 오래된 영상 — 720p 이상은 전부 SOLD OUT 이어야 한다."""
    return {
        "id": "old",
        "title": "옛날 영상",
        "uploader": "누군가",
        "duration": 120,
        "formats": [
            _audio(128.0, "mp4a.40.2", "m4a"),
            _video(240, "avc1.42001e", "mp4", 300.0),
            _video(360, "avc1.42001e", "mp4", 500.0),
            _video(480, "avc1.4d401e", "mp4", 900.0),
        ],
    }


def instagram_reel() -> dict[str, Any]:
    """인스타 릴스: muxed H.264 하나뿐. filesize 없음 → tbr 추정 경로를 탄다."""
    return {
        "id": "reel",
        "title": "릴스",
        "uploader": "insta_user",
        "duration": 30,
        "formats": [
            {
                "format_id": "dash-1",
                "ext": "mp4",
                "height": 1080,
                "width": 1080,
                "vcodec": "avc1.4d401f",
                "acodec": "mp4a.40.2",
                "tbr": 2500.0,
                "protocol": "https",
            }
        ],
    }


def audio_only_source() -> dict[str, Any]:
    return {
        "id": "podcast",
        "title": "팟캐스트",
        "uploader": "방송국",
        "duration": 600,
        "formats": [_audio(128.0, "mp4a.40.2", "m4a", filesize=9_600_000)],
    }


def no_filesize_video() -> dict[str, Any]:
    """filesize / filesize_approx 가 전혀 없어 tbr 로만 추정해야 하는 경우."""
    return {
        "id": "nosize",
        "title": "용량 정보 없음",
        "duration": 100,
        "formats": [
            _audio(128.0, "opus", "webm"),
            _video(1080, "vp09.00.40.08", "webm", 2000.0),
        ],
    }
