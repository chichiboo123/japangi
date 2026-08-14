"""테스트용 로컬 미디어 서버.

ffmpeg 로 HLS 화질 사다리를 만들어 로컬 HTTP 로 서빙한다.
유튜브에 나가지 않고도 "여러 화질이 있는 원본" 을 흉내낼 수 있다.

의도적으로 FastAPI/TestClient 를 import 하지 않는다 — 픽스처 서버만 띄우는
쪽(브라우저 e2e)에서 httpx 같은 테스트 전용 의존성을 요구하지 않기 위해서다.
"""
from __future__ import annotations

import subprocess
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT = 9911
MEDIA_DIR = Path(tempfile.mkdtemp(prefix="japangi-media-"))
SECONDS = 6

# 원본이 가진 화질 사다리. 1080p/4K 는 일부러 빼서 SOLD OUT 을 확인한다.
LADDER: tuple[tuple[int, int, int], ...] = (
    (360, 640, 400_000),
    (720, 1280, 1_500_000),
)

# 240p 뿐인 저화질 원본 — 영상 진열대 전체가 품절인 상황을 만든다.
LOW_LADDER: tuple[tuple[int, int, int], ...] = ((240, 426, 200_000),)


def _write_master(name: str, ladder: tuple[tuple[int, int, int], ...]) -> None:
    lines = ["#EXTM3U", "#EXT-X-VERSION:3"]
    for height, width, bitrate in ladder:
        lines.append(
            f"#EXT-X-STREAM-INF:BANDWIDTH={bitrate + 128_000},"
            f'RESOLUTION={width}x{height},CODECS="avc1.4d401f,mp4a.40.2"'
        )
        lines.append(f"v{height}.m3u8")
    (MEDIA_DIR / name).write_text("\n".join(lines) + "\n")


def make_media() -> None:
    """HLS 화질 사다리를 만든다.

    바로 mp4 를 서빙하면 yt-dlp generic 추출기가 (ffprobe 없이는) 해상도·코덱을
    전혀 알아내지 못한다. HLS 마스터 플레이리스트는 RESOLUTION/CODECS/BANDWIDTH 를
    선언하므로, 유튜브처럼 여러 화질이 있는 원본을 실제와 가깝게 흉내낼 수 있다.
    """
    for height, width, bitrate in LADDER + LOW_LADDER:
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", f"testsrc=size={width}x{height}:rate=30:duration={SECONDS}",
                "-f", "lavfi", "-i", f"sine=frequency=440:duration={SECONDS}",
                "-c:v", "libx264", "-preset", "ultrafast", "-profile:v", "main",
                "-pix_fmt", "yuv420p", "-b:v", str(bitrate), "-g", "30",
                "-c:a", "aac", "-b:a", "128k",
                # fMP4 세그먼트를 쓴다. MPEG-TS 로 두면 yt-dlp 가 컨테이너 교정을 위해
                # ffprobe 를 찾는데, ffprobe 가 없는 환경에서는 실패한다.
                "-f", "hls", "-hls_time", "2", "-hls_playlist_type", "vod",
                "-hls_segment_type", "fmp4",
                "-hls_fmp4_init_filename", f"v{height}_init.mp4",
                "-hls_segment_filename", str(MEDIA_DIR / f"v{height}_%03d.m4s"),
                str(MEDIA_DIR / f"v{height}.m3u8"),
            ],
            check=True,
        )

    _write_master("master.m3u8", LADDER)
    # 240p 하나뿐인 원본 — 진열대가 통째로 SOLD OUT 인 경우를 확인하는 데 쓴다.
    _write_master("master_low.m3u8", LOW_LADDER)

    total = sum(p.stat().st_size for p in MEDIA_DIR.glob("*.m4s"))
    print(
        f"  테스트 미디어: HLS {len(LADDER)}단 사다리 "
        f"({', '.join(f'{h}p' for h, _, _ in LADDER)}, {SECONDS}초, H.264+AAC, {total:,} bytes)"
        f" + 240p 저화질본",
        flush=True,
    )


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args, **kwargs) -> None:  # 접속 로그 침묵
        pass

    def handle_one_request(self) -> None:
        # yt-dlp 가 연결을 일찍 끊는 건 정상이라 트레이스백을 찍지 않는다.
        try:
            super().handle_one_request()
        except (ConnectionResetError, BrokenPipeError):
            self.close_connection = True


def serve(port: int = PORT) -> ThreadingHTTPServer:
    """port=0 을 주면 비어 있는 포트를 알아서 잡는다.

    픽스처 서버를 따로 띄워둔 채로 e2e 스크립트를 돌려도 충돌하지 않게 하기 위함이다.
    """
    handler = partial(_QuietHandler, directory=str(MEDIA_DIR))
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd
