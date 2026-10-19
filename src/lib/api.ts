import type {
  AskResponse, AuditEvent, AuditSummary, AuditTimeseries, CorpusStats, Health,
  HistoryItem, KpiItem, LoginResponse, User,
} from './types'

const BASE: string =
  ((import.meta.env.VITE_API_URL as string | undefined) ?? 'http://127.0.0.1:8000').replace(/\/$/, '')

export const apiBase = BASE

export class ApiError extends Error {
  status: number
  retryAfter?: number

  constructor(status: number, message: string, retryAfter?: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status // 0 = API injoignable ou delai depasse
    this.retryAfter = retryAfter
  }
}

// Jeton garde en memoire (et en sessionStorage par AuthContext) : jamais dans le code ni l'URL.
let token: string | null = null
let onUnauthorized: (() => void) | null = null

export function setToken(value: string | null): void {
  token = value
}
export function setUnauthorizedHandler(fn: (() => void) | null): void {
  onUnauthorized = fn
}

function messageFor(status: number, detail: string, hadToken: boolean): string {
  if (status === 401) return hadToken ? 'Votre session a expiré : reconnectez-vous.' : detail || 'Identifiants invalides.'
  if (status === 403) return detail || 'Accès refusé.'
  if (status === 422) return 'Requête invalide : vérifiez les informations saisies.'
  if (status === 429) return detail || 'Trop de requêtes en peu de temps.'
  if (status === 503) return detail || 'Service momentanément saturé. Réessayez dans un instant.'
  if (status >= 500) return detail || 'Erreur interne du serveur.'
  return detail || `Erreur HTTP ${status}.`
}

interface Options {
  method?: 'GET' | 'POST'
  body?: unknown
  timeoutMs?: number
  auth?: boolean
}

async function request<T>(path: string, opts: Options = {}): Promise<T> {
  const { method = 'GET', body, timeoutMs = 20000, auth = true } = opts
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)

  const headers: Record<string, string> = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const hadToken = auth && token !== null
  if (hadToken) headers.Authorization = `Bearer ${token}`

  try {
    const res = await fetch(BASE + path, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    })

    if (!res.ok) {
      let detail = ''
      try {
        const data = await res.json()
        if (typeof data?.detail === 'string') detail = data.detail
        else if (Array.isArray(data?.detail))
          detail = data.detail.map((d: { msg?: string }) => d.msg ?? '').join('; ')
      } catch {
        /* corps non JSON */
      }
      const retry = Number(res.headers.get('Retry-After')) || undefined
      if (res.status === 401 && hadToken) onUnauthorized?.()
      throw new ApiError(res.status, messageFor(res.status, detail, hadToken), retry)
    }

    return (await res.json()) as T
  } catch (e) {
    if (e instanceof ApiError) throw e
    if (controller.signal.aborted)
      throw new ApiError(0, 'Délai dépassé : le serveur met trop de temps à répondre.')
    throw new ApiError(0, `API injoignable (${BASE}). Le serveur est-il démarré ?`)
  } finally {
    clearTimeout(timer)
  }
}

async function download(path: string, filename: string, timeoutMs = 30000): Promise<{ blob: Blob; filename: string }> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  const hadToken = token !== null
  const headers: Record<string, string> = {}
  if (hadToken) headers.Authorization = `Bearer ${token}`

  try {
    const res = await fetch(BASE + path, { headers, signal: controller.signal })
    if (!res.ok) {
      let detail = ''
      try {
        const data = await res.json()
        if (typeof data?.detail === 'string') detail = data.detail
      } catch {
        /* corps non JSON */
      }
      const retry = Number(res.headers.get('Retry-After')) || undefined
      if (res.status === 401 && hadToken) onUnauthorized?.()
      throw new ApiError(res.status, messageFor(res.status, detail, hadToken), retry)
    }
    return { blob: await res.blob(), filename }
  } catch (e) {
    if (e instanceof ApiError) throw e
    if (controller.signal.aborted)
      throw new ApiError(0, 'Délai dépassé : le serveur met trop de temps à répondre.')
    throw new ApiError(0, `API injoignable (${BASE}). Le serveur est-il démarré ?`)
  } finally {
    clearTimeout(timer)
  }
}

import type { FileAnswer, FileInfo } from './types'

interface CallOptions {
  method?: string
  json?: unknown
  form?: FormData
  timeoutMs?: number
}

async function call<T>(path: string, opts: CallOptions = {}): Promise<T> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), opts.timeoutMs ?? 60000)
  const hadToken = token !== null
  const headers: Record<string, string> = {}
  if (hadToken) headers.Authorization = `Bearer ${token}`
  let body: BodyInit | undefined
  if (opts.form) {
    body = opts.form
  } else if (opts.json !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(opts.json)
  }

  try {
    const res = await fetch(BASE + path, { method: opts.method ?? 'GET', headers, body, signal: controller.signal })
    if (!res.ok) {
      let detail = ''
      try {
        const data = await res.json()
        if (typeof data?.detail === 'string') detail = data.detail
      } catch {
        /* corps non JSON */
      }
      const retry = Number(res.headers.get('Retry-After')) || undefined
      if (res.status === 401 && hadToken) onUnauthorized?.()
      throw new ApiError(res.status, messageFor(res.status, detail, hadToken), retry)
    }
    return (await res.json()) as T
  } catch (e) {
    if (e instanceof ApiError) throw e
    if (controller.signal.aborted)
      throw new ApiError(0, 'Délai dépassé : le serveur met trop de temps à répondre.')
    throw new ApiError(0, `API injoignable (${BASE}). Le serveur est-il démarré ?`)
  } finally {
    clearTimeout(timer)
  }
}

export const api = {
  health: () => request<Health>('/health', { auth: false, timeoutMs: 5000 }),
  login: (username: string, password: string) =>
    request<LoginResponse>('/auth/login', { method: 'POST', body: { username, password }, auth: false }),
  me: () => request<User>('/auth/me'),
  // Une question peut durer ~1 minute (limite de debit du LLM + verification).
  ask: (question: string) =>
    request<AskResponse>('/ask', { method: 'POST', body: { question }, timeoutMs: 150000 }),
  history: (limit = 30) => request<HistoryItem[]>(`/me/history?limit=${limit}`),
  corpusStats: () => request<CorpusStats>('/corpus/stats'),
  auditSummary: () => request<AuditSummary>('/admin/audit/summary'),
  auditTimeseries: (days = 14) => request<AuditTimeseries>(`/admin/audit/timeseries?days=${days}`),
  auditRecent: (limit = 100) => request<AuditEvent[]>(`/admin/audit/recent?limit=${limit}`),
  kpi: () => request<KpiItem[]>('/kpi'),
  uploadFile: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return call<FileInfo>('/files', { method: 'POST', form, timeoutMs: 90000 })
  },
  askFile: (fileId: string, question: string) =>
    call<FileAnswer>(`/files/${fileId}/ask`, { method: 'POST', json: { question } }),
  deleteFile: (fileId: string) =>
    call<{ supprime: boolean }>(`/files/${fileId}`, { method: 'DELETE', timeoutMs: 15000 }),
  kpiReport: () => download('/kpi/report.pdf', `fluxa-indicateurs-${new Date().toISOString().slice(0, 10)}.pdf`),
}
