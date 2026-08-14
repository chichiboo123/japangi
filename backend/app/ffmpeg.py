"""ffmpeg 직접 호출 — 변환 단계의 진행률까지 뽑아내기 위해서.

yt-dlp 의 FFmpegExtractAudio 후처리기는 ffprobe 를 요구하고 샘플레이트/비트깊이를
지정할 수 없다. WAV 48kHz/24bit 같은 옵션을 정확히 만들려면 직접 부르는 편이 낫다.
덤으로 `-progress pipe:1` 을 파싱해서 변환 진행률을 실시간으로 얻는다.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Callable

logger = logging.getLogger("japangi.ffmpeg")

ProgressCb = Callable[[float], None]  # 0~100


class FFmpegError(RuntimeError):
    pass


def ffmpeg_path() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise FFmpegError("ffmpeg not found on PATH")
    return path


def _run(
    args: list[str],
    duration: float | None,
    on_progress: ProgressCb | None,
    *,
    failure_is_expected: bool = False,
) -> None:
    """ffmpeg 를 돌리면서 -progress 출력을 파싱한다."""
    cmd = [ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-nostdin", "-y", *args]
    cmd += ["-progress", "pipe:1", "-stats_period", "0.5"]
    logger.debug("ffmpeg: %s", " ".join(cmd))

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    try:
        for line in process.stdout:
            line = line.strip()
            if not line or "=" not in line:
                continue
            key, _, value = line.partition("=")
            if key == "out_time_ms" and duration and on_progress:
                try:
                    seconds = int(value) / 1_000_000
                except ValueError:
                    continue
                on_progress(max(0.0, min(100.0, seconds / duration * 100)))
            elif key == "progress" and value == "end" and on_progress:
                on_progress(100.0)
    finally:
        process.stdout.close()
        stderr = process.stderr.read() if process.stderr else ""
        if process.stderr:
            process.stderr.close()
        code = process.wait()

    if code != 0:
        # 리먹스 시도처럼 "실패해도 되는" 호출은 경고로 남긴다 (재인코딩으로 넘어간다).
        log = logger.info if failure_is_expected else logger.error
        log("ffmpeg exited %s: %s", code, stderr[-2000:].strip())
        raise FFmpegError(f"ffmpeg failed (exit {code})")


# ── 음원 변환 ────────────────────────────────────────────────────────────────


def to_mp3(
    source: Path,
    target: Path,
    *,
    bitrate_kbps: int,
    duration: float | None = None,
    on_progress: ProgressCb | None = None,
) -> Path:
    _run(
        [
            "-i", str(source),
            "-vn",
            "-c:a", "libmp3lame",
            "-b:a", f"{bitrate_kbps}k",
            "-ar", "44100",
            "-ac", "2",
            str(target),
        ],
        duration,
        on_progress,
    )
    return target


def to_wav(
    source: Path,
    target: Path,
    *,
    sample_rate: int,
    bit_depth: int,
    duration: float | None = None,
    on_progress: ProgressCb | None = None,
) -> Path:
    codec = {16: "pcm_s16le", 24: "pcm_s24le", 32: "pcm_s32le"}.get(bit_depth, "pcm_s16le")
    _run(
        [
            "-i", str(source),
            "-vn",
            "-c:a", codec,
            "-ar", str(sample_rate),
            "-ac", "2",
            str(target),
        ],
        duration,
        on_progress,
    )
    return target


# ── 영상 변환 ────────────────────────────────────────────────────────────────


def remux(
    source: Path,
    target: Path,
    *,
    duration: float | None = None,
    on_progress: ProgressCb | None = None,
) -> Path:
    """컨테이너만 바꾼다. 재인코딩 없음 → 화질 손실 0, 거의 즉시 끝난다.

    코덱이 그 컨테이너에 못 들어가면 실패한다 (예: H.264 → WebM). 호출부가
    재인코딩으로 넘어갈 수 있도록 실패를 '예상된 것'으로 표시한다.
    """
    extra = ["-movflags", "+faststart"] if target.suffix.lower() == ".mp4" else []
    _run(
        ["-i", str(source), "-c", "copy", *extra, str(target)],
        duration,
        on_progress,
        failure_is_expected=True,
    )
    return target


def reencode_h264(
    source: Path,
    target: Path,
    *,
    duration: float | None = None,
    on_progress: ProgressCb | None = None,
) -> Path:
    _run(
        [
            "-i", str(source),
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            str(target),
        ],
        duration,
        on_progress,
    )
    return target


def reencode_vp9(
    source: Path,
    target: Path,
    *,
    duration: float | None = None,
    on_progress: ProgressCb | None = None,
) -> Path:
    _run(
        [
            "-i", str(source),
            "-c:v", "libvpx-vp9",
            "-crf", "32",
            "-b:v", "0",
            "-row-mt", "1",
            "-deadline", "good",
            "-cpu-used", "4",
            "-c:a", "libopus",
            "-b:a", "160k",
            str(target),
        ],
        duration,
        on_progress,
    )
    return target
