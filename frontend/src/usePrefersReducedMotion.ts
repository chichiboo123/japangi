import { useEffect, useState } from 'react'

const QUERY = '(prefers-reduced-motion: reduce)'

/**
 * 움직임 최소화 설정. CSS 로도 애니메이션을 끄지만,
 * 자바스크립트로 만들어내는 연출(떨어지는 동전 등)은 아예 만들지 않는 게 낫다.
 */
export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(() => window.matchMedia?.(QUERY).matches ?? false)

  useEffect(() => {
    const media = window.matchMedia?.(QUERY)
    if (!media) return
    const listen = (event: MediaQueryListEvent) => setReduced(event.matches)
    media.addEventListener('change', listen)
    return () => media.removeEventListener('change', listen)
  }, [])

  return reduced
}
