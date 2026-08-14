"""상품 진열대 — 포맷 카탈로그, 재고(available) 판정, 코덱 협상.

핵심 원칙
  1. 원본에 없는 화질은 미리 SOLD OUT 으로 내린다. 고르게 해놓고 나중에 실패하는 게 최악.
  2. 재인코딩보다 항상 리먹스를 택한다 (화질 손실 0, 수십 배 빠름).
  3. 유튜브는 1080p 초과 해상도에 H.264 를 거의 주지 않는다 → MP4 4K 는 대부분 VP9/AV1 리먹스.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from . import sizes

# ── 카탈로그 정의 ────────────────────────────────────────────────────────────

MP3_BITRATES: tuple[int, ...] = (128, 192, 256, 320)

# quality 키 → (샘플레이트, 비트깊이)
WAV_PROFILES: dict[str, tuple[int, int]] = {
    "44100-16": (44100, 16),
    "48000-24": (48000, 24),
}

# quality 키 → 세로 픽셀
VIDEO_HEIGHTS: dict[str, int] = {
    "360p": 360,
    "720p": 720,
    "1080p": 1080,
    "2160p": 2160,
}

VIDEO_CONTAINERS: tuple[str, ...] = ("mp4", "webm")

# 컨테이너별로 "재인코딩 없이" 담을 수 있는 코덱
MP4_VIDEO_CODECS = ("avc1", "h264", "hev1", "hvc1", "h265", "av01")
# 용량 추정에 쓰는 선호 코덱은 반드시 format selector 의 1순위와 같아야 한다.
# (mp4 셀렉터가 bestaudio[ext=m4a] 를 먼저 고르는데 opus 로 추정하면 용량이 어긋난다)
MP4_AUDIO_CODECS = ("mp4a", "aac")
WEBM_VIDEO_CODECS = ("vp9", "vp09", "vp8", "av01")
WEBM_AUDIO_CODECS = ("opus", "vorbis")

# 요청 화질 대비 이 비율 미만이면 "그 화질은 없는 것"으로 본다.
HEIGHT_TOLERANCE = 0.9


@dataclass
class Option:
    kind: str  # "audio" | "video"
    format: str  # mp3 | wav | mp4 | webm
    quality: str
    label: str
    estimated_bytes: int | None
    available: bool
    size_source: str = sizes.SizeSource.UNKNOWN
    needs_reencode: bool = False
    warning: str | None = None
    note: str | None = None
    badge: str | None = None  # "대용량" 같은 진열대 라벨
    source_height: int | None = None

    def to_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "format": self.format,
            "quality": self.quality,
            "label": self.label,
            "estimatedBytes": self.estimated_bytes,
            "available": self.available,
            "sizeSource": self.size_source,
        }
        if self.kind == "video":
            payload["needsReencode"] = self.needs_reencode
            if self.source_height is not None:
                payload["sourceHeight"] = self.source_height
        for key, value in (("warning", self.warning), ("note", self.note), ("badge", self.badge)):
            if value:
                payload[key] = value
        return payload


# ── 포맷 목록 훑기 ───────────────────────────────────────────────────────────


def _codec_of(fmt: Mapping[str, Any], key: str) -> str:
    value = fmt.get(key) or ""
    if value in ("none", None):
        return ""
    return str(value).lower()


def _codec_matches(codec: str, prefixes: Sequence[str]) -> bool:
    return any(codec.startswith(p) for p in prefixes)


def is_video_stream(fmt: Mapping[str, Any]) -> bool:
    return bool(_codec_of(fmt, "vcodec")) and bool(fmt.get("height"))


def is_audio_stream(fmt: Mapping[str, Any]) -> bool:
    return bool(_codec_of(fmt, "acodec"))


def video_only(fmt: Mapping[str, Any]) -> bool:
    return is_video_stream(fmt) and not is_audio_stream(fmt)


def audio_only(fmt: Mapping[str, Any]) -> bool:
    return is_audio_stream(fmt) and not _codec_of(fmt, "vcodec")


@dataclass
class FormatIndex:
    """extract_info 결과의 formats 배열을 한 번만 훑어서 정리해둔 것."""

    videos: list[dict[str, Any]] = field(default_factory=list)  # 영상 트랙 (muxed 포함)
    audios: list[dict[str, Any]] = field(default_factory=list)  # 음성 전용 트랙
    muxed: list[dict[str, Any]] = field(default_factory=list)  # 영상+음성 한 덩어리
    duration: float | None = None

    @property
    def max_height(self) -> int:
        return max((int(f.get("height") or 0) for f in self.videos), default=0)

    @property
    def has_audio(self) -> bool:
        return bool(self.audios or self.muxed)

    def best_audio(self, prefer: Sequence[str] | None = None) -> dict[str, Any] | None:
        """비트레이트가 가장 높은 음성 트랙. prefer 가 주어지면 해당 코덱을 우선한다."""
        pool = self.audios or self.muxed
        if not pool:
            return None
        if prefer:
            preferred = [f for f in pool if _codec_matches(_codec_of(f, "acodec"), prefer)]
            if preferred:
                pool = preferred
        return max(pool, key=lambda f: float(f.get("abr") or f.get("tbr") or 0))

    def best_video_at(
        self,
        height: int,
        codecs: Sequence[str] | None = None,
    ) -> dict[str, Any] | None:
        """height 이하 중 가장 좋은 영상 트랙. codecs 가 주어지면 그 코덱만 본다."""
        pool = [f for f in self.videos if int(f.get("height") or 0) <= height]
        if codecs:
            pool = [f for f in pool if _codec_matches(_codec_of(f, "vcodec"), codecs)]
        if not pool:
            return None
        return max(
            pool,
            key=lambda f: (int(f.get("height") or 0), float(f.get("tbr") or f.get("vbr") or 0)),
        )


def index_formats(info: Mapping[str, Any]) -> FormatIndex:
    index = FormatIndex(duration=info.get("duration"))
    raw: Iterable[Mapping[str, Any]] = info.get("formats") or []
    for item in raw:
        fmt = dict(item)
        # 스토리보드/이미지 포맷은 제외
        if fmt.get("ext") in ("mhtml", "jpg", "png", "webp"):
            continue
        if fmt.get("protocol") in ("mhtml",):
            continue
        if video_only(fmt):
            index.videos.append(fmt)
        elif audio_only(fmt):
            index.audios.append(fmt)
        elif is_video_stream(fmt) and is_audio_stream(fmt):
            index.muxed.append(fmt)
            index.videos.append(fmt)

    # 인스타그램처럼 formats 배열 없이 단일 포맷만 오는 경우
    if not index.videos and not index.audios and info.get("url"):
        single = dict(info)
        if is_video_stream(single):
            index.videos.append(single)
            index.muxed.append(single)
        elif is_audio_stream(single):
            index.audios.append(single)
    return index


# ── 음원 진열대 ──────────────────────────────────────────────────────────────


def build_audio_options(index: FormatIndex) -> list[Option]:
    duration = index.duration
    source_audio = index.best_audio()
    has_audio = source_audio is not None
    # 원본 비트레이트보다 높은 MP3 를 골라도 음질은 좋아지지 않는다 (안내만, 막지는 않음)
    source_abr = float(source_audio.get("abr") or source_audio.get("tbr") or 0) if source_audio else 0.0
    channels = int(source_audio.get("audio_channels") or 2) if source_audio else 2
    channels = max(1, min(channels, 2))  # WAV 는 스테레오 기준으로 계산

    options: list[Option] = []
    for kbps in MP3_BITRATES:
        note = None
        if has_audio and source_abr and kbps > source_abr * 1.15:
            note = f"원본 음질이 약 {int(source_abr)}kbps라 더 좋아지지는 않아요"
        options.append(
            Option(
                kind="audio",
                format="mp3",
                quality=str(kbps),
                label=f"MP3 {kbps}kbps",
                estimated_bytes=sizes.mp3_bytes(kbps, duration) if has_audio else None,
                available=has_audio,
                size_source=sizes.SizeSource.FORMULA,
                note=note,
            )
        )

    for quality, (rate, depth) in WAV_PROFILES.items():
        estimated = sizes.wav_bytes(rate, depth, duration, channels) if has_audio else None
        label = f"WAV {rate // 1000 if rate % 1000 == 0 else rate / 1000:g}kHz {depth}bit"
        options.append(
            Option(
                kind="audio",
                format="wav",
                quality=quality,
                label=label,
                estimated_bytes=estimated,
                available=has_audio,
                size_source=sizes.SizeSource.FORMULA,
                badge="대용량",
                note="무압축이라 용량이 큽니다",
            )
        )
    return options


# ── 영상 진열대 + 코덱 협상 ─────────────────────────────────────────────────


def negotiate_video(
    index: FormatIndex,
    container: str,
    height: int,
) -> Option:
    """컨테이너 × 화질 하나에 대해 재고와 리먹스/재인코딩 여부를 판정한다."""
    quality = next(q for q, h in VIDEO_HEIGHTS.items() if h == height)
    label = f"{container.upper()} {quality}"

    # 1) 그 화질 자체가 원본에 있는가?
    best_any = index.best_video_at(height)
    if best_any is None:
        return Option(
            kind="video",
            format=container,
            quality=quality,
            label=label,
            estimated_bytes=None,
            available=False,
            note="원본에 영상 트랙이 없어요",
        )

    source_height = int(best_any.get("height") or 0)
    if source_height < height * HEIGHT_TOLERANCE:
        return Option(
            kind="video",
            format=container,
            quality=quality,
            label=label,
            estimated_bytes=None,
            available=False,
            source_height=source_height,
            note=f"원본 최대 화질이 {source_height}p 예요",
        )

    # 2) 이 컨테이너에 재인코딩 없이 담을 수 있는 코덱이 있는가?
    if container == "mp4":
        native_codecs, audio_codecs = MP4_VIDEO_CODECS, MP4_AUDIO_CODECS
        # H.264 가 있으면 호환성이 가장 좋다.
        preferred = index.best_video_at(height, ("avc1", "h264"))
    else:
        native_codecs, audio_codecs = WEBM_VIDEO_CODECS, WEBM_AUDIO_CODECS
        preferred = index.best_video_at(height, ("vp9", "vp09"))

    chosen = preferred
    needs_reencode = False
    warning: str | None = None

    if chosen is None or int(chosen.get("height") or 0) < height * HEIGHT_TOLERANCE:
        # 선호 코덱이 그 화질에 없다 → 컨테이너가 담을 수 있는 다른 코덱을 찾는다.
        fallback = index.best_video_at(height, native_codecs)
        if fallback is not None and int(fallback.get("height") or 0) >= height * HEIGHT_TOLERANCE:
            chosen = fallback
            if container == "mp4":
                codec_name = "AV1" if _codec_of(fallback, "vcodec").startswith("av01") else "HEVC"
                warning = (
                    f"원본에 H.264 {quality}가 없어 {codec_name} 스트림을 MP4로 리먹스해요. "
                    "빠르지만 오래된 플레이어에서는 안 열릴 수 있어요. "
                    "재인코딩을 켜면 H.264로 변환합니다 (수 분 소요)."
                )
            needs_reencode = False
        else:
            # 컨테이너 네이티브 코덱이 아예 없다 → 재인코딩 필요
            chosen = best_any
            needs_reencode = True
            if container == "mp4":
                warning = f"원본에 MP4용 코덱 {quality}가 없어 재인코딩이 필요해요 (수 분 소요)"
            else:
                warning = f"원본이 H.264라 WebM으로 만들려면 재인코딩이 필요해요 (수 분 소요)"

    # 3) 용량 = 영상 + 음성
    audio_fmt = None
    if not is_audio_stream(chosen):
        audio_fmt = index.best_audio(audio_codecs)
    estimated, size_source = sizes.combined_bytes(chosen, audio_fmt, index.duration)

    chosen_height = int(chosen.get("height") or 0)
    note = None
    if chosen_height and chosen_height != height:
        note = f"원본 {chosen_height}p로 받아요"

    return Option(
        kind="video",
        format=container,
        quality=quality,
        label=label,
        estimated_bytes=estimated,
        available=True,
        size_source=size_source,
        needs_reencode=needs_reencode,
        warning=warning,
        note=note,
        source_height=chosen_height or None,
        badge="4K" if height >= 2160 else None,
    )


def build_video_options(index: FormatIndex) -> list[Option]:
    if not index.videos:
        return []
    options: list[Option] = []
    for container in VIDEO_CONTAINERS:
        for quality, height in VIDEO_HEIGHTS.items():
            options.append(negotiate_video(index, container, height))
    return options


# ── yt-dlp format selector 문자열 ───────────────────────────────────────────


def video_format_selector(container: str, height: int) -> str:
    """다운로드 시 넘길 format selector.

    앞에서부터 시도하고 실패하면 다음으로 넘어간다.
    (선호 코덱 조합) → (컨테이너 네이티브 조합) → (아무거나 그 화질)
    """
    if container == "mp4":
        return "/".join(
            (
                f"bestvideo[height<={height}][vcodec^=avc1]+bestaudio[ext=m4a]",
                f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]",
                f"bestvideo[height<={height}]+bestaudio",
                f"best[height<={height}][ext=mp4]",
                f"best[height<={height}]",
            )
        )
    return "/".join(
        (
            f"bestvideo[height<={height}][ext=webm][vcodec^=vp9]+bestaudio[acodec=opus]",
            f"bestvideo[height<={height}][ext=webm]+bestaudio[ext=webm]",
            f"bestvideo[height<={height}]+bestaudio",
            f"best[height<={height}][ext=webm]",
            f"best[height<={height}]",
        )
    )


AUDIO_FORMAT_SELECTOR = "bestaudio/best"


__all__ = [
    "AUDIO_FORMAT_SELECTOR",
    "FormatIndex",
    "MP3_BITRATES",
    "Option",
    "VIDEO_CONTAINERS",
    "VIDEO_HEIGHTS",
    "WAV_PROFILES",
    "build_audio_options",
    "build_video_options",
    "index_formats",
    "negotiate_video",
    "video_format_selector",
]
