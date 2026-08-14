"""진열대 구성 & 코덱 협상 테스트."""
from __future__ import annotations

import pytest

from app import formats
from tests import fixtures


def options_by_key(options):
    return {(o.format, o.quality): o for o in options}


# ── 포맷 인덱싱 ──────────────────────────────────────────────────────────────


def test_index_separates_video_and_audio_and_drops_storyboards():
    index = formats.index_formats(fixtures.youtube_full())
    assert index.max_height == 2160
    assert len(index.audios) == 3
    assert all(f.get("ext") != "mhtml" for f in index.videos + index.audios)


def test_index_handles_muxed_only_source():
    index = formats.index_formats(fixtures.instagram_reel())
    assert index.max_height == 1080
    assert index.has_audio
    assert len(index.muxed) == 1


def test_best_audio_prefers_requested_codec():
    index = formats.index_formats(fixtures.youtube_full())
    opus = index.best_audio(("opus",))
    m4a = index.best_audio(("mp4a", "aac"))
    assert opus["acodec"].startswith("opus")
    assert m4a["acodec"].startswith("mp4a")


# ── 음원 진열대 ──────────────────────────────────────────────────────────────


def test_audio_shelf_has_four_mp3_and_two_wav():
    options = formats.build_audio_options(formats.index_formats(fixtures.youtube_full()))
    assert [o.quality for o in options if o.format == "mp3"] == ["128", "192", "256", "320"]
    assert [o.quality for o in options if o.format == "wav"] == ["44100-16", "48000-24"]
    assert all(o.available for o in options)


def test_wav_gets_large_size_badge():
    options = formats.build_audio_options(formats.index_formats(fixtures.youtube_full()))
    wav = [o for o in options if o.format == "wav"]
    assert all(o.badge == "대용량" for o in wav)


def test_audio_sizes_use_the_formula_not_the_source_stream():
    options = options_by_key(formats.build_audio_options(formats.index_formats(fixtures.youtube_full())))
    assert options[("mp3", "320")].estimated_bytes == 8_520_000
    assert options[("wav", "48000-24")].estimated_bytes == int(48000 * 24 * 2 * 213 / 8) + 44


def test_audio_shelf_is_sold_out_when_source_has_no_audio():
    silent = {"duration": 60, "formats": [
        {"format_id": "v", "ext": "mp4", "height": 720, "vcodec": "avc1", "acodec": "none", "tbr": 1000}
    ]}
    options = formats.build_audio_options(formats.index_formats(silent))
    assert all(not o.available for o in options)


def test_mp3_above_source_bitrate_gets_a_note():
    options = options_by_key(formats.build_audio_options(formats.index_formats(fixtures.audio_only_source())))
    # 원본이 128kbps → 320 을 골라도 음질이 좋아지지 않는다
    assert options[("mp3", "320")].note is not None
    assert options[("mp3", "128")].note is None


# ── 영상 진열대: 재고 판정 ───────────────────────────────────────────────────


def test_all_heights_available_on_a_full_youtube_video():
    options = options_by_key(formats.build_video_options(formats.index_formats(fixtures.youtube_full())))
    for container in ("mp4", "webm"):
        for quality in ("360p", "720p", "1080p", "2160p"):
            assert options[(container, quality)].available, f"{container} {quality}"


def test_heights_above_the_source_are_sold_out():
    options = options_by_key(formats.build_video_options(formats.index_formats(fixtures.youtube_low())))
    assert options[("mp4", "360p")].available
    assert not options[("mp4", "720p")].available
    assert not options[("mp4", "1080p")].available
    assert not options[("mp4", "2160p")].available
    assert "480p" in (options[("mp4", "720p")].note or "")


def test_sold_out_options_have_no_estimated_size():
    options = formats.build_video_options(formats.index_formats(fixtures.youtube_low()))
    assert all(o.estimated_bytes is None for o in options if not o.available)


def test_no_video_shelf_for_audio_only_source():
    assert formats.build_video_options(formats.index_formats(fixtures.audio_only_source())) == []


# ── 영상 진열대: 코덱 협상 ───────────────────────────────────────────────────


def test_h264_available_up_to_1080p_means_no_reencode():
    options = options_by_key(formats.build_video_options(formats.index_formats(fixtures.youtube_full())))
    for quality in ("360p", "720p", "1080p"):
        option = options[("mp4", quality)]
        assert option.needs_reencode is False
        assert option.warning is None


def test_mp4_4k_remuxes_av1_instead_of_reencoding():
    """유튜브 4K 에 H.264 가 없어도 AV1 은 MP4 컨테이너에 담을 수 있다 → 리먹스."""
    option = options_by_key(
        formats.build_video_options(formats.index_formats(fixtures.youtube_full()))
    )[("mp4", "2160p")]
    assert option.available
    assert option.needs_reencode is False
    assert option.warning is not None
    assert "리먹스" in option.warning


def test_webm_is_native_for_vp9_source():
    options = options_by_key(formats.build_video_options(formats.index_formats(fixtures.youtube_full())))
    for quality in ("360p", "720p", "1080p", "2160p"):
        option = options[("webm", quality)]
        assert option.needs_reencode is False, quality


def test_webm_from_h264_only_source_needs_reencode():
    """인스타처럼 H.264 밖에 없으면 WebM 은 재인코딩이 불가피하다."""
    option = options_by_key(
        formats.build_video_options(formats.index_formats(fixtures.instagram_reel()))
    )[("webm", "1080p")]
    assert option.available
    assert option.needs_reencode is True
    assert "재인코딩" in (option.warning or "")


def test_mp4_from_h264_only_source_never_needs_reencode():
    option = options_by_key(
        formats.build_video_options(formats.index_formats(fixtures.instagram_reel()))
    )[("mp4", "1080p")]
    assert option.needs_reencode is False
    assert option.warning is None


# ── 영상 용량: 합산 확인 ─────────────────────────────────────────────────────


def test_video_size_includes_the_audio_track():
    index = formats.index_formats(fixtures.youtube_full())
    option = options_by_key(formats.build_video_options(index))[("mp4", "1080p")]
    video_only_size = 74_550_000
    assert option.estimated_bytes is not None
    assert option.estimated_bytes > video_only_size  # 오디오가 더해져야 한다
    assert option.estimated_bytes == video_only_size + 3_430_000  # m4a 트랙


def test_webm_size_uses_opus_audio_track():
    index = formats.index_formats(fixtures.youtube_full())
    option = options_by_key(formats.build_video_options(index))[("webm", "1080p")]
    assert option.estimated_bytes == 50_590_000 + 4_260_000


def test_muxed_source_size_is_not_double_counted():
    index = formats.index_formats(fixtures.instagram_reel())
    option = options_by_key(formats.build_video_options(index))[("mp4", "1080p")]
    # 2500kbps × 30초 ÷ 8 = 9,375,000 — 오디오를 또 더하면 안 된다
    assert option.estimated_bytes == 9_375_000


def test_size_estimated_from_bitrate_when_filesize_missing():
    index = formats.index_formats(fixtures.no_filesize_video())
    option = options_by_key(formats.build_video_options(index))[("webm", "1080p")]
    assert option.size_source == "bitrate"
    assert option.estimated_bytes == int(2000 * 1000 * 100 / 8) + int(128 * 1000 * 100 / 8)


# ── format selector 문자열 ───────────────────────────────────────────────────


@pytest.mark.parametrize("height", [360, 720, 1080, 2160])
def test_mp4_selector_prefers_avc1_then_falls_back(height):
    selector = formats.video_format_selector("mp4", height)
    assert selector.startswith(f"bestvideo[height<={height}][vcodec^=avc1]+bestaudio[ext=m4a]")
    assert selector.endswith(f"best[height<={height}]")
    assert selector.count("/") >= 3  # 폴백 체인이 있어야 한다


@pytest.mark.parametrize("height", [360, 720, 1080, 2160])
def test_webm_selector_prefers_vp9_opus(height):
    selector = formats.video_format_selector("webm", height)
    assert "vcodec^=vp9" in selector
    assert "acodec=opus" in selector


def test_json_shape_matches_the_api_contract():
    index = formats.index_formats(fixtures.youtube_full())
    audio = formats.build_audio_options(index)[0].to_json()
    video = options_by_key(formats.build_video_options(index))[("mp4", "2160p")].to_json()

    assert set(audio) >= {"format", "quality", "label", "estimatedBytes", "available"}
    assert set(video) >= {"format", "quality", "estimatedBytes", "available", "needsReencode"}
    assert "warning" in video
