import type { MediaKind, ProbeResult, Product, ProductOption } from './types'

const PRODUCT_TITLES: Record<string, string> = {
  mp3: 'MP3',
  wav: 'WAV',
  mp4: 'MP4',
  webm: 'WebM',
}

/** 포맷별로 품질 선택지를 묶어 진열대 한 칸을 만든다. */
export function shelves(result: ProbeResult | null): { audio: Product[]; video: Product[] } {
  if (!result) return { audio: [], video: [] }
  return {
    audio: group('audio', result.options.audio),
    video: group('video', result.options.video),
  }
}

function group(kind: MediaKind, options: ProductOption[]): Product[] {
  const buckets = new Map<string, ProductOption[]>()
  for (const option of options) {
    const list = buckets.get(option.format) ?? []
    list.push(option)
    buckets.set(option.format, list)
  }
  return [...buckets.entries()].map(([format, list]) => ({
    kind,
    format: format as Product['format'],
    title: PRODUCT_TITLES[format] ?? format.toUpperCase(),
    options: list,
  }))
}

/** 한 칸이 통째로 품절인지 (모든 품질이 SOLD OUT). */
export function isSoldOut(product: Product): boolean {
  return product.options.every((option) => !option.available)
}
