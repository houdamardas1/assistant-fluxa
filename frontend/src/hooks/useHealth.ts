import { useEffect, useState } from 'react'
import { api } from '../lib/api'

export type HealthState = 'checking' | 'online' | 'degraded' | 'offline'

/** Etat REEL de l'API (GET /health), reinterroge toutes les 30 s. */
export function useHealth(intervalMs = 30000): HealthState {
  const [state, setState] = useState<HealthState>('checking')

  useEffect(() => {
    let alive = true
    const check = () =>
      api
        .health()
        .then((h) => alive && setState(h.index_loaded ? 'online' : 'degraded'))
        .catch(() => alive && setState('offline'))
    check()
    const id = setInterval(check, intervalMs)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [intervalMs])

  return state
}
