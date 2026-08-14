"""URL 화이트리스트 / SSRF 방어 테스트."""
from __future__ import annotations

import pytest

from app.urls import UrlNotAllowed, validate_url


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ",
        "https://m.youtube.com/watch?v=x",
        "https://music.youtube.com/watch?v=x",
        "https://www.youtube-nocookie.com/embed/x",
        "https://www.instagram.com/reel/Cabc123/",
        "https://instagram.com/p/Cabc123/",
    ],
)
def test_allowed_urls(url):
    assert validate_url(url).url


def test_source_classification():
    assert validate_url("https://youtu.be/x").source == "youtube"
    assert validate_url("https://www.instagram.com/reel/x/").source == "instagram"


def test_scheme_is_added_when_missing():
    assert validate_url("youtu.be/abc").url.startswith("https://")


def test_fragment_is_stripped():
    assert "#" not in validate_url("https://youtu.be/abc#t=30").url


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.com/video",
        "https://youtube.com.evil.com/watch?v=x",  # 접미사 위장
        "https://notyoutube.com/watch?v=x",
        "https://vimeo.com/12345",
    ],
)
def test_non_whitelisted_hosts_are_rejected(url):
    with pytest.raises(UrlNotAllowed):
        validate_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8000/secret",
        "http://169.254.169.254/latest/meta-data/",  # 클라우드 메타데이터
        "http://[::1]/x",
        "http://10.0.0.5/internal",
        "https://192.168.1.1/admin",
    ],
)
def test_ip_literals_are_rejected(url):
    with pytest.raises(UrlNotAllowed):
        validate_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://youtube.com/x",
        "gopher://youtube.com/x",
        "javascript:alert(1)",
    ],
)
def test_non_http_schemes_are_rejected(url):
    with pytest.raises(UrlNotAllowed):
        validate_url(url)


def test_credentials_in_url_are_rejected():
    with pytest.raises(UrlNotAllowed):
        validate_url("https://user:pass@youtube.com/watch?v=x")


def test_odd_ports_are_rejected():
    with pytest.raises(UrlNotAllowed):
        validate_url("https://www.youtube.com:8080/watch?v=x")


@pytest.mark.parametrize("url", ["", "   ", "not a url at all "])
def test_empty_and_garbage(url):
    with pytest.raises(UrlNotAllowed):
        validate_url(url)


def test_extra_hosts_are_disabled_by_default():
    """EXTRA_ALLOWED_HOSTS 를 설정하지 않으면 로컬 호스트는 절대 통과하지 못한다."""
    with pytest.raises(UrlNotAllowed):
        validate_url("http://localhost:9999/video.mp4")
