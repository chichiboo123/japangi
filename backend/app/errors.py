"""yt-dlp 에러를 사용자 친화 문구로 번역한다.

원문 스택 트레이스는 서버 로그에만 남기고, 사용자에게는 자판기 말투로만 보여준다.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger("japangi.errors")


class FriendlyError(Exception):
    """사용자에게 그대로 보여줘도 되는 에러."""

    def __init__(self, message: str, *, code: str = "unavailable", status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status


# (정규식, 사용자 메시지, 코드) — 위에서부터 먼저 맞는 것을 쓴다.
_PATTERNS: tuple[tuple[str, str, str], ...] = (
    (
        r"login required|requires? login|log in|authentication|cookies|rate-?limit reached|"
        r"empty media response|not available.*(?:logged|sign)",
        "이 링크는 자판기가 받을 수 없어요 (비공개이거나 로그인이 필요한 게시물이에요)",
        "login_required",
    ),
    (
        r"private (?:video|account|post)|this post is private",
        "비공개 게시물이라 자판기가 받을 수 없어요",
        "private",
    ),
    (
        r"video unavailable|removed by the uploader|no longer available|has been terminated|"
        r"account.*(?:closed|terminated)",
        "삭제되었거나 더 이상 볼 수 없는 게시물이에요",
        "gone",
    ),
    (
        r"age.?restrict|confirm your age|inappropriate for some users",
        "연령 제한 콘텐츠라 자판기가 받을 수 없어요",
        "age_restricted",
    ),
    (
        r"geo.?restrict|available in your country|blocked it in your country",
        "지역 제한이 걸린 콘텐츠예요",
        "geo_blocked",
    ),
    (
        r"members-only|join this channel|premium",
        "멤버십 전용 콘텐츠라 받을 수 없어요",
        "members_only",
    ),
    (
        r"live event will begin|is live|premieres in|upcoming",
        "아직 시작하지 않았거나 진행 중인 라이브예요. 끝난 뒤에 다시 시도해 주세요",
        "live",
    ),
    (
        r"unsupported url|unable to extract|no video formats|unable to download webpage.*404|"
        r"does not pass filter",
        "이 링크에서는 받을 수 있는 영상이나 음원을 찾지 못했어요",
        "no_media",
    ),
    (
        r"sign in to confirm.*(?:not a bot|you'?re not a bot)|bot",
        "유튜브가 이 서버를 봇으로 보고 있어요. 개인 PC에서 실행하거나 COOKIES_FILE을 설정해 주세요",
        "bot_check",
    ),
    (
        r"timed out|timeout|connection reset|temporary failure|network is unreachable|"
        r"failed to resolve|getaddrinfo",
        "네트워크가 불안정해서 실패했어요. 잠시 뒤 다시 시도해 주세요",
        "network",
    ),
    (
        r"ffmpeg|postprocess|conversion failed",
        "변환하는 중에 문제가 생겼어요. 다른 형식으로 다시 시도해 주세요",
        "convert_failed",
    ),
)

_COMPILED = tuple((re.compile(p, re.IGNORECASE), msg, code) for p, msg, code in _PATTERNS)

_FALLBACK = (
    "자판기가 이 링크를 처리하지 못했어요. 링크를 확인하고 다시 시도해 주세요",
    "unknown",
)


def humanize(exc: BaseException, *, context: str = "") -> FriendlyError:
    """예외를 FriendlyError 로 바꾼다. 원문은 로그로만 남는다."""
    if isinstance(exc, FriendlyError):
        return exc

    raw = str(exc) or exc.__class__.__name__
    logger.warning("yt-dlp 실패%s: %s", f" ({context})" if context else "", raw, exc_info=True)

    for pattern, message, code in _COMPILED:
        if pattern.search(raw):
            return FriendlyError(message, code=code)

    message, code = _FALLBACK
    return FriendlyError(message, code=code)
