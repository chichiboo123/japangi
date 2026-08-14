"""실제 배출 로직 — yt-dlp 다운로드 + ffmpeg 변환.

진행률은 두 단계로 확실히 구분해서 내보낸다.
  1) downloading : yt-dlp progress_hooks (바이트 기준, 여러 트랙이면 가중 평균)
  2) processing  : 머지/변환. ffmpeg 를 직접 부르는 구간은 실제 %, 그 외는 indeterminate
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Callable

from . import ffmpeg, formats, naming, ytdl
from .config import settings
from .errors import FriendlyError
from .jobs import DONE, DOWNLOADING, PROCESSING, Job
from .sizes import human_bytes

logger = logging.getLogger("japangi.downloader")

Emit = Callable[..., None]


def _format_speed(value: Any) -> str | None:
    if not value:
        return None
    try:
        return f"{human_bytes(float(value))}/s"
    except (TypeError, ValueError):
        return None


class _DownloadProgress:
    """yt-dlp progress_hook 어댑터.

    영상+음성을 따로 받으면 hook 이 파일마다 0→100 을 반복한다. 그대로 흘리면
    진행바가 되감기는 것처럼 보여서, 파일 인덱스를 세어 전체 비율로 환산한다.
    """

    def __init__(self, emit: Emit) -> None:
        self.emit = emit
        self.expected_files = 1
        self.seen: list[str] = []
        self._last_sent = 0.0

    def __call__(self, status: dict[str, Any]) -> None:
        state = status.get("status")
        if state == "error":
            return  # 예외는 yt-dlp 가 따로 던진다

        info = status.get("info_dict") or {}
        requested = info.get("requested_formats")
        if requested:
            self.expected_files = max(self.expected_files, len(requested))

        filename = status.get("filename") or status.get("tmpfilename") or ""
        if filename and filename not in self.seen:
            self.seen.append(filename)
        index = max(0, self.seen.index(filename) if filename in self.seen else 0)

        if state == "finished":
            fraction = 1.0
        else:
            total = status.get("total_bytes") or status.get("total_bytes_estimate")
            downloaded = status.get("downloaded_bytes") or 0
            if total:
                fraction = min(1.0, downloaded / total)
            elif status.get("fragment_count"):
                fraction = min(1.0, (status.get("fragment_index") or 0) / status["fragment_count"])
            else:
                fraction = 0.0

        overall = (index + fraction) / max(1, self.expected_files) * 100

        now = time.monotonic()
        if state != "finished" and now - self._last_sent < 0.25:
            return  # SSE 홍수 방지
        self._last_sent = now

        label = "음성 트랙" if self.expected_files > 1 and index > 0 else "영상"
        message = (
            f"{label} 내려받는 중" if self.expected_files > 1 else "내려받는 중"
        )
        self.emit(
            status=DOWNLOADING,
            percent=min(100.0, overall),
            speed=_format_speed(status.get("speed")),
            eta=status.get("eta"),
            message=message,
            indeterminate=False,
        )


def _enforce_limits(info: dict[str, Any]) -> None:
    """probe 를 거치지 않고 들어온 요청에도 같은 상한을 적용한다."""
    if info.get("is_live"):
        raise FriendlyError("진행 중인 라이브는 받을 수 없어요", code="live")
    duration = info.get("duration")
    if duration and duration > settings.max_duration_seconds:
        raise FriendlyError(
            f"{settings.max_duration_label} 이내 콘텐츠만 받을 수 있어요",
            code="too_long",
        )


def _find_downloaded(job: Job, info: dict[str, Any]) -> Path:
    path = ytdl.resolved_filepath(info)
    if path and Path(path).exists():
        return Path(path)
    # 후처리로 확장자가 바뀐 경우를 대비해 폴더를 뒤진다.
    candidates = [p for p in job.directory.iterdir() if p.is_file() and p.stat().st_size > 0]
    if not candidates:
        raise FriendlyError("파일을 만들지 못했어요. 다른 형식으로 다시 시도해 주세요", code="no_output")
    return max(candidates, key=lambda p: p.stat().st_size)


def _processing_ticker(emit: Emit, message: str) -> Callable[[float], None]:
    last = 0.0

    def on_progress(percent: float) -> None:
        nonlocal last
        now = time.monotonic()
        if percent < 100 and now - last < 0.4:
            return
        last = now
        emit(status=PROCESSING, percent=percent, message=message, indeterminate=False, speed=None, eta=None)

    return on_progress


def run_job(job: Job, emit: Emit) -> None:
    """워커 스레드에서 실행된다. 예외는 JobManager 가 잡아 번역한다."""
    params = job.params
    url: str = params["url"]
    kind: str = params["type"]
    container: str = params["format"]
    quality: str = params["quality"]
    reencode: bool = bool(params.get("reencode"))

    outtmpl = str(job.directory / "source.%(ext)s")
    progress = _DownloadProgress(emit)

    def pp_hook(status: dict[str, Any]) -> None:
        if status.get("status") == "started":
            name = status.get("postprocessor") or ""
            label = "트랙 합치는 중..." if "Merger" in name else "다듬는 중..."
            emit(status=PROCESSING, percent=0.0, message=label, indeterminate=True, speed=None, eta=None)

    # 다운로드 직전에 원본을 한 번 더 확인한다.
    # /api/download 를 직접 때리면 프론트의 SOLD OUT 표시를 건너뛸 수 있으므로,
    # 재생시간 상한과 재고 판정을 서버에서 다시 강제한다.
    emit(status=DOWNLOADING, percent=0.0, message="상품 확인 중...", indeterminate=True)
    preview = ytdl.extract_info(url)
    _enforce_limits(preview)

    if kind == "audio":
        index = formats.index_formats(preview)
        if not index.has_audio:
            raise FriendlyError("이 링크에는 음원 트랙이 없어요", code="no_audio")
        selector = formats.AUDIO_FORMAT_SELECTOR
        merge_format = None
    else:
        height = formats.VIDEO_HEIGHTS[quality]
        index = formats.index_formats(preview)
        option = formats.negotiate_video(index, container, height)
        if not option.available:
            raise FriendlyError(
                f"{container.upper()} {quality}는 품절이에요. {option.note or '원본에 없는 화질입니다'}",
                code="sold_out",
            )
        # 협상 결과가 "재인코딩 필요" 면 사용자가 토글을 껐어도 어쩔 수 없다.
        # (예: H.264 원본을 WebM 으로 — 리먹스로는 불가능)
        reencode = reencode or option.needs_reencode
        selector = formats.video_format_selector(container, height)
        merge_format = container

    info = ytdl.download(
        url,
        format_selector=selector,
        outtmpl=outtmpl,
        progress_hook=progress,
        postprocessor_hook=pp_hook,
        merge_output_format=merge_format,
    )

    source_path = _find_downloaded(job, info)
    duration = info.get("duration")
    title = info.get("title") or "제목없음"

    if kind == "audio":
        final_path = _convert_audio(job, emit, source_path, container, quality, duration)
    else:
        final_path = _finalize_video(
            job, emit, source_path, container, quality, duration, reencode=reencode
        )

    filename = naming.build_filename(title, quality, final_path.suffix.lstrip("."))
    size = final_path.stat().st_size

    emit(
        status=DONE,
        percent=100.0,
        message="배출구에서 가져가세요!",
        indeterminate=False,
        filepath=final_path,
        filename=filename,
        filesize=size,
        speed=None,
        eta=None,
    )
    logger.info("작업 %s 완료 — %s (%s)", job.id, filename, human_bytes(size))


def _convert_audio(
    job: Job,
    emit: Emit,
    source: Path,
    container: str,
    quality: str,
    duration: float | None,
) -> Path:
    if container == "mp3":
        target = job.directory / "output.mp3"
        on_progress = _processing_ticker(emit, f"MP3 {quality}kbps로 바꾸는 중...")
        emit(status=PROCESSING, percent=0.0, message=f"MP3 {quality}kbps로 바꾸는 중...", indeterminate=False)
        return ffmpeg.to_mp3(
            source, target, bitrate_kbps=int(quality), duration=duration, on_progress=on_progress
        )

    if container == "wav":
        rate, depth = formats.WAV_PROFILES.get(quality, (44100, 16))
        target = job.directory / "output.wav"
        label = f"WAV {rate // 1000}kHz {depth}bit로 바꾸는 중..."
        emit(status=PROCESSING, percent=0.0, message=label, indeterminate=False)
        return ffmpeg.to_wav(
            source,
            target,
            sample_rate=rate,
            bit_depth=depth,
            duration=duration,
            on_progress=_processing_ticker(emit, label),
        )

    raise FriendlyError("지원하지 않는 음원 형식이에요", code="bad_format")


def _finalize_video(
    job: Job,
    emit: Emit,
    source: Path,
    container: str,
    quality: str,
    duration: float | None,
    *,
    reencode: bool,
) -> Path:
    suffix = source.suffix.lower().lstrip(".")

    if reencode:
        target = job.directory / f"reencoded.{container}"
        label = "H.264로 재인코딩하는 중 (수 분 걸려요)" if container == "mp4" else "VP9로 재인코딩하는 중 (수 분 걸려요)"
        emit(status=PROCESSING, percent=0.0, message=label, indeterminate=False)
        on_progress = _processing_ticker(emit, label)
        if container == "mp4":
            return ffmpeg.reencode_h264(source, target, duration=duration, on_progress=on_progress)
        return ffmpeg.reencode_vp9(source, target, duration=duration, on_progress=on_progress)

    if suffix == container:
        return source  # yt-dlp 가 이미 원하는 컨테이너로 머지해줬다

    # 컨테이너만 다르면 리먹스 — 화질 손실 없고 거의 즉시 끝난다.
    target = job.directory / f"remuxed.{container}"
    label = f"{container.upper()} 컨테이너로 바꾸는 중..."
    emit(status=PROCESSING, percent=0.0, message=label, indeterminate=False)
    try:
        return ffmpeg.remux(source, target, duration=duration, on_progress=_processing_ticker(emit, label))
    except ffmpeg.FFmpegError:
        # 코덱이 컨테이너에 안 맞으면 리먹스가 실패한다 → 재인코딩으로 넘어간다.
        logger.info("리먹스 실패 → 재인코딩으로 전환 (job %s)", job.id)
        return _finalize_video(job, emit, source, container, quality, duration, reencode=True)


__all__ = ["run_job"]
