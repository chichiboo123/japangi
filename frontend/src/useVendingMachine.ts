import { useCallback, useEffect, useRef, useState } from 'react'
import { VendingError, fileUrl, probe, startDownload, subscribeProgress } from './api'
import type { MediaKind, ProbeResult, ProductOption, ProgressEvent } from './types'

/** 자판기의 상태. UI 는 이 값만 보고 그린다. */
export type MachineState =
  | 'idle' // 링크를 기다리는 중
  | 'inspecting' // 투입된 링크 확인 중
  | 'ready' // 진열대 공개
  | 'dispensing' // 배출 중
  | 'dispensed' // 배출구에 상품이 떨어짐
  | 'jammed' // 오류

export interface Selection {
  kind: MediaKind
  option: ProductOption
}

export interface MachineSnapshot {
  state: MachineState
  url: string
  product: ProbeResult | null
  selection: Selection | null
  progress: ProgressEvent | null
  error: string | null
  errorCode: string | null
  reencode: boolean
  downloadUrl: string | null
  downloadName: string | null
}

const INITIAL: MachineSnapshot = {
  state: 'idle',
  url: '',
  product: null,
  selection: null,
  progress: null,
  error: null,
  errorCode: null,
  reencode: false,
  downloadUrl: null,
  downloadName: null,
}

export function useVendingMachine() {
  const [snapshot, setSnapshot] = useState<MachineSnapshot>(INITIAL)
  const unsubscribe = useRef<(() => void) | null>(null)
  const inspectAbort = useRef<AbortController | null>(null)

  useEffect(() => {
    return () => {
      unsubscribe.current?.()
      inspectAbort.current?.abort()
    }
  }, [])

  const patch = useCallback((changes: Partial<MachineSnapshot>) => {
    setSnapshot((current) => ({ ...current, ...changes }))
  }, [])

  const setUrl = useCallback(
    (url: string) => {
      setSnapshot((current) =>
        // 링크를 새로 넣으면 진열대를 비운다.
        current.state === 'idle' || current.state === 'inspecting'
          ? { ...current, url }
          : { ...INITIAL, url },
      )
    },
    [],
  )

  const reset = useCallback(() => {
    unsubscribe.current?.()
    unsubscribe.current = null
    setSnapshot(INITIAL)
  }, [])

  /** 동전 투입 — 링크를 확인하고 진열대를 채운다. */
  const inspect = useCallback(
    async (rawUrl?: string) => {
      const url = (rawUrl ?? snapshot.url).trim()
      if (!url) {
        patch({ state: 'jammed', error: '링크를 먼저 넣어주세요', errorCode: 'empty' })
        return
      }

      inspectAbort.current?.abort()
      const controller = new AbortController()
      inspectAbort.current = controller

      patch({ state: 'inspecting', url, error: null, errorCode: null, product: null, selection: null })
      try {
        const result = await probe(url, controller.signal)
        setSnapshot((current) => ({
          ...current,
          state: 'ready',
          product: result,
          // 기본 선택: 판매 중인 첫 상품
          selection: firstAvailable(result),
          error: null,
          errorCode: null,
        }))
      } catch (error) {
        if (controller.signal.aborted) return
        const failure = error as VendingError
        patch({
          state: 'jammed',
          error: failure.message ?? '자판기가 링크를 읽지 못했어요',
          errorCode: failure.code ?? 'unknown',
        })
      }
    },
    [patch, snapshot.url],
  )

  const select = useCallback(
    (kind: MediaKind, option: ProductOption) => {
      if (!option.available) return
      patch({ selection: { kind, option } })
    },
    [patch],
  )

  const setReencode = useCallback((value: boolean) => patch({ reencode: value }), [patch])

  /** 구매 버튼 — 배출 시작. */
  const purchase = useCallback(async () => {
    const { url, selection, reencode } = snapshot
    if (!selection || !url) return

    patch({
      state: 'dispensing',
      error: null,
      errorCode: null,
      downloadUrl: null,
      downloadName: null,
      progress: { status: 'queued', percent: 0, message: '주문을 넣는 중...', indeterminate: true },
    })

    try {
      const jobId = await startDownload({
        url,
        type: selection.kind,
        format: selection.option.format,
        quality: selection.option.quality,
        reencode,
      })

      unsubscribe.current?.()
      unsubscribe.current = subscribeProgress(
        jobId,
        (event) => {
          if (event.status === 'done') {
            patch({
              state: 'dispensed',
              progress: event,
              downloadUrl: fileUrl(jobId),
              downloadName: event.filename ?? null,
            })
          } else if (event.status === 'error') {
            patch({
              state: 'jammed',
              progress: event,
              error: event.error ?? event.message,
              errorCode: event.code ?? 'unknown',
            })
          } else {
            patch({ progress: event })
          }
        },
        (failure) => {
          patch({ state: 'jammed', error: failure.message, errorCode: failure.code })
        },
      )
    } catch (error) {
      const failure = error as VendingError
      patch({ state: 'jammed', error: failure.message, errorCode: failure.code ?? 'unknown' })
    }
  }, [patch, snapshot])

  /** 오류 후 진열대로 돌아가기 (링크는 유지). */
  const dismissError = useCallback(() => {
    setSnapshot((current) => ({
      ...current,
      state: current.product ? 'ready' : 'idle',
      error: null,
      errorCode: null,
      progress: null,
    }))
  }, [])

  return { snapshot, setUrl, inspect, select, setReencode, purchase, reset, dismissError }
}

function firstAvailable(result: ProbeResult): Selection | null {
  const audio = result.options.audio.find((option) => option.available)
  if (audio) return { kind: 'audio', option: audio }
  const video = result.options.video.find((option) => option.available)
  return video ? { kind: 'video', option: video } : null
}
