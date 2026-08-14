import { useMemo } from 'react'
import { useVendingMachine } from './useVendingMachine'
import { shelves } from './products'
import { formatDuration, formatEta, priceTag, qualityLabel, sizeTooltip } from './format'
import { COPYRIGHT_NOTICE } from './copy'
import Footer from './Footer'
import type { MediaKind, ProductOption } from './types'

export default function App() {
  const machine = useVendingMachine()
  const { snapshot, setUrl, inspect, select, setReencode, purchase, reset, dismissError } = machine
  const { state, product, selection, progress, error } = snapshot

  const stock = useMemo(() => shelves(product), [product])
  const chosen = selection?.option ?? null

  return (
    <div>
      <h1>링크 자판기</h1>

      {/* 상단 표시창 */}
      <p data-testid="display">{displayMessage(machine.snapshot)}</p>

      {/* 동전 투입구 */}
      <form
        onSubmit={(event) => {
          event.preventDefault()
          void inspect()
        }}
      >
        <label htmlFor="url-input">유튜브 또는 인스타그램 링크</label>
        <input
          id="url-input"
          data-testid="url-input"
          type="url"
          value={snapshot.url}
          placeholder="https://www.youtube.com/watch?v=..."
          onChange={(event) => setUrl(event.target.value)}
          disabled={state === 'inspecting' || state === 'dispensing'}
        />
        <button type="submit" data-testid="inspect" disabled={state === 'inspecting' || state === 'dispensing'}>
          {state === 'inspecting' ? '확인 중...' : '넣기'}
        </button>
        {product && (
          <button type="button" onClick={reset}>
            비우기
          </button>
        )}
      </form>

      {/* 미리보기 창 */}
      {product && (
        <section data-testid="preview">
          {product.thumbnail && <img src={product.thumbnail} alt="" width={160} />}
          <h2 data-testid="title">{product.title}</h2>
          <p>
            {product.uploader && <span>{product.uploader}</span>} <span>{formatDuration(product.duration)}</span>{' '}
            <span>{product.source}</span>
          </p>
        </section>
      )}

      {/* 진열대 */}
      {product && (
        <>
          <Shelf
            heading="음원"
            products={stock.audio}
            selected={chosen}
            onSelect={(option) => select('audio', option)}
          />
          <Shelf
            heading="영상"
            products={stock.video}
            selected={chosen}
            onSelect={(option) => select('video', option)}
          />
        </>
      )}

      {/* 재인코딩 토글 — 경고가 붙은 상품에서만 의미가 있다 */}
      {chosen?.warning && selection?.kind === 'video' && (
        <p>
          <label>
            <input
              type="checkbox"
              data-testid="reencode"
              checked={snapshot.reencode}
              onChange={(event) => setReencode(event.target.checked)}
            />
            H.264로 재인코딩하기 (호환성 ↑, 수 분 소요)
          </label>
          <br />
          <small>{chosen.warning}</small>
        </p>
      )}

      {/* 구매 버튼 */}
      {chosen && (
        <button
          type="button"
          data-testid="purchase"
          onClick={() => void purchase()}
          disabled={state === 'dispensing' || !chosen.available}
        >
          {chosen.label} 뽑기 — {priceTag(chosen)}
        </button>
      )}

      {/* 진행률 */}
      {progress && (state === 'dispensing' || state === 'dispensed') && (
        <section data-testid="progress">
          <p>
            <strong>{phaseLabel(progress.status)}</strong> {progress.message}
          </p>
          <progress value={progress.indeterminate ? undefined : progress.percent} max={100} />
          <span data-testid="percent">{progress.indeterminate ? '' : `${progress.percent.toFixed(0)}%`}</span>
          {progress.speed && <span> {progress.speed}</span>}
          {progress.eta !== undefined && <span> {formatEta(progress.eta)}</span>}
        </section>
      )}

      {/* 배출구 */}
      {state === 'dispensed' && snapshot.downloadUrl && (
        <section data-testid="tray">
          <a href={snapshot.downloadUrl} download={snapshot.downloadName ?? undefined} data-testid="save">
            {snapshot.downloadName} 저장하기
          </a>
          <button type="button" onClick={dismissError}>
            하나 더 뽑기
          </button>
        </section>
      )}

      {/* 오류 */}
      {state === 'jammed' && (
        <section data-testid="error" role="alert">
          <p>{error}</p>
          <button type="button" onClick={dismissError}>
            확인
          </button>
        </section>
      )}

      <p>{COPYRIGHT_NOTICE}</p>
      <Footer />
    </div>
  )
}

function Shelf({
  heading,
  products,
  selected,
  onSelect,
}: {
  heading: string
  products: ReturnType<typeof shelves>['audio']
  selected: ProductOption | null
  onSelect: (option: ProductOption) => void
}) {
  if (products.length === 0) return null
  return (
    <section>
      <h3>{heading}</h3>
      {products.map((item) => (
        <div key={item.format} data-testid={`product-${item.format}`}>
          <h4>
            {item.title}
            {item.options.every((option) => !option.available) && <span> SOLD OUT</span>}
          </h4>
          <ul>
            {item.options.map((option) => (
              <li key={option.quality}>
                <button
                  type="button"
                  data-testid={`option-${option.format}-${option.quality}`}
                  onClick={() => onSelect(option)}
                  disabled={!option.available}
                  aria-pressed={selected === option}
                  aria-label={optionAriaLabel(option)}
                >
                  {qualityLabel(option.format, option.quality)}
                  {' — '}
                  <span title={sizeTooltip(option.sizeSource)}>
                    {option.available ? priceTag(option) : 'SOLD OUT'}
                  </span>
                  {option.badge && <span> [{option.badge}]</span>}
                </button>
                {option.note && <small> {option.note}</small>}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </section>
  )
}

function optionAriaLabel(option: ProductOption): string {
  const quality = qualityLabel(option.format, option.quality)
  if (!option.available) return `${option.format.toUpperCase()} ${quality}, 품절${option.note ? `, ${option.note}` : ''}`
  return `${option.format.toUpperCase()} ${quality}, 예상 용량 ${priceTag(option)}`
}

function phaseLabel(status: string): string {
  switch (status) {
    case 'queued':
      return '대기'
    case 'downloading':
      return '내려받는 중'
    case 'processing':
      return '변환 중'
    case 'done':
      return '완료'
    default:
      return ''
  }
}

function displayMessage(snapshot: ReturnType<typeof useVendingMachine>['snapshot']): string {
  switch (snapshot.state) {
    case 'idle':
      return '링크를 넣어주세요'
    case 'inspecting':
      return '상품 확인 중...'
    case 'ready':
      return '원하는 상품을 골라주세요'
    case 'dispensing':
      return snapshot.progress?.indeterminate
        ? (snapshot.progress?.message ?? '준비 중...')
        : `${Math.round(snapshot.progress?.percent ?? 0)}% 배출 중`
    case 'dispensed':
      return '배출구에서 가져가세요!'
    case 'jammed':
      return snapshot.error ?? '오류가 발생했어요'
    default:
      return ''
  }
}

// MediaKind 를 실제로 쓰는 곳이 Shelf 호출부라 타입만 재수출한다.
export type { MediaKind }
