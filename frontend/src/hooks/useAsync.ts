import { useCallback, useEffect, useState } from 'react'
import { ApiError } from '../lib/api'

interface AsyncState<T> {
  data: T | null
  error: ApiError | null
  loading: boolean
}

/** Charge une ressource de l'API ; `reload()` relance l'appel. */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [state, setState] = useState<AsyncState<T>>({ data: null, error: null, loading: true })
  const [tick, setTick] = useState(0)

  useEffect(() => {
    let alive = true
    setState((s) => ({ ...s, loading: true, error: null }))
    fn()
      .then((data) => alive && setState({ data, error: null, loading: false }))
      .catch((e) =>
        alive &&
        setState({ data: null, error: e instanceof ApiError ? e : new ApiError(0, String(e)), loading: false }),
      )
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick])

  const reload = useCallback(() => setTick((t) => t + 1), [])
  return { ...state, reload }
}
