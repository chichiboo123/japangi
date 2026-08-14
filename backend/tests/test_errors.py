"""에러 번역 테스트 — 사용자에게 스택 트레이스가 절대 노출되면 안 된다."""
from __future__ import annotations

import pytest
from yt_dlp.utils import DownloadError, ExtractorError

from app.errors import FriendlyError, humanize


def test_instagram_login_required_is_friendly():
    exc = ExtractorError(
        "[Instagram] Cabc123: Requested content is not available, rate-limit reached or "
        "login required. Use --cookies-from-browser or --cookies for the authentication."
    )
    friendly = humanize(exc)
    assert friendly.code == "login_required"
    assert "비공개" in friendly.message and "로그인" in friendly.message


def test_instagram_private_account():
    friendly = humanize(ExtractorError("This post is private"))
    assert friendly.code in ("private", "login_required")
    assert "비공개" in friendly.message


@pytest.mark.parametrize(
    ("raw", "expected_code"),
    [
        ("ERROR: Video unavailable. This video has been removed by the uploader", "gone"),
        ("Sign in to confirm your age. This video may be inappropriate for some users.", "age_restricted"),
        ("The uploader has not made this video available in your country", "geo_blocked"),
        ("Join this channel to get access to members-only content", "members_only"),
        ("This live event will begin in 3 hours", "live"),
        ("Unsupported URL: https://example.com/x", "no_media"),
        ("Sign in to confirm you're not a bot", "bot_check"),
        ("[Errno 110] Connection timed out", "network"),
        ("Postprocessing: ffmpeg conversion failed", "convert_failed"),
    ],
)
def test_known_failures_map_to_codes(raw, expected_code):
    assert humanize(DownloadError(raw)).code == expected_code


def test_unknown_error_gets_generic_message():
    friendly = humanize(RuntimeError("something exploded at 0x7fff in module <foo>"))
    assert friendly.code == "unknown"
    assert "0x7fff" not in friendly.message
    assert "자판기" in friendly.message


def test_messages_never_leak_internals():
    noisy = DownloadError(
        'Traceback (most recent call last):\n  File "/app/yt_dlp/extractor/youtube.py", line 42\n'
        "KeyError: 'streamingData'"
    )
    friendly = humanize(noisy)
    for leak in ("Traceback", "yt_dlp", ".py", "KeyError"):
        assert leak not in friendly.message


def test_friendly_error_passes_through_unchanged():
    original = FriendlyError("이미 친절한 메시지", code="custom", status=418)
    assert humanize(original) is original


def test_all_messages_are_korean_and_short():
    for exc in (
        ExtractorError("login required"),
        DownloadError("Video unavailable"),
        RuntimeError("boom"),
    ):
        message = humanize(exc).message
        assert len(message) < 120
        assert any("가" <= ch <= "힣" for ch in message)  # 한글 포함
