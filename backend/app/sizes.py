"""예상 용량 계산.

이 앱의 핵심 로직이라 의도적으로 순수 함수만 모아두었다 (I/O 없음 → 단위 테스트 쉬움).

계산 우선순위
  영상: filesize(정확값) → filesize_approx → tbr × duration ÷ 8
  음원: 인코딩 전이므로 항상 공식으로 계산한다.
       MP3(CBR)  = kbps × 1000 × 초 ÷ 8
       WAV(PCM)  = 샘플레이트 × 비트깊이 × 채널수 × 초 ÷ 8
"""
from __future__ import annotations

from typing import Any, Mapping

# 1 KB = 1024 B (표시 규칙)
_UNITS = ("B", "KB", "MB", "GB", "TB")


class SizeSource:
    """추정치가 어디서 나왔는지. 프론트 툴팁에서 '정확/추정'을 구분하는 데 쓴다."""

    EXACT = "exact"  # filesize
    APPROX = "approx"  # filesize_approx
    BITRATE = "bitrate"  # tbr × duration
    FORMULA = "formula"  # 음원 인코딩 공식
    UNKNOWN = "unknown"


def human_bytes(num: float | int | None, decimals: int = 1) -> str:
    """1024 기준으로 KB/MB/GB 자동 변환. 소수점 1자리."""
    if num is None:
        return "용량 미상"
    value = float(num)
    if value < 0:
        return "용량 미상"
    unit_index = 0
    while value >= 1024 and unit_index < len(_UNITS) - 1:
        value /= 1024
        unit_index += 1
    if unit_index == 0:
        return f"{int(value)} {_UNITS[0]}"
    return f"{value:.{decimals}f} {_UNITS[unit_index]}"


def _positive(value: Any) -> float | None:
    """yt-dlp 는 None, 문자열, 0 등 뭐든 줄 수 있어서 방어적으로 받는다."""
    if value is None or isinstance(value, bool):
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if num <= 0:
        return None
    return num


def stream_bytes(fmt: Mapping[str, Any] | None, duration: float | None) -> tuple[int | None, str]:
    """단일 스트림(영상 또는 음성)의 용량과 출처를 돌려준다."""
    if not fmt:
        return None, SizeSource.UNKNOWN

    exact = _positive(fmt.get("filesize"))
    if exact is not None:
        return int(exact), SizeSource.EXACT

    approx = _positive(fmt.get("filesize_approx"))
    if approx is not None:
        return int(approx), SizeSource.APPROX

    seconds = _positive(duration)
    if seconds is None:
        return None, SizeSource.UNKNOWN

    # tbr 은 kbps(1000 기준). vbr/abr 만 있는 포맷도 있어서 순서대로 본다.
    bitrate_kbps = _positive(fmt.get("tbr"))
    if bitrate_kbps is None:
        vbr = _positive(fmt.get("vbr")) or 0.0
        abr = _positive(fmt.get("abr")) or 0.0
        bitrate_kbps = (vbr + abr) or None
    if bitrate_kbps is None:
        return None, SizeSource.UNKNOWN

    return int(bitrate_kbps * 1000 * seconds / 8), SizeSource.BITRATE


def combined_bytes(
    video_fmt: Mapping[str, Any] | None,
    audio_fmt: Mapping[str, Any] | None,
    duration: float | None,
) -> tuple[int | None, str]:
    """video-only + audio-only 를 머지하는 경우 두 용량을 **더한다**.

    이걸 빠뜨리면 1080p 영상에서 오디오 트랙(보통 3~5MB) 만큼 과소 추정된다.
    """
    video_size, video_src = stream_bytes(video_fmt, duration)
    if audio_fmt is None:
        return video_size, video_src

    audio_size, audio_src = stream_bytes(audio_fmt, duration)
    if video_size is None and audio_size is None:
        return None, SizeSource.UNKNOWN
    total = (video_size or 0) + (audio_size or 0)

    # 둘 중 하나라도 추정이면 전체가 추정이다. 정확도가 낮은 쪽으로 맞춘다.
    rank = {
        SizeSource.EXACT: 0,
        SizeSource.APPROX: 1,
        SizeSource.BITRATE: 2,
        SizeSource.UNKNOWN: 3,
    }
    worst = max((video_src, audio_src), key=lambda s: rank.get(s, 3))
    return total, worst


def mp3_bytes(bitrate_kbps: int, duration: float | None) -> int | None:
    """MP3 CBR: kbps × 1000 × 초 ÷ 8.

    예) 320kbps × 213초 = 8,520,000 B
    ID3 태그/프레임 헤더 오버헤드는 1% 미만이라 무시한다.
    """
    seconds = _positive(duration)
    if seconds is None or bitrate_kbps <= 0:
        return None
    return int(bitrate_kbps * 1000 * seconds / 8)


def wav_bytes(
    sample_rate: int,
    bit_depth: int,
    duration: float | None,
    channels: int = 2,
) -> int | None:
    """무압축 PCM: 샘플레이트 × 비트깊이 × 채널수 × 초 ÷ 8 (+ 44B 헤더).

    44.1kHz/16bit/스테레오 → 약 10.1 MB/분
    48kHz/24bit/스테레오   → 약 16.5 MB/분
    """
    seconds = _positive(duration)
    if seconds is None or sample_rate <= 0 or bit_depth <= 0 or channels <= 0:
        return None
    payload = sample_rate * bit_depth * channels * seconds / 8
    return int(payload) + 44  # RIFF/fmt/data 헤더


__all__ = [
    "SizeSource",
    "combined_bytes",
    "human_bytes",
    "mp3_bytes",
    "stream_bytes",
    "wav_bytes",
]
