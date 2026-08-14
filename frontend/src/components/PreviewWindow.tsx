import { formatDuration } from '../format'
import type { ProbeResult } from '../types'
import { FilmIcon } from './icons'

const SOURCE_LABELS: Record<string, string> = {
  youtube: '유튜브',
  instagram: '인스타그램',
  test: '테스트',
}

/** 자판기 상단 미리보기 창 — 지금 무엇을 뽑으려는지 보여준다. */
export default function PreviewWindow({ product }: { product: ProbeResult }) {
  return (
    <section className="preview" data-testid="preview" aria-label="선택한 콘텐츠 미리보기">
      {product.thumbnail ? (
        <img className="preview__thumb" src={product.thumbnail} alt="" loading="lazy" />
      ) : (
        <div className="preview__thumb preview__thumb--empty" aria-hidden="true">
          <FilmIcon />
        </div>
      )}
      <div className="preview__body">
        <h2 className="preview__title" data-testid="title">
          {product.title}
        </h2>
        <p className="preview__meta">
          <span className="preview__badge">{SOURCE_LABELS[product.source] ?? product.source}</span>
          {product.uploader && <span>{product.uploader}</span>}
          {product.duration !== null && <span>{formatDuration(product.duration)}</span>}
        </p>
      </div>
    </section>
  )
}
