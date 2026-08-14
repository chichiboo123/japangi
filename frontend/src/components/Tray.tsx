import { humanBytes } from '../format'
import { PackageIcon } from './icons'

interface Props {
  href: string
  filename: string
  filesize?: number
  onAgain: () => void
}

/** 하단 배출구 — 완성된 상품이 툭 떨어진다. 클릭하면 저장. */
export default function Tray({ href, filename, filesize, onAgain }: Props) {
  return (
    <section className="tray" data-testid="tray" aria-label="배출구">
      <p className="tray__label">— 배출구 —</p>
      <a className="tray__item" href={href} download={filename} data-testid="save">
        <span className="tray__icon" aria-hidden="true">
          <PackageIcon />
        </span>
        <span className="tray__name">
          {filename}
          <span className="tray__size">{humanBytes(filesize ?? null)}</span>
        </span>
        <span className="tray__cta">저장</span>
      </a>
      <button type="button" className="tray__again" onClick={onAgain} data-testid="again">
        하나 더 뽑기
      </button>
    </section>
  )
}
