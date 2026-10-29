import { useEffect, useState } from 'react'
import { useReducedMotion } from 'framer-motion'

/** Revelation progressive d'un texte DEJA recu (effet de presentation, pas du streaming). */
export function useTypewriter(text: string, enabled: boolean, maxSeconds = 1.6) {
  const reduce = useReducedMotion()
  const skip = !enabled || !!reduce
  const [length, setLength] = useState<number>(skip ? text.length : 0)

  useEffect(() => {
    if (skip) {
      setLength(text.length)
      return
    }
    const total = Math.min(maxSeconds * 1000, Math.max(400, text.length * 8))
    const start = performance.now()
    let raf = 0
    const tick = (now: number) => {
      const p = Math.min(1, (now - start) / total)
      setLength(Math.floor(p * text.length))
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [text, skip, maxSeconds])

  return { shown: text.slice(0, length), done: length >= text.length }
}
