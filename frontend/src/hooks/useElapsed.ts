import { useEffect, useState } from 'react'

/** Secondes ecoulees depuis `since` (ms) : compteur reel d'attente. */
export function useElapsed(since: number | null): number {
  const [now, setNow] = useState<number>(() => Date.now())

  useEffect(() => {
    if (since === null) return
    setNow(Date.now())
    const id = setInterval(() => setNow(Date.now()), 500)
    return () => clearInterval(id)
  }, [since])

  return since === null ? 0 : Math.max(0, Math.floor((now - since) / 1000))
}
