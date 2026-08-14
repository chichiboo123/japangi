# 링크 자판기 (Link Vending Machine)

유튜브·인스타그램 링크를 넣으면 원하는 형식과 품질로 꺼내주는 웹앱.

동전을 넣듯 링크를 투입하고 → 진열대에서 상품(포맷)을 고르고 → 배출구에서 파일을 받아갑니다.
**모든 선택지에 예상 용량이 가격표처럼 붙는 것**이 이 앱의 핵심입니다.

| 구분 | 포맷 | 품질 |
|---|---|---|
| 음원 | MP3 | 128 / 192 / 256 / 320 kbps |
| 음원 | WAV | 44.1kHz·16bit / 48kHz·24bit |
| 영상 | MP4 | 360p / 720p / 1080p / 4K(2160p) |
| 영상 | WebM | 360p / 720p / 1080p / 4K(2160p) |

> 본인이 권리를 가진 콘텐츠, 저작권자가 허락한 콘텐츠, 또는 법이 허용하는 범위(수업 목적 이용 등) 내에서만 사용해 주세요.

---

## 빠른 시작 — 도커 (권장)

```bash
docker compose up --build
```

브라우저에서 <http://localhost:8000> 을 엽니다. 끝입니다.

ffmpeg 는 이미지 안에 들어 있으므로 따로 설치할 필요가 없습니다.

### 도커 없이 실행하기

**필요한 것**: Python 3.11+, Node.js 20+, **ffmpeg** (ffprobe 포함)

```bash
# ffmpeg 설치
brew install ffmpeg                      # macOS
sudo apt install ffmpeg                  # Ubuntu / Debian
winget install Gyan.FFmpeg               # Windows

# 백엔드
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 프론트 (새 터미널에서)
cd frontend
npm install
npm run dev
```

개발 중에는 <http://localhost:5173> 으로 접속합니다 (`/api` 요청은 8000 으로 자동 전달).

> **ffprobe 도 반드시 필요합니다.** ffmpeg 만 있고 ffprobe 가 없으면 yt-dlp 의 컨테이너
> 교정 단계가 실패합니다. 대부분의 배포판은 두 실행 파일을 함께 설치하지만,
> 일부 최소 설치 패키지는 그렇지 않으니 `ffprobe -version` 으로 확인해 주세요.

---

## yt-dlp 업데이트 (중요)

유튜브·인스타그램은 수시로 내부 구조를 바꿉니다. 어제까지 되던 게 오늘 안 될 수 있고,
**대부분의 경우 yt-dlp 를 최신으로 올리면 해결됩니다.**

```bash
pip install -U yt-dlp          # 직접 실행할 때

docker compose build --no-cache && docker compose up -d    # 도커일 때
```

증상이 이럴 때 의심해 보세요.

- 멀쩡한 링크인데 "받을 수 있는 영상이나 음원을 찾지 못했어요"
- 어제까지 되던 화질이 갑자기 전부 SOLD OUT
- 다운로드가 시작되자마자 실패

---

## 설정 (환경변수)

| 변수 | 기본값 | 설명 |
|---|---|---|
| `MAX_CONCURRENT_JOBS` | `3` | 동시에 처리할 다운로드 수. 초과분은 대기 큐로 |
| `MAX_DURATION_SECONDS` | `7200` | 이보다 긴 콘텐츠는 거부 (디스크·메모리 보호) |
| `JOB_TTL_SECONDS` | `1800` | 완성된 파일을 지우기까지의 시간 |
| `MAX_JOBS_IN_FLIGHT` | `24` | 대기 포함 전체 작업 상한 |
| `WORK_DIR` | 시스템 임시 폴더 | 작업 파일을 두는 곳 |
| `STATIC_DIR` | `frontend_dist` | 프론트 빌드 결과물 경로 |
| `COOKIES_FILE` | (없음) | 쿠키 파일 경로. 아래 참고 |
| `EXTRA_ALLOWED_HOSTS` | (없음) | **테스트 전용.** 운영에서는 절대 설정하지 마세요 |

### 인스타그램 비공개 게시물 — 쿠키

인스타그램은 **공개 게시물과 릴스만 안정적으로** 받을 수 있습니다. 비공개 계정이나
스토리는 로그인이 필요하고, 이 경우 앱은 "이 링크는 자판기가 받을 수 없어요"라고
안내합니다. 이는 오류가 아니라 정상 동작입니다.

굳이 필요하다면 Netscape 형식 `cookies.txt` 를 준비해 경로를 지정할 수 있습니다.

```bash
COOKIES_FILE=/path/to/cookies.txt uvicorn app.main:app
```

도커에서는 `docker-compose.yml` 의 해당 주석 두 줄을 풀어 주세요.

> 쿠키는 로그인 세션 그 자체입니다. 저장소에 커밋하거나 공용 서버에 두지 마세요.
> `.gitignore` 에 `cookies.txt` 를 이미 넣어 두었습니다.

---

## 배포

### 1순위: 개인 PC에서 로컬 실행

가장 안정적이고 안전합니다. `docker compose up` 한 줄이면 됩니다.
링크도 파일도 내 컴퓨터 밖으로 나가지 않습니다.

### 2순위: Fly.io / Railway 같은 곳에 도커 이미지로

태그를 붙여 푸시하면 GitHub Actions 가 이미지를 GHCR 로 올립니다.

```bash
git tag v1.0.0 && git push origin v1.0.0
# → ghcr.io/<계정>/<저장소>:1.0.0
```

**다만 공용 서버 IP 는 봇으로 감지되어 차단될 수 있습니다.** 클라우드 사업자의
IP 대역은 이미 널리 알려져 있어서, 유튜브가 "Sign in to confirm you're not a bot"
같은 응답을 돌려주는 일이 흔합니다. 앱은 이 상황을 감지해
"유튜브가 이 서버를 봇으로 보고 있어요" 라고 안내하지만, 근본적인 해결책은 아닙니다.
**되도록 개인 PC에서 쓰시길 권합니다.**

### 정적 호스팅에는 올릴 수 없습니다

이 앱은 서버에서 `yt-dlp` 와 `ffmpeg` 를 직접 실행합니다.
Cloudflare Pages, GitHub Pages, Netlify 같은 정적 호스팅에는 배포할 수 없습니다.

---

## 구조

```
backend/app/
  main.py         FastAPI 엔트리포인트, 라우트
  urls.py         URL 화이트리스트 (SSRF 방지)
  probe.py        링크 하나 → 제목·썸네일·포맷별 예상 용량
  sizes.py        예상 용량 계산 (순수 함수만, 단위 테스트 대상)
  formats.py      진열대 구성, 재고 판정, 코덱 협상
  jobs.py         작업 큐, 동시 실행 제한, 진행률 브로드캐스트, TTL 청소
  downloader.py   yt-dlp 다운로드 + ffmpeg 변환
  ffmpeg.py       ffmpeg 직접 호출 (변환 진행률 파싱용)
  naming.py       파일명 정규화, RFC 5987 헤더
  errors.py       yt-dlp 에러 → 사용자 친화 문구

frontend/src/
  useVendingMachine.ts   상태기계 (idle → ready → dispensing → dispensed)
  api.ts                 probe / download / SSE 구독
  format.ts              용량 표시 규칙 (1024 기준)
  components/            자판기 UI (투입구·표시창·진열대·배출구)
```

### API

| 엔드포인트 | 설명 |
|---|---|
| `POST /api/probe` | 링크 확인 → 제목·재생시간·포맷별 예상 용량 |
| `POST /api/download` | 다운로드 시작 → `job_id` 발급 |
| `GET /api/progress/{job_id}` | 진행률 (SSE) |
| `GET /api/file/{job_id}` | 완성 파일 |
| `GET /api/health` | 상태 확인 |

---

## 예상 용량은 어떻게 계산하나

**영상** — `filesize`(정확값) → `filesize_approx` → `tbr × 재생시간 ÷ 8` 순으로 시도합니다.
영상 트랙과 음성 트랙을 따로 받아 합치는 경우에는 **두 용량을 더합니다.**
(이걸 빠뜨리면 1080p 기준 3~5MB 를 과소 계산하게 됩니다.)

**음원** — 인코딩 전이라 실측값이 없으므로 공식으로 계산합니다.

- MP3(CBR) = `비트레이트(kbps) × 1000 × 초 ÷ 8`
- WAV(무압축 PCM) = `샘플레이트 × 비트깊이 × 채널수 × 초 ÷ 8`

WAV 는 44.1kHz/16bit 기준 **분당 약 10.1MB**, 48kHz/24bit 기준 **분당 약 16.5MB** 입니다.
용량이 커서 UI 에 "대용량" 라벨을 붙여 둡니다.

표시는 1024 기준(KB/MB/GB), 소수점 한 자리입니다. 추정값에는 `약` 이 붙고,
실제와 5~10% 차이날 수 있습니다.

---

## 코덱 협상 — 4K MP4 를 고르면 생기는 일

유튜브는 **1080p 를 넘는 해상도에 H.264 를 거의 제공하지 않습니다.** VP9 나 AV1 뿐입니다.
그래서 MP4 4K 를 고르면 둘 중 하나를 해야 합니다.

1. **리먹스** — 컨테이너만 MP4 로 바꿉니다. 즉시 끝나고 화질 손실이 없습니다. (기본값)
2. **재인코딩** — H.264 로 다시 인코딩합니다. 호환성은 좋아지지만 수 분 걸립니다.

**항상 리먹스를 먼저 시도합니다.** 리먹스로 불가능한 조합(예: H.264 원본 → WebM)일 때만
재인코딩으로 넘어가고, 그런 상황은 미리 진열대에 경고로 표시합니다.
사용자가 원하면 "H.264로 재인코딩하기" 토글로 직접 고를 수도 있습니다.

원본에 없는 화질은 **미리 SOLD OUT 으로 표시**하고, API 를 직접 호출해 우회하려 해도
서버에서 다시 막습니다. 고르게 해놓고 나중에 실패하는 게 가장 나쁘기 때문입니다.

---

## 안전장치

- URL 화이트리스트 (youtube.com / youtu.be / instagram.com 등) — SSRF 방지
- IP 리터럴·비표준 포트·`file:` 등 비 HTTP 스킴 거부
- 재생시간 상한 (기본 2시간) — `/api/probe` 와 `/api/download` 양쪽에서 강제
- 동시 작업 수 제한 + 대기 큐
- 작업별 임시 폴더 → 30분 TTL 자동 삭제, 서버 종료 시 전부 정리
- 파일명 sanitize (경로 탈출·OS 금지문자·예약어)
- 파일 전송 시 잡 폴더 밖 경로 차단
- 모든 에러는 사용자 친화 문구로 변환, 원문은 서버 로그에만

---

## 테스트

```bash
# 단위 테스트 (153개)
cd backend && python -m pytest

# 파이프라인 e2e — 유튜브에 나가지 않고 로컬 미디어로 전 과정 실행
python -m tests.e2e_local

# 브라우저 e2e (백엔드·픽스처·Vite 를 먼저 띄운 뒤)
cd frontend
node tests/browser.mjs      # 전체 흐름
node tests/browser-ui.mjs   # UI·접근성
```

e2e 는 ffmpeg 로 만든 HLS 화질 사다리를 로컬에 띄워 원본처럼 씁니다.
유튜브에 접속하지 않으므로 CI 나 폐쇄망에서도 그대로 돌아갑니다.

---

<p align="center">
  <a href="https://litt.ly/chichiboo">Created by. 교육뮤지컬 꿈꾸는 치수쌤</a>
</p>
