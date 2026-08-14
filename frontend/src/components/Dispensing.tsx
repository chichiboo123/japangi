import { formatEta } from '../format'
import type { ProgressEvent } from '../types'

const PHASES = [
  { key: 'downloading', label: '내려받기' },
  { key: 'processing', label: '변환' },
] as const

/** 배출 중 — 내부 코일이 돌고, 다운로드와 변환 단계를 나눠 보여준다. */
export default function Dispensing({ progress }: { progress: ProgressEvent }) {
  const currentIndex = PHASES.findIndex((phase) => phase.key === progress.status)

  return (
    <section className="dispensing" data-testid="progress" aria-label="배출 진행 상황">
      <div className="dispensing__head">
        <span className="coil" aria-hidden="true" />
        <div>
          <span className="dispensing__phase">{phaseName(progress.status)}</span>
          <p className="dispensing__message">{progress.message}</p>
        </div>
      </div>

      <div
        className="gauge"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={progress.indeterminate ? undefined : Math.round(progress.percent)}
        aria-valuetext={progress.indeterminate ? '진행률 계산 중' : `${Math.round(progress.percent)}%`}
      >
        <div
          className={`gauge__fill${progress.indeterminate ? ' gauge__fill--indeterminate' : ''}`}
          style={{ width: progress.indeterminate ? undefined : `${progress.percent}%` }}
        />
      </div>

      <div className="gauge__stats">
        <span data-testid="percent">{progress.indeterminate ? '···' : `${Math.round(progress.percent)}%`}</span>
        <span>
          {progress.speed && <span>{progress.speed}</span>}
          {progress.eta !== undefined && <span> · {formatEta(progress.eta)}</span>}
          {progress.queuePosition !== undefined && <span>대기 {progress.queuePosition}번째</span>}
        </span>
      </div>

      <ol className="steps">
        {PHASES.map((phase, index) => (
          <li
            key={phase.key}
            className={`steps__item${
              index === currentIndex ? ' steps__item--active' : index < currentIndex ? ' steps__item--done' : ''
            }`}
          >
            {index + 1}. {phase.label}
            {index < currentIndex && ' ✓'}
          </li>
        ))}
      </ol>
    </section>
  )
}

function phaseName(status: string): string {
  switch (status) {
    case 'queued':
      return '대기 중'
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
