import type { ProductOption, SizeSource } from './types'

const UNITS = ['B', 'KB', 'MB', 'GB', 'TB']

/** 1024 기준, 소수점 1자리 — 백엔드 sizes.human_bytes 와 같은 규칙. */
export function humanBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined || bytes < 0) return '용량 미상'
  let value = bytes
  let unit = 0
  while (value >= 1024 && unit < UNITS.length - 1) {
    value /= 1024
    unit += 1
  }
  return unit === 0 ? `${Math.round(value)} B` : `${value.toFixed(1)} ${UNITS[unit]}`
}

/** 추정값에는 '약' 을 붙인다. filesize 로 확정된 값에는 붙이지 않는다. */
export function priceTag(option: ProductOption): string {
  if (option.estimatedBytes === null) return '용량 미상'
  const size = humanBytes(option.estimatedBytes)
  return option.sizeSource === 'exact' ? size : `약 ${size}`
}

export function sizeTooltip(source: SizeSource): string {
  switch (source) {
    case 'exact':
      return '원본 서버가 알려준 정확한 용량이에요.'
    case 'approx':
      return '원본 서버가 알려준 근사값이에요. 실제와 5~10% 차이날 수 있어요.'
    case 'bitrate':
      return '비트레이트 × 재생시간으로 계산한 추정값이에요. 실제와 5~10% 차이날 수 있어요.'
    case 'formula':
      return '인코딩 공식으로 계산한 값이에요. 실제와 5~10% 차이날 수 있어요.'
    default:
      return '용량을 알 수 없는 항목이에요.'
  }
}

export function formatDuration(seconds: number | null | undefined): string {
  if (!seconds || seconds < 0) return '--:--'
  const total = Math.round(seconds)
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const secs = total % 60
  const pad = (n: number) => String(n).padStart(2, '0')
  return hours > 0 ? `${hours}:${pad(minutes)}:${pad(secs)}` : `${minutes}:${pad(secs)}`
}

export function formatEta(seconds: number | undefined): string {
  if (seconds === undefined || seconds === null || seconds < 0) return ''
  if (seconds < 60) return `${Math.round(seconds)}초 남음`
  return `${Math.floor(seconds / 60)}분 ${Math.round(seconds % 60)}초 남음`
}

/** 품질 키를 사람이 읽는 라벨로. */
export function qualityLabel(format: string, quality: string): string {
  if (format === 'mp3') return `${quality}kbps`
  if (format === 'wav') {
    const [rate, depth] = quality.split('-')
    return `${Number(rate) / 1000}kHz ${depth}bit`
  }
  return quality
}
