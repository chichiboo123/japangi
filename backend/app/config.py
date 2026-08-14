"""애플리케이션 설정 — 전부 환경변수로 덮어쓸 수 있다."""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _csv_env(name: str) -> tuple[str, ...]:
    raw = os.getenv(name) or ""
    return tuple(item.strip().lower() for item in raw.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    # 동시에 실제로 돌아가는 다운로드 작업 수. 초과분은 대기 큐로 들어간다.
    max_concurrent_jobs: int = field(default_factory=lambda: _int_env("MAX_CONCURRENT_JOBS", 3))
    # 디스크/메모리 보호용 재생시간 상한 (기본 2시간)
    max_duration_seconds: int = field(default_factory=lambda: _int_env("MAX_DURATION_SECONDS", 2 * 60 * 60))
    # 완료된 작업 디렉터리를 지우기까지의 시간 (기본 30분)
    job_ttl_seconds: int = field(default_factory=lambda: _int_env("JOB_TTL_SECONDS", 30 * 60))
    # 큐 대기 포함 전체 작업 상한
    max_jobs_in_flight: int = field(default_factory=lambda: _int_env("MAX_JOBS_IN_FLIGHT", 24))

    work_dir: Path = field(
        default_factory=lambda: Path(
            os.getenv("WORK_DIR") or Path(tempfile.gettempdir()) / "link-vending-machine"
        )
    )

    # 인스타그램 비공개 게시물 등을 위한 쿠키 파일. 기본 비활성.
    cookies_file: str | None = field(default_factory=lambda: (os.getenv("COOKIES_FILE") or "").strip() or None)

    # 로컬 e2e 테스트에서만 쓰는 추가 허용 호스트. 운영에서는 절대 설정하지 말 것.
    extra_allowed_hosts: tuple[str, ...] = field(default_factory=lambda: _csv_env("EXTRA_ALLOWED_HOSTS"))

    # 프론트 정적 빌드 결과물 (Docker 이미지 안에서 서빙)
    static_dir: Path = field(default_factory=lambda: Path(os.getenv("STATIC_DIR") or "frontend_dist"))

    @property
    def cookies_enabled(self) -> bool:
        return bool(self.cookies_file and Path(self.cookies_file).is_file())


settings = Settings()
