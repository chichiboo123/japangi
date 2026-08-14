"""로컬 e2e 점검 스크립트.

유튜브에 나갈 수 없는 환경(CI/샌드박스)에서도 파이프라인 전체를 실제로 돌려보기 위한 것.
ffmpeg 로 만든 진짜 미디어 파일을 로컬 HTTP 서버에 올려두고,
probe → download → SSE 진행률 → 파일 수령까지 전부 실행한다.

    python3 -m tests.e2e_local
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time

os.environ.setdefault("EXTRA_ALLOWED_HOSTS", "localhost")
os.environ.setdefault("WORK_DIR", tempfile.mkdtemp(prefix="japangi-e2e-"))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from tests.media_fixture import MEDIA_DIR, SECONDS, make_media, serve  # noqa: E402

OK = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"

failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    print(f"  {OK if condition else FAIL}  {label}{(' — ' + detail) if detail else ''}")
    if not condition:
        failures.append(label)


def run_download(client: TestClient, url: str, payload: dict) -> dict:
    """다운로드 요청 → SSE 로 진행률 수집 → 파일 받기."""
    response = client.post("/api/download", json={"url": url, **payload})
    if response.status_code != 200:
        return {"error": response.json(), "events": []}
    job_id = response.json()["job_id"]

    events: list[dict] = []
    with client.stream("GET", f"/api/progress/{job_id}") as stream:
        for line in stream.iter_lines():
            if not line.startswith("data:"):
                continue
            body = line[5:].strip()
            if not body or body == "{}":
                continue
            event = json.loads(body)
            events.append(event)
            if event.get("status") in ("done", "error"):
                break

    result = {"job_id": job_id, "events": events, "final": events[-1] if events else {}}
    if result["final"].get("status") == "done":
        file_response = client.get(f"/api/file/{job_id}")
        result["http_status"] = file_response.status_code
        result["content"] = file_response.content
        result["disposition"] = file_response.headers.get("content-disposition", "")
    return result


def phases(events: list[dict]) -> list[str]:
    seen: list[str] = []
    for event in events:
        status = event.get("status")
        if status and (not seen or seen[-1] != status):
            seen.append(status)
    return seen


def main() -> int:
    make_media()
    httpd = serve(port=0)  # 이미 떠 있는 픽스처 서버와 부딪히지 않게 빈 포트를 쓴다
    port = httpd.server_address[1]
    url = f"http://localhost:{port}/master.m3u8"

    try:
        with TestClient(app) as client:
            print("\n[1] /api/health")
            health = client.get("/api/health")
            check("헬스체크 200", health.status_code == 200, str(health.json()))

            print("\n[2] /api/probe — 화이트리스트 거부")
            for bad, label in [
                ("https://evil.com/x", "미허용 도메인"),
                ("http://169.254.169.254/latest/", "메타데이터 IP"),
                ("file:///etc/passwd", "file 스킴"),
            ]:
                response = client.post("/api/probe", json={"url": bad})
                check(
                    f"{label} 400 + 친절한 메시지",
                    response.status_code == 400 and "error" in response.json(),
                    response.json().get("error", ""),
                )

            print("\n[3] /api/probe — 실제 미디어")
            response = client.post("/api/probe", json={"url": url})
            check("probe 200", response.status_code == 200, response.text[:200])
            if response.status_code != 200:
                return 1
            info = response.json()
            check("재생시간 추출", abs((info.get("duration") or 0) - SECONDS) <= 1, f"{info.get('duration')}초")
            audio = {(o["format"], o["quality"]): o for o in info["options"]["audio"]}
            video = {(o["format"], o["quality"]): o for o in info["options"]["video"]}
            check("MP3 4종 + WAV 2종", len(audio) == 6, ", ".join(f"{k[0]}{k[1]}" for k in audio))
            check("영상 8종 (mp4/webm × 4화질)", len(video) == 8)
            check(
                "MP3 320 예상용량 = 공식값",
                audio[("mp3", "320")]["estimatedBytes"] == int(320 * 1000 * SECONDS / 8),
                f"{audio[('mp3', '320')]['estimatedBytes']:,} B",
            )
            check(
                "WAV 48k/24bit 예상용량 = 공식값",
                audio[("wav", "48000-24")]["estimatedBytes"] == int(48000 * 24 * 2 * SECONDS / 8) + 44,
                f"{audio[('wav', '48000-24')]['estimatedBytes']:,} B",
            )
            check("WAV 대용량 라벨", audio[("wav", "48000-24")].get("badge") == "대용량")
            check("720p 이하 판매중", video[("mp4", "720p")]["available"])
            check(
                "1080p SOLD OUT (원본 720p)",
                video[("mp4", "1080p")]["available"] is False,
                video[("mp4", "1080p")].get("note", ""),
            )
            check("4K SOLD OUT", video[("mp4", "2160p")]["available"] is False)
            check("MP4 720p 리먹스 (재인코딩 불필요)", video[("mp4", "720p")]["needsReencode"] is False)
            check(
                "WebM 720p 는 H.264 원본이라 재인코딩 필요",
                video[("webm", "720p")]["needsReencode"] is True,
                video[("webm", "720p")].get("warning", ""),
            )

            print("\n[4] /api/download — MP3 320kbps")
            result = run_download(client, url, {"type": "audio", "format": "mp3", "quality": "320"})
            final = result["final"]
            check("완료 상태", final.get("status") == "done", json.dumps(final, ensure_ascii=False)[:200])
            check(
                "다운로드/변환 단계가 분리되어 보임",
                "downloading" in phases(result["events"]) and "processing" in phases(result["events"]),
                " → ".join(phases(result["events"])),
            )
            check("파일 전송 200", result.get("http_status") == 200)
            check("MP3 시그니처", result.get("content", b"")[:3] in (b"ID3", b"\xff\xfb"), str(result.get("content", b"")[:4]))
            expected = int(320 * 1000 * SECONDS / 8)
            actual = len(result.get("content", b""))
            drift = abs(actual - expected) / expected * 100
            check(f"실제 용량이 추정치의 ±10% 이내", drift < 10, f"추정 {expected:,} / 실제 {actual:,} ({drift:.1f}% 차이)")

            print("\n[5] /api/download — WAV 48kHz 24bit")
            result = run_download(client, url, {"type": "audio", "format": "wav", "quality": "48000-24"})
            check("완료 상태", result["final"].get("status") == "done", json.dumps(result["final"], ensure_ascii=False)[:200])
            content = result.get("content", b"")
            check("WAV 시그니처", content[:4] == b"RIFF" and content[8:12] == b"WAVE")
            expected = int(48000 * 24 * 2 * SECONDS / 8) + 44
            drift = abs(len(content) - expected) / expected * 100
            check("실제 용량이 추정치의 ±5% 이내", drift < 5, f"추정 {expected:,} / 실제 {len(content):,} ({drift:.1f}%)")

            print("\n[6] /api/download — MP4 720p (리먹스 경로)")
            result = run_download(client, url, {"type": "video", "format": "mp4", "quality": "720p"})
            check("완료 상태", result["final"].get("status") == "done", json.dumps(result["final"], ensure_ascii=False)[:200])
            check("MP4 시그니처(ftyp)", result.get("content", b"")[4:8] == b"ftyp")
            check("한글 파일명 헤더(RFC 5987)", "filename*=UTF-8''" in result.get("disposition", ""), result.get("disposition", "")[:120])

            print("\n[7] /api/download — WebM 720p (재인코딩 경로)")
            result = run_download(client, url, {"type": "video", "format": "webm", "quality": "720p"})
            check("완료 상태", result["final"].get("status") == "done", json.dumps(result["final"], ensure_ascii=False)[:200])
            check("WebM 시그니처(EBML)", result.get("content", b"")[:4] == b"\x1a\x45\xdf\xa3")
            processing = [e for e in result["events"] if e.get("status") == "processing"]
            check(
                "재인코딩 진행률이 실제로 움직임",
                len({round(e.get("percent", 0)) for e in processing}) > 2,
                f"{len(processing)}개 이벤트, 퍼센트 {sorted({round(e.get('percent', 0)) for e in processing})[:8]}",
            )

            print("\n[8] SOLD OUT 인 조합을 API 로 직접 요청 (프론트 우회)")
            result = run_download(client, url, {"type": "video", "format": "mp4", "quality": "2160p"})
            final = result["final"]
            message = json.dumps(final, ensure_ascii=False)
            # 원본이 720p 라 4K 는 만들 수 없다. 720p 를 4K 라고 속여 내보내면 안 된다.
            check("품절 요청은 error 로 거부", final.get("status") == "error", message[:200])
            check("품절 코드", final.get("code") == "sold_out", str(final.get("code")))
            check("Traceback 노출 없음", "Traceback" not in message and "yt_dlp" not in message)
            check("2160p 라고 이름 붙은 파일이 나오지 않음", "2160p" not in str(final.get("filename")))

            print("\n[9] 재인코딩 토글 (리먹스로 충분한데도 사용자가 켠 경우)")
            remuxed = run_download(client, url, {"type": "video", "format": "mp4", "quality": "720p"})
            reencoded = run_download(
                client, url, {"type": "video", "format": "mp4", "quality": "720p", "reencode": True}
            )
            check("재인코딩본도 완료", reencoded["final"].get("status") == "done", json.dumps(reencoded["final"], ensure_ascii=False)[:160])
            check("MP4 시그니처 유지", reencoded.get("content", b"")[4:8] == b"ftyp")
            check(
                "리먹스본과 실제로 다른 파일 (재인코딩이 일어남)",
                len(reencoded.get("content", b"")) != len(remuxed.get("content", b"")),
                f"리먹스 {len(remuxed.get('content', b'')):,} vs 재인코딩 {len(reencoded.get('content', b'')):,}",
            )
            messages = " ".join(e.get("message", "") for e in reencoded["events"])
            check("재인코딩 안내 문구 노출", "재인코딩" in messages, messages[:80])

            print("\n[10] 재생시간 상한 (프론트 우회)")
            with_limit = client.post("/api/download", json={"url": url, "type": "audio", "format": "mp3", "quality": "128"})
            job_id = with_limit.json()["job_id"]
            check("정상 길이는 통과", with_limit.status_code == 200, str(job_id)[:12])
            # 상한을 1초로 낮추면 같은 요청이 거부되어야 한다
            from app.config import settings as live_settings

            object.__setattr__(live_settings, "max_duration_seconds", 1)
            try:
                blocked = run_download(client, url, {"type": "audio", "format": "mp3", "quality": "128"})
                check(
                    "상한 초과는 거부",
                    blocked["final"].get("code") == "too_long",
                    json.dumps(blocked["final"], ensure_ascii=False)[:160],
                )
            finally:
                object.__setattr__(live_settings, "max_duration_seconds", 7200)

            print("\n[11] 잘못된 입력 방어")
            response = client.post("/api/download", json={"url": url, "type": "audio", "format": "mp3", "quality": "9999"})
            check("허용되지 않은 품질 거부", response.status_code == 400, response.text[:120])
            response = client.get("/api/file/deadbeef")
            check("없는 job_id 404", response.status_code == 404)

    finally:
        httpd.shutdown()

    print("\n" + "=" * 60)
    if failures:
        print(f"{FAIL}  {len(failures)}개 실패: {', '.join(failures)}")
        return 1
    print(f"{OK}  전체 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
