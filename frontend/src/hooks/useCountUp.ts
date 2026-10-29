import { useEffect, useState } from 'react'
import { animate, useReducedMotion } from 'framer-motion'

/** Compteur anime de 0 jusqu'a `target` (immediat si l'utilisateur reduit les animations). */
export function useCountUp(target: number, duration = 1.1): number {
  const reduce = useReducedMotion()
  const [value, setValue] = useState<number>(reduce ? target : 0)

  useEffect(() => {
    if (reduce) {
      setValue(target)
      return
    }
    const controls = animate(0, target, {
      duration,
      ease: 'easeOut',
      onUpdate: (x: number) => setValue(Math.round(x)),
    })
    return () => controls.stop()
  }, [target, duration, reduce])

  return value
}
