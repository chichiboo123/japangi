"""브라우저 e2e 용 로컬 미디어 서버.

tests/e2e_local.py 와 같은 HLS 사다리를 만들어 고정 포트에 올려두고 계속 떠 있는다.

    python3 -m tests.fixture_server
"""
from __future__ import annotations

import signal
import sys

from tests.e2e_local import MEDIA_DIR, PORT, make_media, serve


def main() -> int:
    make_media()
    serve()
    print(f"  픽스처 서버: http://localhost:{PORT}/master.m3u8  ({MEDIA_DIR})", flush=True)
    signal.pause()
    return 0


if __name__ == "__main__":
    sys.exit(main())
