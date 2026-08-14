"""작업(잡) 관리 — 큐, 동시 실행 제한, 진행률 브로드캐스트, TTL 청소.

metube 의 큐 구조를 참고하되, 파일을 영구 보관하지 않고 cobalt 처럼
"받아가면 끝" 에 가깝게 30분 TTL 로 지운다.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .config import settings
from .errors import FriendlyError, humanize

logger = logging.getLogger("japangi.jobs")

QUEUED = "queued"
DOWNLOADING = "downloading"
PROCESSING = "processing"
DONE = "done"
ERROR = "error"


@dataclass
class Job:
    id: str
    params: dict[str, Any]
    directory: Path
    status: str = QUEUED
    percent: float = 0.0
    speed: str | None = None
    eta: int | None = None
    message: str = "대기 중이에요"
    indeterminate: bool = False
    filepath: Path | None = None
    filename: str | None = None
    filesize: int | None = None
    error: str | None = None
    error_code: str | None = None
    created_at: float = field(default_factory=time.monotonic)
    finished_at: float | None = None
    queue_position: int | None = None
    _subscribers: list[asyncio.Queue] = field(default_factory=list, repr=False)

    def snapshot(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": self.status,
            "percent": round(self.percent, 1),
            "message": self.message,
            "indeterminate": self.indeterminate,
        }
        if self.speed:
            payload["speed"] = self.speed
        if self.eta is not None:
            payload["eta"] = self.eta
        if self.queue_position is not None:
            payload["queuePosition"] = self.queue_position
        if self.status == DONE:
            payload["filename"] = self.filename
            payload["filesize"] = self.filesize
        if self.status == ERROR:
            payload["error"] = self.error
            payload["code"] = self.error_code
        return payload

    @property
    def terminal(self) -> bool:
        return self.status in (DONE, ERROR)


class JobManager:
    """잡 생성 → 큐 → 실행 → 브로드캐스트 → TTL 삭제까지 전부 여기서."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._semaphore: asyncio.Semaphore | None = None
        self._executor = ThreadPoolExecutor(
            max_workers=max(2, settings.max_concurrent_jobs), thread_name_prefix="japangi-dl"
        )
        self._cleaner: asyncio.Task | None = None
        self._waiting: list[str] = []  # 대기 큐 (순번 표시용)
        # create_task 의 반환값을 붙들고 있지 않으면 GC 가 실행 중인 작업을 거둬갈 수 있다.
        self._running: set[asyncio.Task] = set()

    # ── 수명주기 ────────────────────────────────────────────────────────────

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_jobs)
        settings.work_dir.mkdir(parents=True, exist_ok=True)
        self._cleaner = asyncio.create_task(self._cleanup_loop())
        logger.info(
            "자판기 가동 — 동시 %s개, TTL %s분, 작업 폴더 %s",
            settings.max_concurrent_jobs,
            settings.job_ttl_seconds // 60,
            settings.work_dir,
        )

    async def shutdown(self) -> None:
        if self._cleaner:
            self._cleaner.cancel()
            try:
                await self._cleaner
            except asyncio.CancelledError:
                pass
        self._executor.shutdown(wait=False, cancel_futures=True)
        for job in list(self._jobs.values()):
            self._remove_dir(job)

    # ── 잡 생성/실행 ────────────────────────────────────────────────────────

    def create(self, params: dict[str, Any]) -> Job:
        active = sum(1 for j in self._jobs.values() if not j.terminal)
        if active >= settings.max_jobs_in_flight:
            raise FriendlyError(
                "자판기가 지금 너무 바빠요. 잠시 뒤 다시 시도해 주세요",
                code="busy",
                status=429,
            )
        job_id = uuid.uuid4().hex
        directory = settings.work_dir / job_id
        directory.mkdir(parents=True, exist_ok=True)
        job = Job(id=job_id, params=params, directory=directory)
        self._jobs[job_id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def submit(self, job: Job, worker: Callable[[Job, Callable[..., None]], None]) -> None:
        task = asyncio.create_task(self._run(job, worker))
        self._running.add(task)
        task.add_done_callback(self._running.discard)

    async def _run(self, job: Job, worker: Callable[[Job, Callable[..., None]], None]) -> None:
        assert self._semaphore is not None and self._loop is not None

        if self._semaphore.locked():
            self._waiting.append(job.id)
            self._refresh_queue_positions()

        async with self._semaphore:
            if job.id in self._waiting:
                self._waiting.remove(job.id)
                self._refresh_queue_positions()
            job.queue_position = None
            self.publish(job, status=DOWNLOADING, percent=0.0, message="상품을 꺼내는 중...")

            def emit(**kwargs: Any) -> None:
                """워커 스레드에서 호출된다 → 이벤트 루프로 안전하게 넘긴다."""
                self._loop.call_soon_threadsafe(lambda: self.publish(job, **kwargs))

            try:
                await self._loop.run_in_executor(self._executor, worker, job, emit)
            except Exception as exc:  # noqa: BLE001 - 전부 사용자 문구로 번역한다
                friendly = humanize(exc, context=f"job {job.id}")
                self.publish(
                    job,
                    status=ERROR,
                    message=friendly.message,
                    error=friendly.message,
                    error_code=friendly.code,
                )
            finally:
                if not job.terminal:
                    self.publish(
                        job,
                        status=ERROR,
                        message="작업이 끝나지 않았어요",
                        error="작업이 끝나지 않았어요",
                        error_code="incomplete",
                    )
                job.finished_at = time.monotonic()

    def _refresh_queue_positions(self) -> None:
        for position, job_id in enumerate(self._waiting, start=1):
            job = self._jobs.get(job_id)
            if job and job.status == QUEUED:
                self.publish(
                    job,
                    queue_position=position,
                    message=f"앞에 {position}명 대기 중이에요",
                )

    # ── 브로드캐스트 ────────────────────────────────────────────────────────

    def publish(self, job: Job, **changes: Any) -> None:
        """잡 상태를 갱신하고 모든 SSE 구독자에게 밀어넣는다 (이벤트 루프 스레드 전용)."""
        for key, value in changes.items():
            if not hasattr(job, key):
                # 조용히 무시하면 "진행률이 안 움직인다" 같은 버그의 원인을 못 찾는다.
                raise AttributeError(f"Job 에 없는 필드입니다: {key}")
            setattr(job, key, value)
        event = job.snapshot()
        for queue in list(job._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.debug("구독자 큐가 가득 참 — 이벤트 하나 버림 (job %s)", job.id)

    def subscribe(self, job: Job) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        queue.put_nowait(job.snapshot())  # 붙자마자 현재 상태부터
        job._subscribers.append(queue)
        return queue

    def unsubscribe(self, job: Job, queue: asyncio.Queue) -> None:
        if queue in job._subscribers:
            job._subscribers.remove(queue)

    # ── TTL 청소 ────────────────────────────────────────────────────────────

    async def _cleanup_loop(self) -> None:
        interval = max(30, min(300, settings.job_ttl_seconds // 4))
        while True:
            try:
                await asyncio.sleep(interval)
                self._sweep()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - 청소 루프는 절대 죽으면 안 된다
                logger.exception("TTL 청소 중 오류")

    def _sweep(self) -> None:
        now = time.monotonic()
        for job_id, job in list(self._jobs.items()):
            reference = job.finished_at or job.created_at
            age = now - reference
            # 끝난 작업은 TTL 후, 시작도 못 한 채 방치된 작업은 넉넉히 2배 후 정리
            limit = settings.job_ttl_seconds if job.terminal else settings.job_ttl_seconds * 2
            if age > limit:
                self._remove_dir(job)
                self._jobs.pop(job_id, None)
                logger.info("작업 %s 정리 완료 (%.0f초 경과)", job_id, age)

    def _remove_dir(self, job: Job) -> None:
        try:
            if job.directory.exists():
                shutil.rmtree(job.directory, ignore_errors=True)
        except OSError:
            logger.warning("작업 폴더 삭제 실패: %s", job.directory)


manager = JobManager()
