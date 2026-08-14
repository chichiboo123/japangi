"""요청/응답 스키마."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ProbeRequest(BaseModel):
    url: str = Field(..., max_length=2048, description="유튜브 또는 인스타그램 링크")


class DownloadRequest(BaseModel):
    url: str = Field(..., max_length=2048)
    type: Literal["audio", "video"]
    format: Literal["mp3", "wav", "mp4", "webm"]
    quality: str = Field(..., max_length=32)
    # MP4 4K 처럼 리먹스로 끝나는 경우에도 굳이 H.264 로 재인코딩할지 여부
    reencode: bool = False


class DownloadResponse(BaseModel):
    job_id: str


class ErrorResponse(BaseModel):
    error: str
    code: str
