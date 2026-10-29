import {
  createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode,
} from 'react'
import { api, setToken, setUnauthorizedHandler } from '../lib/api'
import type { User } from '../lib/types'

type Status = 'loading' | 'authenticated' | 'anonymous'

interface AuthValue {
  status: Status
  user: User | null
  login: (username: string, password: string) => Promise<void>
  logout: () => void
}

const STORAGE_KEY = 'mei.session'
const Ctx = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>('loading')
  const [user, setUser] = useState<User | null>(null)

  const logout = useCallback(() => {
    setToken(null)
    try {
      sessionStorage.removeItem(STORAGE_KEY)
    } catch {
      /* stockage indisponible */
    }
    setUser(null)
    setStatus('anonymous')
  }, [])

  // Restaure une session de l'onglet courant, validee aupres du serveur (GET /auth/me).
  useEffect(() => {
    setUnauthorizedHandler(logout)
    let saved: { token: string } | null = null
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY)
      saved = raw ? (JSON.parse(raw) as { token: string }) : null
    } catch {
      saved = null
    }

    if (!saved?.token) {
      setStatus('anonymous')
    } else {
      setToken(saved.token)
      api
        .me()
        .then((u) => {
          setUser(u)
          setStatus('authenticated')
        })
        .catch(() => logout())
    }
    return () => setUnauthorizedHandler(null)
  }, [logout])

  const login = useCallback(async (username: string, password: string) => {
    const res = await api.login(username, password)
    setToken(res.access_token)
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ token: res.access_token }))
    } catch {
      /* la session ne survivra pas a un rechargement */
    }
    setUser(res.user)
    setStatus('authenticated')
  }, [])

  const value = useMemo(() => ({ status, user, login, logout }), [status, user, login, logout])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useAuth(): AuthValue {
  const v = useContext(Ctx)
  if (!v) throw new Error('useAuth doit etre utilise sous <AuthProvider>')
  return v
}
