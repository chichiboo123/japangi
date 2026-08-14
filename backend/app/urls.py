"""URL 검증 — SSRF 방지를 위한 화이트리스트."""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import urlsplit

from .config import settings

# 등록 도메인 기준 화이트리스트. 서브도메인은 허용하되 접미사 매칭만 인정한다.
YOUTUBE_DOMAINS = (
    "youtube.com",
    "youtu.be",
    "youtube-nocookie.com",
    "yt.be",
)
INSTAGRAM_DOMAINS = ("instagram.com",)

ALLOWED_DOMAINS = YOUTUBE_DOMAINS + INSTAGRAM_DOMAINS
ALLOWED_SCHEMES = ("http", "https")


class UrlNotAllowed(ValueError):
    """화이트리스트에 없거나 형태가 잘못된 URL."""


@dataclass(frozen=True)
class ParsedTarget:
    url: str
    host: str
    source: str  # "youtube" | "instagram" | "test"


def _registrable_match(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def classify_host(host: str) -> str | None:
    if any(_registrable_match(host, d) for d in YOUTUBE_DOMAINS):
        return "youtube"
    if any(_registrable_match(host, d) for d in INSTAGRAM_DOMAINS):
        return "instagram"
    if host in settings.extra_allowed_hosts:
        # 로컬 e2e 테스트 전용 탈출구. EXTRA_ALLOWED_HOSTS 가 비어 있으면 절대 도달하지 않는다.
        return "test"
    return None


def validate_url(raw: str) -> ParsedTarget:
    """허용된 URL이면 정규화해서 돌려주고, 아니면 UrlNotAllowed 를 던진다."""
    if not raw or not raw.strip():
        raise UrlNotAllowed("링크를 넣어주세요.")

    candidate = raw.strip()
    if "://" not in candidate:
        # "youtu.be/xxxx" 처럼 스킴 없이 붙여넣는 경우가 흔하다.
        candidate = "https://" + candidate

    try:
        parts = urlsplit(candidate)
    except ValueError as exc:  # noqa: BLE001 - urlsplit 은 잘못된 IPv6 등에서 던진다
        raise UrlNotAllowed("링크 형태가 올바르지 않아요.") from exc

    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        raise UrlNotAllowed("http/https 링크만 넣을 수 있어요.")

    if parts.username or parts.password:
        raise UrlNotAllowed("링크 형태가 올바르지 않아요.")

    host = (parts.hostname or "").lower().rstrip(".")
    if not host:
        raise UrlNotAllowed("링크 형태가 올바르지 않아요.")

    # IP 리터럴은 무조건 거부 (내부망 접근 차단)
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise UrlNotAllowed("이 자판기는 유튜브와 인스타그램 링크만 받아요.")

    source = classify_host(host)
    if source is None:
        raise UrlNotAllowed("이 자판기는 유튜브와 인스타그램 링크만 받아요.")

    if source != "test" and parts.port not in (None, 80, 443):
        raise UrlNotAllowed("링크 형태가 올바르지 않아요.")

    normalized = parts._replace(scheme=parts.scheme.lower(), fragment="").geturl()
    return ParsedTarget(url=normalized, host=host, source=source)
