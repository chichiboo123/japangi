import { useEffect, useRef, useState } from 'react'

interface Props {
  url: string
  busy: boolean
  hasProduct: boolean
  onChange: (url: string) => void
  onSubmit: () => void
  onCoin: () => void
  reduceMotion: boolean
}

/** 동전 투입구 — 링크를 붙여넣으면 동전이 슬롯으로 떨어진다. */
export default function CoinSlot({ url, busy, hasProduct, onChange, onSubmit, onCoin, reduceMotion }: Props) {
  const [coins, setCoins] = useState<number[]>([])
  const nextId = useRef(0)

  useEffect(() => {
    if (coins.length === 0) return
    const timer = window.setTimeout(() => setCoins((list) => list.slice(1)), 650)
    return () => window.clearTimeout(timer)
  }, [coins])

  const dropCoin = () => {
    onCoin()
    if (reduceMotion) return
    nextId.current += 1
    setCoins((list) => [...list, nextId.current])
  }

  return (
    <form
      className="slot"
      onSubmit={(event) => {
        event.preventDefault()
        onSubmit()
      }}
    >
      <label className="slot__label" htmlFor="url-input">
        동전 투입구 · 유튜브 / 인스타그램 링크
      </label>
      <div className="slot__row">
        <div className="slot__mouth">
          {coins.map((id) => (
            <span key={id} className="coin" aria-hidden="true" />
          ))}
          <input
            id="url-input"
            data-testid="url-input"
            className="slot__input"
            type="url"
            inputMode="url"
            autoComplete="off"
            spellCheck={false}
            value={url}
            placeholder="https://www.youtube.com/watch?v=..."
            disabled={busy}
            onChange={(event) => onChange(event.target.value)}
            onPaste={dropCoin}
          />
        </div>
        <button type="submit" className="button button--primary" data-testid="inspect" disabled={busy}>
          {busy ? '확인 중...' : '넣기'}
        </button>
        {hasProduct && (
          <button type="button" className="button" data-testid="reset" onClick={() => onChange('')}>
            비우기
          </button>
        )}
      </div>
    </form>
  )
}
