"""링크 자판기 — FastAPI 엔트리포인트."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from . import downloader, formats, naming, probe as probe_module
from .config import settings
from .errors import FriendlyError, humanize
from .jobs import DONE, ERROR, manager
from .models import DownloadRequest, DownloadResponse, ProbeRequest
from .urls import UrlNotAllowed, validate_url

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("japangi")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await manager.start()
    try:
        yield
    finally:
        await manager.shutdown()


app = FastAPI(title="링크 자판기", version="1.0.0", lifespan=lifespan)

# 개발 중에는 Vite dev 서버(5173)에서 접근한다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.exception_handler(FriendlyError)
async def friendly_handler(_: Request, exc: FriendlyError) -> JSONResponse:
    return JSONResponse(status_code=exc.status, content={"error": exc.message, "code": exc.code})


@app.exception_handler(UrlNotAllowed)
async def url_handler(_: Request, exc: UrlNotAllowed) -> JSONResponse:
    return JSONResponse(status_code=400, content={"error": str(exc), "code": "bad_url"})


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "cookies": settings.cookies_enabled,
        "maxDurationSeconds": settings.max_duration_seconds,
        "maxConcurrent": settings.max_concurrent_jobs,
    }


@app.post("/api/probe")
async def api_probe(payload: ProbeRequest) -> dict[str, Any]:
    target = validate_url(payload.url)
    try:
        return await asyncio.to_thread(probe_module.probe, target)
    except FriendlyError:
        raise
    except Exception as exc:  # noqa: BLE001 - 원문은 로그, 사용자에겐 친절한 문구
        raise humanize(exc, context="probe") from exc


@app.post("/api/download", response_model=DownloadResponse)
async def api_download(payload: DownloadRequest) -> DownloadResponse:
    target = validate_url(payload.url)

    if payload.type == "audio" and payload.format not in ("mp3", "wav"):
        raise FriendlyError("음원은 MP3 또는 WAV만 가능해요", code="bad_format")
    if payload.type == "video" and payload.format not in formats.VIDEO_CONTAINERS:
        raise FriendlyError("영상은 MP4 또는 WebM만 가능해요", code="bad_format")

    if payload.type == "audio":
        if payload.format == "mp3" and int_or_none(payload.quality) not in formats.MP3_BITRATES:
            raise FriendlyError("고를 수 없는 음질이에요", code="bad_quality")
        if payload.format == "wav" and payload.quality not in formats.WAV_PROFILES:
            raise FriendlyError("고를 수 없는 음질이에요", code="bad_quality")
    elif payload.quality not in formats.VIDEO_HEIGHTS:
        raise FriendlyError("고를 수 없는 화질이에요", code="bad_quality")

    job = manager.create(
        {
            "url": target.url,
            "type": payload.type,
            "format": payload.format,
            "quality": payload.quality,
            "reencode": payload.reencode,
        }
    )
    manager.submit(job, downloader.run_job)
    return DownloadResponse(job_id=job.id)


def int_or_none(value: str) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@app.get("/api/progress/{job_id}")
async def api_progress(job_id: str, request: Request) -> EventSourceResponse:
    job = manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="그런 작업이 없어요")

    async def stream():
        queue = manager.subscribe(job)
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    # 프록시가 끊지 않도록 하트비트
                    yield {"event": "ping", "data": "{}"}
                    continue
                yield {"event": "progress", "data": _dumps(event)}
                if event.get("status") in (DONE, ERROR):
                    break
        finally:
            manager.unsubscribe(job, queue)

    return EventSourceResponse(stream())


def _dumps(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False)


@app.get("/api/file/{job_id}")
async def api_file(job_id: str) -> FileResponse:
    job = manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="그런 작업이 없어요 (시간이 지나 정리되었을 수 있어요)")
    if job.status != DONE or not job.filepath:
        raise HTTPException(status_code=409, detail="아직 배출 준비가 안 됐어요")

    path = job.filepath
    # 경로 탈출 방지 — 반드시 이 잡의 폴더 안에 있어야 한다.
    try:
        path.resolve().relative_to(job.directory.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="잘못된 파일 경로예요") from None
    if not path.exists():
        raise HTTPException(status_code=410, detail="파일이 이미 정리되었어요. 다시 받아주세요")

    filename = job.filename or path.name
    return FileResponse(
        path,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": naming.content_disposition(filename),
            "Cache-Control": "no-store",
        },
    )


# 프론트 빌드 결과물이 있으면 같이 서빙한다 (Docker 단일 컨테이너 구성).
if settings.static_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(settings.static_dir), html=True), name="static")
