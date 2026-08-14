/** 백엔드 API 계약 — backend/app/models.py, formats.py 와 짝을 이룬다. */

export type MediaKind = 'audio' | 'video'
export type ContainerFormat = 'mp3' | 'wav' | 'mp4' | 'webm'

export type SizeSource = 'exact' | 'approx' | 'bitrate' | 'formula' | 'unknown'

export interface ProductOption {
  format: ContainerFormat
  quality: string
  label: string
  estimatedBytes: number | null
  available: boolean
  sizeSource: SizeSource
  /** 영상 전용 */
  needsReencode?: boolean
  sourceHeight?: number
  warning?: string
  note?: string
  badge?: string
}

export interface ProbeResult {
  title: string
  uploader: string
  duration: number | null
  thumbnail: string | null
  source: 'youtube' | 'instagram' | 'test'
  webpageUrl: string
  options: {
    audio: ProductOption[]
    video: ProductOption[]
  }
}

export type JobStatus = 'queued' | 'downloading' | 'processing' | 'done' | 'error'

export interface ProgressEvent {
  status: JobStatus
  percent: number
  message: string
  indeterminate: boolean
  speed?: string
  eta?: number
  queuePosition?: number
  filename?: string
  filesize?: number
  error?: string
  code?: string
}

export interface ApiError {
  error: string
  code: string
}

/** 진열대에 놓인 상품 한 칸 — 같은 포맷의 품질 선택지를 묶는다. */
export interface Product {
  kind: MediaKind
  format: ContainerFormat
  title: string
  options: ProductOption[]
}
