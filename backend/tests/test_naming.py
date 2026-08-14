"""파일명 정규화 / RFC 5987 헤더 테스트."""
from __future__ import annotations

from urllib.parse import unquote

import pytest

from app.naming import build_filename, content_disposition, sanitize_component


def test_korean_title_is_preserved():
    assert build_filename("우리 반 뮤지컬 연습", "320", "mp3") == "우리 반 뮤지컬 연습_320.mp3"


def test_quality_labels_are_readable():
    assert build_filename("노래", "48000-24", "wav") == "노래_48kHz24bit.wav"
    assert build_filename("노래", "44100-16", "wav") == "노래_44.1kHz16bit.wav"
    assert build_filename("영상", "1080p", "mp4") == "영상_1080p.mp4"


@pytest.mark.parametrize(
    ("raw", "banned"),
    [
        ('제목/슬래시', "/"),
        ("제목\\역슬래시", "\\"),
        ("제목:콜론", ":"),
        ('제목"따옴표', '"'),
        ("제목|파이프", "|"),
        ("제목?물음표", "?"),
        ("제목*별표", "*"),
        ("제목<꺾쇠>", "<"),
    ],
)
def test_os_forbidden_characters_are_replaced(raw, banned):
    assert banned not in sanitize_component(raw)


def test_path_traversal_is_neutralized():
    result = sanitize_component("../../etc/passwd")
    assert ".." not in result
    assert "/" not in result


def test_leading_dots_and_spaces_are_trimmed():
    assert sanitize_component("  ...숨김파일  ") == "숨김파일"


def test_windows_reserved_names_are_escaped():
    assert sanitize_component("CON") == "_CON"
    assert sanitize_component("com1") == "_com1"


def test_empty_title_falls_back():
    assert sanitize_component("") == "제목없음"
    assert sanitize_component("///") != ""


def test_long_titles_are_truncated_without_breaking_utf8():
    long_korean = "가" * 200
    result = sanitize_component(long_korean)
    assert len(result.encode("utf-8")) <= 120
    result.encode("utf-8").decode("utf-8")  # 깨지지 않아야 한다


def test_extension_is_sanitized():
    assert build_filename("영상", "1080p", "../mp4").endswith(".mp4")
    assert build_filename("영상", "1080p", "").endswith(".bin")


# ── Content-Disposition ──────────────────────────────────────────────────────


def test_content_disposition_encodes_korean():
    header = content_disposition("우리 반 뮤지컬_320.mp3")
    assert "filename*=UTF-8''" in header
    encoded = header.split("filename*=UTF-8''")[1]
    assert unquote(encoded) == "우리 반 뮤지컬_320.mp3"


def test_content_disposition_has_ascii_fallback():
    header = content_disposition("한글제목_320.mp3")
    assert header.startswith('attachment; filename="')
    fallback = header.split('"')[1]
    fallback.encode("ascii")  # 폴백은 반드시 ASCII


def test_content_disposition_is_header_safe():
    header = content_disposition('나쁜"제목_1080p.mp4')
    assert header.count('"') == 2  # 따옴표 이스케이프로 헤더가 깨지지 않아야 한다
    assert "\n" not in header and "\r" not in header
