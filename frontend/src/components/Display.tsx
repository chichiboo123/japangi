import { useEffect, useRef, useState } from 'react'

/** 상단 LED 도트매트릭스 표시창. 긴 문장은 흘러가고, 상태 변화는 스크린리더에도 알린다. */
export default function Display({ message }: { message: string }) {
  const textRef = useRef<HTMLParagraphElement>(null)
  const [overflowing, setOverflowing] = useState(false)

  useEffect(() => {
    const node = textRef.current
    if (!node) return
    // 표시창보다 글자가 길면 흐르게 한다.
    setOverflowing(node.scrollWidth > node.parentElement!.clientWidth)
  }, [message])

  return (
    <div className="display">
      <p
        ref={textRef}
        data-testid="display"
        className={`display__text${overflowing ? ' display__text--scroll' : ''}`}
        aria-live="polite"
        aria-atomic="true"
      >
        {message}
        <span className="display__cursor" aria-hidden="true" />
      </p>
    </div>
  )
}
