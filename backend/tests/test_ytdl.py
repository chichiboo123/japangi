"""yt-dlp 래퍼 테스트 — 옵션 구성, 재생목록 처리, 쿠키 설정."""
from __future__ import annotations

from pathlib import Path

import pytest
from yt_dlp.utils import ExtractorError

from app import ytdl


class FakeYoutubeDL:
    """extract_info 만 흉내내는 가짜. 마지막으로 받은 opts 를 클래스에 남긴다."""

    last_opts: dict = {}
    result: object = None

    def __init__(self, opts):
        FakeYoutubeDL.last_opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def extract_info(self, url, download=False):  # noqa: ARG002
        if isinstance(FakeYoutubeDL.result, Exception):
            raise FakeYoutubeDL.result
        return FakeYoutubeDL.result

    def sanitize_info(self, info):
        return info


@pytest.fixture
def fake_ydl(monkeypatch):
    monkeypatch.setattr(ytdl, "YoutubeDL", FakeYoutubeDL)
    return FakeYoutubeDL


# ── 기본 옵션 ────────────────────────────────────────────────────────────────


def test_base_opts_are_quiet_and_single_video():
    opts = ytdl.build_opts()
    assert opts["quiet"] is True
    assert opts["noplaylist"] is True  # 재생목록 링크여도 영상 하나만
    assert opts["noprogress"] is True  # 진행률은 hook 으로 받는다
    assert opts["retries"] >= 3  # 재시도는 yt-dlp 에 맡긴다


def test_cookies_are_disabled_by_default():
    assert "cookiefile" not in ytdl.build_opts()


def test_cookies_are_used_when_the_file_exists(tmp_path, override_settings):
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text("# Netscape HTTP Cookie File\n")
    override_settings(cookies_file=str(cookie_file))
    assert ytdl.build_opts()["cookiefile"] == str(cookie_file)


def test_missing_cookie_file_is_ignored_rather_than_crashing(override_settings):
    """경로만 잘못 적어둔 채로 서버가 안 뜨면 곤란하다."""
    override_settings(cookies_file="/does/not/exist.txt")
    assert "cookiefile" not in ytdl.build_opts()


def test_overrides_win():
    opts = ytdl.build_opts(format="bestaudio", quiet=False)
    assert opts["format"] == "bestaudio"
    assert opts["quiet"] is False


# ── 재생목록 / 예외 처리 ─────────────────────────────────────────────────────


def test_playlist_url_falls_back_to_the_first_entry(fake_ydl):
    fake_ydl.result = {
        "_type": "playlist",
        "entries": [
            {"id": "first", "title": "첫 번째"},
            {"id": "second", "title": "두 번째"},
        ],
    }
    assert ytdl.extract_info("https://youtube.com/playlist?list=x")["id"] == "first"


def test_playlist_skips_none_entries(fake_ydl):
    """비공개 영상이 섞이면 yt-dlp 가 None 을 끼워 넣는다."""
    fake_ydl.result = {"_type": "playlist", "entries": [None, {"id": "ok"}]}
    assert ytdl.extract_info("https://youtube.com/playlist?list=x")["id"] == "ok"


def test_empty_playlist_raises(fake_ydl):
    fake_ydl.result = {"_type": "playlist", "entries": []}
    with pytest.raises(ExtractorError):
        ytdl.extract_info("https://youtube.com/playlist?list=x")


def test_none_result_raises(fake_ydl):
    fake_ydl.result = None
    with pytest.raises(ExtractorError):
        ytdl.extract_info("https://youtube.com/watch?v=x")


# ── 최종 파일 경로 찾기 ──────────────────────────────────────────────────────


def test_resolved_filepath_prefers_requested_downloads():
    info = {
        "requested_downloads": [{"filepath": "/work/final.mp4"}],
        "filepath": "/work/stale.webm",
    }
    assert ytdl.resolved_filepath(info) == "/work/final.mp4"


def test_resolved_filepath_falls_back():
    assert ytdl.resolved_filepath({"filepath": "/work/a.mp3"}) == "/work/a.mp3"
    assert ytdl.resolved_filepath({"_filename": "/work/b.mp3"}) == "/work/b.mp3"
    assert ytdl.resolved_filepath({}) is None


def test_download_passes_selector_and_hooks(fake_ydl, tmp_path):
    fake_ydl.result = {"id": "x", "requested_downloads": [{"filepath": str(tmp_path / "a.mp4")}]}
    calls: list = []
    ytdl.download(
        "https://youtube.com/watch?v=x",
        format_selector="bestvideo+bestaudio",
        outtmpl=str(tmp_path / "source.%(ext)s"),
        progress_hook=calls.append,
        merge_output_format="mp4",
    )
    opts = fake_ydl.last_opts
    assert opts["format"] == "bestvideo+bestaudio"
    assert opts["merge_output_format"] == "mp4"
    assert len(opts["progress_hooks"]) == 1
    assert opts["overwrites"] is True
    assert Path(opts["outtmpl"]["default"]).name == "source.%(ext)s"
