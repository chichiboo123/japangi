import { useEffect, useMemo, useRef } from 'react'
import { useVendingMachine } from './useVendingMachine'
import { useSound } from './useSound'
import { usePrefersReducedMotion } from './usePrefersReducedMotion'
import { shelves } from './products'
import { priceTag } from './format'
import { COPYRIGHT_NOTICE, SIZE_DISCLAIMER } from './copy'
import Display from './components/Display'
import CoinSlot from './components/CoinSlot'
import PreviewWindow from './components/PreviewWindow'
import Shelf from './components/Shelf'
import Dispensing from './components/Dispensing'
import Tray from './components/Tray'
import Footer from './Footer'
import { SoundOffIcon, SoundOnIcon, WarningIcon } from './components/icons'
import type { MachineSnapshot } from './useVendingMachine'

export default function App() {
  const { snapshot, setUrl, inspect, select, setReencode, purchase, reset, dismissError } = useVendingMachine()
  const { muted, toggleMute, play } = useSound()
  const reduceMotion = usePrefersReducedMotion()
  const { state, product, selection, progress, error } = snapshot

  const stock = useMemo(() => shelves(product), [product])
  const chosen = selection?.option ?? null

  // 상태가 바뀔 때 자판기 소리를 낸다 (사용자 조작에 따른 결과에만).
  const previousState = useRef(state)
  useEffect(() => {
    if (previousState.current === state) return
    previousState.current = state
    if (state === 'ready') play('ready')
    else if (state === 'dispensed') play('dispense')
    else if (state === 'jammed') play('error')
  }, [state, play])

  const busy = state === 'inspecting' || state === 'dispensing'

  return (
    <div className="machine">
      <header className="marquee">
        <div className="marquee__brand">
          <h1 className="marquee__title">링크 자판기</h1>
          <span className="marquee__sub">LINK VENDING MACHINE</span>
        </div>
        <button
          type="button"
          className="mute-toggle"
          onClick={toggleMute}
          data-testid="mute"
          aria-pressed={muted}
          aria-label={muted ? '효과음 켜기' : '효과음 끄기'}
        >
          {muted ? <SoundOffIcon /> : <SoundOnIcon />}
          {muted ? '소리 꺼짐' : '소리 켜짐'}
        </button>
      </header>

      <Display message={displayMessage(snapshot)} />

      <CoinSlot
        url={snapshot.url}
        busy={busy}
        hasProduct={product !== null}
        reduceMotion={reduceMotion}
        onChange={(value) => (value === '' ? reset() : setUrl(value))}
        onSubmit={() => {
          play('press')
          void inspect()
        }}
        onCoin={() => play('coin')}
      />

      {!product && state !== 'inspecting' && (
        <p className="hint">
          <strong>유튜브나 인스타그램 링크를 투입구에 넣어주세요.</strong>
          <br />
          원하는 형식(MP3 · WAV · MP4 · WebM)과 품질을 고르면
          <br />
          예상 용량을 확인하고 배출구에서 받아갈 수 있어요.
        </p>
      )}

      {product && <PreviewWindow product={product} />}

      {product && (
        <div className="showcase">
          <Shelf
            heading="음원"
            products={stock.audio}
            selected={chosen}
            onSelect={(kind, option) => {
              play('select')
              select(kind, option)
            }}
          />
          <Shelf
            heading="영상"
            products={stock.video}
            selected={chosen}
            onSelect={(kind, option) => {
              play('select')
              select(kind, option)
            }}
          />
        </div>
      )}

      {chosen?.warning && selection?.kind === 'video' && (
        <div className="reencode">
          <label className="reencode__row">
            <input
              type="checkbox"
              data-testid="reencode"
              checked={snapshot.reencode}
              onChange={(event) => setReencode(event.target.checked)}
            />
            H.264로 재인코딩하기 — 호환성은 좋아지지만 수 분 걸려요
          </label>
          <p className="reencode__note">{chosen.warning}</p>
        </div>
      )}

      {chosen && state !== 'dispensing' && state !== 'dispensed' && (
        <button
          type="button"
          className="purchase"
          data-testid="purchase"
          disabled={!chosen.available}
          onClick={() => {
            play('press')
            void purchase()
          }}
        >
          <span>{chosen.label} 뽑기</span>
          <span className="purchase__price">{priceTag(chosen)}</span>
        </button>
      )}

      {progress && state === 'dispensing' && <Dispensing progress={progress} />}

      {state === 'dispensed' && snapshot.downloadUrl && snapshot.downloadName && (
        <Tray
          href={snapshot.downloadUrl}
          filename={snapshot.downloadName}
          filesize={progress?.filesize}
          onAgain={() => {
            play('press')
            dismissError()
          }}
        />
      )}

      {state === 'jammed' && (
        <div className="fault" data-testid="error" role="alert">
          <span className="fault__icon" aria-hidden="true">
            <WarningIcon />
          </span>
          <p className="fault__text">{error}</p>
          <button type="button" className="fault__dismiss" onClick={dismissError}>
            확인
          </button>
        </div>
      )}

      <p className="notice">
        {COPYRIGHT_NOTICE}
        <br />
        {SIZE_DISCLAIMER}
      </p>

      <Footer />
    </div>
  )
}

function displayMessage(snapshot: MachineSnapshot): string {
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
