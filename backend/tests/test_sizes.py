"""예상 용량 계산 단위 테스트 — 이 앱의 핵심 로직."""
from __future__ import annotations

import pytest

from app import sizes


# ── MP3 (CBR) ────────────────────────────────────────────────────────────────


def test_mp3_320kbps_213seconds_matches_spec():
    # 320 × 1000 × 213 ÷ 8 = 8,520,000 B
    assert sizes.mp3_bytes(320, 213) == 8_520_000


@pytest.mark.parametrize(
    ("kbps", "seconds", "expected"),
    [
        (128, 60, 960_000),
        (192, 60, 1_440_000),
        (256, 60, 1_920_000),
        (320, 60, 2_400_000),
    ],
)
def test_mp3_bitrate_table(kbps, seconds, expected):
    assert sizes.mp3_bytes(kbps, seconds) == expected


def test_mp3_scales_linearly_with_duration():
    assert sizes.mp3_bytes(192, 120) == 2 * sizes.mp3_bytes(192, 60)


def test_mp3_without_duration_is_unknown():
    assert sizes.mp3_bytes(320, None) is None
    assert sizes.mp3_bytes(320, 0) is None


# ── WAV (무압축 PCM) ─────────────────────────────────────────────────────────


def test_wav_441_16bit_stereo_is_about_10_1_mb_per_minute():
    result = sizes.wav_bytes(44100, 16, 60)
    # 44100 × 16 × 2 × 60 ÷ 8 = 10,584,000 B
    assert result == 10_584_000 + 44
    assert sizes.human_bytes(result) == "10.1 MB"


def test_wav_48k_24bit_stereo_is_about_16_5_mb_per_minute():
    result = sizes.wav_bytes(48000, 24, 60)
    # 48000 × 24 × 2 × 60 ÷ 8 = 17,280,000 B
    assert result == 17_280_000 + 44
    assert sizes.human_bytes(result) == "16.5 MB"


def test_wav_mono_is_half_of_stereo():
    stereo = sizes.wav_bytes(44100, 16, 60, channels=2) - 44
    mono = sizes.wav_bytes(44100, 16, 60, channels=1) - 44
    assert stereo == 2 * mono


def test_wav_is_much_larger_than_mp3():
    wav = sizes.wav_bytes(48000, 24, 213)
    mp3 = sizes.mp3_bytes(320, 213)
    assert wav > mp3 * 7  # 대용량 라벨을 붙일 만한 차이


def test_wav_rejects_bad_input():
    assert sizes.wav_bytes(44100, 16, None) is None
    assert sizes.wav_bytes(0, 16, 60) is None
    assert sizes.wav_bytes(44100, 0, 60) is None


# ── 영상 스트림 ──────────────────────────────────────────────────────────────


def test_video_prefers_exact_filesize():
    fmt = {"filesize": 74_550_000, "filesize_approx": 999, "tbr": 2800.0}
    assert sizes.stream_bytes(fmt, 213) == (74_550_000, sizes.SizeSource.EXACT)


def test_video_falls_back_to_filesize_approx():
    fmt = {"filesize": None, "filesize_approx": 50_000_000, "tbr": 2800.0}
    assert sizes.stream_bytes(fmt, 213) == (50_000_000, sizes.SizeSource.APPROX)


def test_video_falls_back_to_bitrate_times_duration():
    fmt = {"tbr": 2800.0}
    # 2800 × 1000 × 213 ÷ 8 = 74,550,000
    assert sizes.stream_bytes(fmt, 213) == (74_550_000, sizes.SizeSource.BITRATE)


def test_video_uses_vbr_plus_abr_when_tbr_missing():
    fmt = {"vbr": 2000.0, "abr": 128.0}
    assert sizes.stream_bytes(fmt, 100) == (int(2128 * 1000 * 100 / 8), sizes.SizeSource.BITRATE)


def test_video_unknown_without_any_hint():
    assert sizes.stream_bytes({}, 213) == (None, sizes.SizeSource.UNKNOWN)
    assert sizes.stream_bytes({"tbr": 2800.0}, None) == (None, sizes.SizeSource.UNKNOWN)


def test_zero_and_bogus_values_are_ignored():
    assert sizes.stream_bytes({"filesize": 0, "tbr": 1000.0}, 10)[1] == sizes.SizeSource.BITRATE
    assert sizes.stream_bytes({"filesize": "not a number", "tbr": 1000.0}, 10)[1] == sizes.SizeSource.BITRATE


# ── 영상 + 음성 합산 (많은 구현이 빠뜨리는 부분) ─────────────────────────────


def test_combined_adds_video_and_audio():
    video = {"filesize": 74_550_000}
    audio = {"filesize": 3_430_000}
    total, source = sizes.combined_bytes(video, audio, 213)
    assert total == 77_980_000
    assert source == sizes.SizeSource.EXACT


def test_combined_downgrades_source_to_the_least_accurate():
    video = {"filesize": 74_550_000}  # 정확
    audio = {"tbr": 128.0}  # 추정
    total, source = sizes.combined_bytes(video, audio, 100)
    assert total == 74_550_000 + int(128 * 1000 * 100 / 8)
    assert source == sizes.SizeSource.BITRATE


def test_combined_without_audio_is_just_video():
    assert sizes.combined_bytes({"filesize": 100}, None, 10) == (100, sizes.SizeSource.EXACT)


def test_combined_all_unknown():
    assert sizes.combined_bytes({}, {}, None) == (None, sizes.SizeSource.UNKNOWN)


# ── 표시 규칙 (1024 기준, 소수점 1자리) ──────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "0 B"),
        (512, "512 B"),
        (1024, "1.0 KB"),
        (1536, "1.5 KB"),
        (1024 * 1024, "1.0 MB"),
        (8_520_000, "8.1 MB"),
        (1024 ** 3, "1.0 GB"),
        (319_500_000, "304.7 MB"),
    ],
)
def test_human_bytes(value, expected):
    assert sizes.human_bytes(value) == expected


def test_human_bytes_handles_none():
    assert sizes.human_bytes(None) == "용량 미상"
