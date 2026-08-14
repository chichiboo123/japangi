/**
 * 인라인 SVG 아이콘.
 * 이모지는 OS/브라우저마다 모양도 유무도 제각각이라 (일부 리눅스에는 컬러 이모지 폰트가
 * 아예 없다) 자판기 UI 처럼 모양이 중요한 곳에는 직접 그린 아이콘을 쓴다.
 */

const base = {
  width: 20,
  height: 20,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 2,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  'aria-hidden': true,
  focusable: false,
}

export function SoundOnIcon() {
  return (
    <svg {...base}>
      <path d="M11 5 6 9H3v6h3l5 4V5Z" />
      <path d="M15.5 8.5a5 5 0 0 1 0 7" />
      <path d="M18.5 5.5a9 9 0 0 1 0 13" />
    </svg>
  )
}

export function SoundOffIcon() {
  return (
    <svg {...base}>
      <path d="M11 5 6 9H3v6h3l5 4V5Z" />
      <path d="m17 9 4 6" />
      <path d="m21 9-4 6" />
    </svg>
  )
}

export function PackageIcon() {
  return (
    <svg {...base} width={22} height={22}>
      <path d="M3 7.5 12 3l9 4.5v9L12 21l-9-4.5v-9Z" />
      <path d="M3 7.5 12 12l9-4.5" />
      <path d="M12 12v9" />
    </svg>
  )
}

export function FilmIcon() {
  return (
    <svg {...base} width={26} height={26}>
      <rect x="2.5" y="4.5" width="19" height="15" rx="2" />
      <path d="M7 4.5v15M17 4.5v15" />
      <path d="M2.5 12h19" />
    </svg>
  )
}

export function WarningIcon() {
  return (
    <svg {...base} width={22} height={22}>
      <path d="M12 3.5 2.8 19.5h18.4L12 3.5Z" />
      <path d="M12 10v4" />
      <path d="M12 17.2h.01" />
    </svg>
  )
}
