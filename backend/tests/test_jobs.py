"""잡 관리 테스트 — 동시 실행 제한, 대기 큐, TTL 청소, 에러 처리."""
from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path

import pytest

from app import jobs
from app.errors import FriendlyError
from app.jobs import DONE, DOWNLOADING, ERROR, JobManager


def run(coro):
    return asyncio.run(coro)


async def drain(job, manager: JobManager, timeout: float = 10.0) -> list[dict]:
    """잡이 끝날 때까지 이벤트를 모은다."""
    queue = manager.subscribe(job)
    events: list[dict] = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            event = await asyncio.wait_for(queue.get(), timeout=deadline - time.monotonic())
        except asyncio.TimeoutError:
            break
        events.append(event)
        if event["status"] in (DONE, ERROR):
            break
    manager.unsubscribe(job, queue)
    return events


@pytest.fixture
def manager(tmp_path, override_settings):
    override_settings(work_dir=tmp_path)
    return JobManager()


# ── 기본 흐름 ────────────────────────────────────────────────────────────────


def test_successful_job_reaches_done(manager):
    async def scenario():
        await manager.start()
        job = manager.create({"url": "x"})

        def worker(job, emit):
            emit(status=DOWNLOADING, percent=50.0, message="받는 중")
            emit(status=DONE, percent=100.0, message="완료", filename="a.mp3", filesize=123)

        manager.submit(job, worker)
        events = await drain(job, manager)
        await manager.shutdown()
        return events

    events = run(scenario())
    assert events[-1]["status"] == DONE
    assert events[-1]["filename"] == "a.mp3"
    assert events[-1]["filesize"] == 123


def test_worker_exception_becomes_friendly_error(manager):
    async def scenario():
        await manager.start()
        job = manager.create({"url": "x"})

        def worker(job, emit):
            raise RuntimeError("KeyError: 'streamingData' at yt_dlp/extractor/youtube.py:42")

        manager.submit(job, worker)
        events = await drain(job, manager)
        await manager.shutdown()
        return events

    final = run(scenario())[-1]
    assert final["status"] == ERROR
    assert "yt_dlp" not in final["error"]
    assert "streamingData" not in final["error"]
    assert final["code"] == "unknown"


def test_friendly_error_keeps_its_code(manager):
    async def scenario():
        await manager.start()
        job = manager.create({"url": "x"})

        def worker(job, emit):
            raise FriendlyError("MP4 2160p는 품절이에요", code="sold_out")

        manager.submit(job, worker)
        events = await drain(job, manager)
        await manager.shutdown()
        return events

    final = run(scenario())[-1]
    assert final["code"] == "sold_out"
    assert "품절" in final["error"]


def test_worker_that_finishes_without_terminal_status_is_marked_failed(manager):
    """워커가 조용히 끝나버려도 잡이 영원히 매달려 있으면 안 된다."""

    async def scenario():
        await manager.start()
        job = manager.create({"url": "x"})
        manager.submit(job, lambda job, emit: None)
        events = await drain(job, manager)
        await manager.shutdown()
        return events

    final = run(scenario())[-1]
    assert final["status"] == ERROR
    assert final["code"] == "incomplete"


# ── 동시 실행 제한 & 대기 큐 ─────────────────────────────────────────────────


def test_concurrency_is_capped_and_extra_jobs_queue(manager, override_settings):
    override_settings(max_concurrent_jobs=2)

    peak = 0
    active = 0
    lock = threading.Lock()
    release = threading.Event()

    def worker(job, emit):
        nonlocal peak, active
        with lock:
            active += 1
            peak = max(peak, active)
        release.wait(timeout=5)
        with lock:
            active -= 1
        emit(status=DONE, percent=100.0, message="완료")

    async def scenario():
        await manager.start()
        created = [manager.create({"url": f"x{i}"}) for i in range(5)]
        drains = [asyncio.create_task(drain(job, manager, timeout=15)) for job in created]
        for job in created:
            manager.submit(job, worker)

        await asyncio.sleep(0.6)  # 앞의 두 개가 자리를 잡을 시간
        running_now = peak
        release.set()
        results = await asyncio.gather(*drains)
        await manager.shutdown()
        return running_now, results

    running_now, results = run(scenario())
    assert running_now <= 2, f"동시에 {running_now}개가 돌았다 (상한 2)"
    assert all(events[-1]["status"] == DONE for events in results)


def test_queued_jobs_report_their_position(manager, override_settings):
    override_settings(max_concurrent_jobs=1)
    release = threading.Event()

    def worker(job, emit):
        release.wait(timeout=5)
        emit(status=DONE, percent=100.0, message="완료")

    async def scenario():
        await manager.start()
        first, second = manager.create({"url": "a"}), manager.create({"url": "b"})
        watcher = asyncio.create_task(drain(second, manager, timeout=15))
        manager.submit(first, worker)
        await asyncio.sleep(0.2)
        manager.submit(second, worker)
        await asyncio.sleep(0.3)
        queued = second.queue_position
        release.set()
        await watcher
        await manager.shutdown()
        return queued

    assert run(scenario()) == 1


def test_too_many_jobs_in_flight_is_rejected(manager, override_settings):
    override_settings(max_jobs_in_flight=3)

    async def scenario():
        await manager.start()
        for _ in range(3):
            manager.create({"url": "x"})
        with pytest.raises(FriendlyError) as caught:
            manager.create({"url": "x"})
        await manager.shutdown()
        return caught.value

    error = run(scenario())
    assert error.status == 429
    assert error.code == "busy"


# ── 구독 ────────────────────────────────────────────────────────────────────


def test_subscriber_immediately_receives_current_state(manager):
    async def scenario():
        await manager.start()
        job = manager.create({"url": "x"})
        manager.publish(job, status=DOWNLOADING, percent=42.0, message="받는 중")
        queue = manager.subscribe(job)
        first = await asyncio.wait_for(queue.get(), timeout=1)
        await manager.shutdown()
        return first

    first = run(scenario())
    assert first["percent"] == 42.0
    assert first["status"] == DOWNLOADING


def test_multiple_subscribers_all_get_events(manager):
    async def scenario():
        await manager.start()
        job = manager.create({"url": "x"})
        queues = [manager.subscribe(job) for _ in range(3)]
        for queue in queues:
            await queue.get()  # 초기 스냅샷 비우기
        manager.publish(job, status=DONE, percent=100.0, message="완료")
        received = [await asyncio.wait_for(q.get(), timeout=1) for q in queues]
        await manager.shutdown()
        return received

    assert all(event["status"] == DONE for event in run(scenario()))


def test_unsubscribe_stops_delivery(manager):
    async def scenario():
        await manager.start()
        job = manager.create({"url": "x"})
        queue = manager.subscribe(job)
        await queue.get()
        manager.unsubscribe(job, queue)
        manager.publish(job, status=DONE, percent=100.0, message="완료")
        await manager.shutdown()
        return queue.qsize()

    assert run(scenario()) == 0


# ── TTL 청소 ────────────────────────────────────────────────────────────────


def test_finished_job_directory_is_removed_after_ttl(manager, override_settings):
    override_settings(job_ttl_seconds=1)

    async def scenario():
        await manager.start()
        job = manager.create({"url": "x"})
        marker = job.directory / "output.mp3"
        marker.write_bytes(b"x" * 100)
        job.status = DONE
        job.finished_at = time.monotonic() - 5  # TTL 이 지난 것처럼
        manager._sweep()
        gone = not marker.exists() and manager.get(job.id) is None
        await manager.shutdown()
        return gone

    assert run(scenario()) is True


def test_fresh_job_survives_the_sweep(manager, override_settings):
    override_settings(job_ttl_seconds=1800)

    async def scenario():
        await manager.start()
        job = manager.create({"url": "x"})
        marker = job.directory / "output.mp3"
        marker.write_bytes(b"x")
        job.status = DONE
        job.finished_at = time.monotonic()
        manager._sweep()
        alive = marker.exists() and manager.get(job.id) is not None
        await manager.shutdown()
        return alive

    assert run(scenario()) is True


def test_shutdown_wipes_every_job_directory(manager):
    async def scenario():
        await manager.start()
        directories = []
        for _ in range(3):
            job = manager.create({"url": "x"})
            (job.directory / "f.bin").write_bytes(b"x")
            directories.append(job.directory)
        await manager.shutdown()
        return directories

    assert all(not Path(d).exists() for d in run(scenario()))


def test_each_job_gets_its_own_directory(manager):
    async def scenario():
        await manager.start()
        first, second = manager.create({"url": "a"}), manager.create({"url": "b"})
        await manager.shutdown()
        return first.directory, second.directory

    first, second = run(scenario())
    assert first != second


# ── 스냅샷 ──────────────────────────────────────────────────────────────────


def test_snapshot_hides_internal_fields(manager):
    async def scenario():
        await manager.start()
        job = manager.create({"url": "https://secret.example/watch?v=x"})
        manager.publish(job, status=DONE, percent=100.0, filepath=Path("/tmp/x.mp3"), filename="x.mp3")
        snapshot = job.snapshot()
        await manager.shutdown()
        return snapshot

    snapshot = run(scenario())
    # 서버 내부 경로나 원본 URL 이 클라이언트로 새어 나가면 안 된다
    assert "filepath" not in snapshot
    assert "/tmp/" not in str(snapshot)
    assert "secret.example" not in str(snapshot)
    assert snapshot["filename"] == "x.mp3"


def test_publish_rejects_unknown_fields(manager):
    """오타난 필드가 조용히 무시되면 진행률이 안 움직여도 원인을 못 찾는다."""

    async def scenario():
        await manager.start()
        job = manager.create({"url": "x"})
        with pytest.raises(AttributeError):
            manager.publish(job, percentt=50.0)
        await manager.shutdown()

    run(scenario())


def test_module_level_manager_exists():
    assert isinstance(jobs.manager, JobManager)
