import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * 자판기 효과음 — 오디오 파일 없이 Web Audio API 로 직접 합성한다.
 * 번들도 안 커지고, 자판기다운 기계음은 오히려 합성이 더 잘 어울린다.
 *
 * 사용자 조작에만 반응해서 소리를 낸다 (페이지 로드 시 자동 재생 없음).
 */
export type SoundName = 'coin' | 'press' | 'select' | 'dispense' | 'error' | 'ready'

const STORAGE_KEY = 'japangi:muted'

export function useSound() {
  const [muted, setMuted] = useState<boolean>(() => {
    try {
      return window.localStorage.getItem(STORAGE_KEY) === 'true'
    } catch {
      return false
    }
  })
  const context = useRef<AudioContext | null>(null)

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, String(muted))
    } catch {
      /* 시크릿 모드 등에서 막혀도 무시 */
    }
  }, [muted])

  const ensureContext = useCallback((): AudioContext | null => {
    if (muted) return null
    if (!context.current) {
      const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
      if (!Ctor) return null
      context.current = new Ctor()
    }
    // 첫 사용자 조작 전에는 suspended 상태다.
    if (context.current.state === 'suspended') void context.current.resume()
    return context.current
  }, [muted])

  const play = useCallback(
    (name: SoundName) => {
      const ctx = ensureContext()
      if (!ctx) return
      const now = ctx.currentTime

      switch (name) {
        case 'coin':
          // 동전이 슬롯을 굴러 떨어지는 소리 — 금속성 배음 두 번
          chime(ctx, now, 1180, 0.07, 0.16)
          chime(ctx, now + 0.09, 1560, 0.06, 0.12)
          chime(ctx, now + 0.17, 940, 0.05, 0.2)
          break
        case 'press':
          // 물리 버튼이 눌리는 딸깍
          thud(ctx, now, 190, 0.09, 0.2)
          break
        case 'select':
          chime(ctx, now, 720, 0.05, 0.09)
          break
        case 'ready':
          // 진열대 점등
          chime(ctx, now, 660, 0.06, 0.1)
          chime(ctx, now + 0.1, 880, 0.06, 0.14)
          break
        case 'dispense':
          // 상품이 배출구로 툭 떨어지는 소리
          thud(ctx, now, 120, 0.16, 0.32)
          noise(ctx, now + 0.05, 0.18, 0.12)
          break
        case 'error':
          // 거스름돈 반환 부저
          buzz(ctx, now, 220, 0.18, 0.22)
          buzz(ctx, now + 0.2, 165, 0.2, 0.2)
          break
      }
    },
    [ensureContext],
  )

  const toggleMute = useCallback(() => setMuted((value) => !value), [])

  return { muted, toggleMute, play }
}

function envelope(ctx: AudioContext, start: number, peak: number, duration: number) {
  const gain = ctx.createGain()
  gain.gain.setValueAtTime(0.0001, start)
  gain.gain.exponentialRampToValueAtTime(peak, start + 0.01)
  gain.gain.exponentialRampToValueAtTime(0.0001, start + duration)
  gain.connect(ctx.destination)
  return gain
}

function chime(ctx: AudioContext, start: number, frequency: number, peak: number, duration: number) {
  const osc = ctx.createOscillator()
  osc.type = 'triangle'
  osc.frequency.setValueAtTime(frequency, start)
  osc.connect(envelope(ctx, start, peak, duration))
  osc.start(start)
  osc.stop(start + duration + 0.02)
}

function thud(ctx: AudioContext, start: number, frequency: number, peak: number, duration: number) {
  const osc = ctx.createOscillator()
  osc.type = 'sine'
  osc.frequency.setValueAtTime(frequency, start)
  osc.frequency.exponentialRampToValueAtTime(Math.max(40, frequency * 0.4), start + duration)
  osc.connect(envelope(ctx, start, peak, duration))
  osc.start(start)
  osc.stop(start + duration + 0.02)
}

function buzz(ctx: AudioContext, start: number, frequency: number, peak: number, duration: number) {
  const osc = ctx.createOscillator()
  osc.type = 'square'
  osc.frequency.setValueAtTime(frequency, start)
  osc.connect(envelope(ctx, start, peak, duration))
  osc.start(start)
  osc.stop(start + duration + 0.02)
}

function noise(ctx: AudioContext, start: number, peak: number, duration: number) {
  const frames = Math.floor(ctx.sampleRate * duration)
  const buffer = ctx.createBuffer(1, frames, ctx.sampleRate)
  const data = buffer.getChannelData(0)
  for (let i = 0; i < frames; i += 1) {
    data[i] = (Math.random() * 2 - 1) * (1 - i / frames)
  }
  const source = ctx.createBufferSource()
  source.buffer = buffer
  source.connect(envelope(ctx, start, peak, duration))
  source.start(start)
}
