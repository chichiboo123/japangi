import type { ApiError, ContainerFormat, MediaKind, ProbeResult, ProgressEvent } from './types'

export class VendingError extends Error {
  code: string
  constructor(message: string, code = 'unknown') {
    super(message)
    this.code = code
  }
}

async function parseError(response: Response): Promise<VendingError> {
  try {
    const body = (await response.json()) as ApiError & { detail?: string }
    return new VendingError(body.error ?? body.detail ?? '알 수 없는 오류예요', body.code ?? 'unknown')
  } catch {
    return new VendingError('자판기가 응답하지 않아요', 'network')
  }
}

export async function probe(url: string, signal?: AbortSignal): Promise<ProbeResult> {
  const response = await fetch('/api/probe', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
    signal,
  })
  if (!response.ok) throw await parseError(response)
  return (await response.json()) as ProbeResult
}

export interface DownloadRequest {
  url: string
  type: MediaKind
  format: ContainerFormat
  quality: string
  reencode?: boolean
}

export async function startDownload(request: DownloadRequest): Promise<string> {
  const response = await fetch('/api/download', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
  if (!response.ok) throw await parseError(response)
  const body = (await response.json()) as { job_id: string }
  return body.job_id
}

/**
 * 진행률 SSE 구독. 정리 함수를 돌려준다.
 * done/error 가 오면 스스로 닫는다.
 */
export function subscribeProgress(
  jobId: string,
  onEvent: (event: ProgressEvent) => void,
  onFailure: (error: VendingError) => void,
): () => void {
  const source = new EventSource(`/api/progress/${jobId}`)
  let closed = false

  const close = () => {
    if (!closed) {
      closed = true
      source.close()
    }
  }

  source.addEventListener('progress', (event) => {
    let payload: ProgressEvent
    try {
      payload = JSON.parse((event as MessageEvent).data) as ProgressEvent
    } catch {
      return
    }
    onEvent(payload)
    if (payload.status === 'done' || payload.status === 'error') close()
  })

  source.onerror = () => {
    // 정상 종료 직후에도 onerror 가 한 번 뜬다 — 이미 닫혔으면 무시한다.
    if (closed) return
    close()
    onFailure(new VendingError('진행 상황 연결이 끊겼어요', 'sse_closed'))
  }

  return close
}

export function fileUrl(jobId: string): string {
  return `/api/file/${jobId}`
}
