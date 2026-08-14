"""공용 픽스처."""
from __future__ import annotations

from typing import Any, Callable

import pytest

from app.config import settings as app_settings


@pytest.fixture
def override_settings() -> Callable[..., None]:
    """frozen dataclass 인 Settings 를 테스트 동안만 바꾼다.

    운영 코드에서 설정이 실수로 바뀌는 걸 막으려고 frozen 을 유지하고 있어서,
    테스트에서는 object.__setattr__ 로 우회한 뒤 끝나면 되돌린다.
    """
    original: dict[str, Any] = {}

    def apply(**changes: Any) -> None:
        for key, value in changes.items():
            if not hasattr(app_settings, key):
                raise AttributeError(f"Settings 에 없는 항목입니다: {key}")
            original.setdefault(key, getattr(app_settings, key))
            object.__setattr__(app_settings, key, value)

    yield apply

    for key, value in original.items():
        object.__setattr__(app_settings, key, value)
