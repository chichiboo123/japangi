# ── 1단계: 프론트 빌드 ───────────────────────────────────────────────────────
# glibc(Debian) 기반을 쓴다. alpine(musl) 로 하면 package-lock 에 박혀 있는
# @rollup/rollup-linux-x64-gnu 대신 -musl 빌드가 필요한데 락파일에 없어서 빌드가 깨진다.
FROM node:22-slim AS frontend

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
# --omit=optional 을 쓰면 rollup 의 플랫폼별 네이티브 바이너리가 빠져 빌드가 실패한다.
RUN npm ci

COPY frontend/ ./
RUN npm run build


# ── 2단계: 실행 이미지 ───────────────────────────────────────────────────────
FROM python:3.12-slim

# ffmpeg + ffprobe. 둘 다 필요하다 — yt-dlp 의 컨테이너 교정 단계가 ffprobe 를 쓴다.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY --from=frontend /build/dist ./frontend_dist

# 루트로 돌리지 않는다.
RUN useradd --create-home --shell /usr/sbin/nologin japangi \
    && mkdir -p /data \
    && chown -R japangi:japangi /app /data
USER japangi

ENV WORK_DIR=/data \
    STATIC_DIR=/app/frontend_dist \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
