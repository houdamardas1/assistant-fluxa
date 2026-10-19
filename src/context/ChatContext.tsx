import {
  createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode,
} from 'react'
import { ApiError, api } from '../lib/api'
import type { AskResponse, FileInfo, HistoryItem } from '../lib/types'

export type ChatMessage =
  | { id: string; role: 'user'; content: string }
  | { id: string; role: 'assistant'; kind: 'answer'; result: AskResponse; latencyMs: number | null; animate: boolean }
  | { id: string; role: 'assistant'; kind: 'error'; message: string }

export interface Pending {
  question: string
  startedAt: number
}

interface ChatValue {
  messages: ChatMessage[]
  pending: Pending | null
  historyVersion: number
  send: (question: string) => Promise<void>
  reset: () => void
  restore: (item: HistoryItem) => void
  attachment: FileInfo | null
  uploading: boolean
  uploadError: string | null
  attach: (file: File) => Promise<void>
  detach: () => void
}

const Ctx = createContext<ChatValue | null>(null)
const uid = () => Math.random().toString(36).slice(2) + Date.now().toString(36)

/** La conversation vit au niveau de l'application : elle survit au changement de page. */
export function ChatProvider({ children }: { children: ReactNode }) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [pending, setPending] = useState<Pending | null>(null)
  const [historyVersion, setHistoryVersion] = useState(0)
  const busy = useRef(false)
  const [attachment, setAttachment] = useState<FileInfo | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)

  const send = useCallback(async (question: string) => {
    const q = question.trim()
    if (!q || busy.current) return
    busy.current = true
    const startedAt = Date.now()
    setMessages((m) => [...m, { id: uid(), role: 'user', content: q }])
    setPending({ question: q, startedAt })

    try {
      const result = attachment
        ? await api.askFile(attachment.file_id, q)
        : await api.ask(q)
      setMessages((m) => [
        ...m,
        { id: uid(), role: 'assistant', kind: 'answer', result, latencyMs: Date.now() - startedAt, animate: true },
      ])
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(0, 'Erreur inattendue.')
      const message = err.retryAfter ? `${err.message} Réessayez dans ${err.retryAfter} s.` : err.message
      setMessages((m) => [...m, { id: uid(), role: 'assistant', kind: 'error', message }])
    } finally {
      busy.current = false
      setPending(null)
      setHistoryVersion((v) => v + 1)
    }
  }, [attachment])

  const attach = useCallback(async (file: File) => {
    if (busy.current) return
    setUploading(true)
    setUploadError(null)
    try {
      setAttachment(await api.uploadFile(file))
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : 'Téléversement impossible.')
    } finally {
      setUploading(false)
    }
  }, [])

  const detach = useCallback(() => {
    if (attachment) api.deleteFile(attachment.file_id).catch(() => undefined)
    setAttachment(null)
    setUploadError(null)
  }, [attachment])

  const reset = useCallback(() => {
    setMessages([])
    detach()
  }, [detach])

  const restore = useCallback((item: HistoryItem) => {
    if (busy.current) return
    setMessages([
      { id: uid(), role: 'user', content: item.question ?? '' },
      {
        id: uid(), role: 'assistant', kind: 'answer', animate: false, latencyMs: item.latency_ms,
        result: {
          request_id: item.request_id, answer: item.answer ?? '', mode: item.mode ?? 'RAG',
          departement: item.departement, confidence: item.confidence ?? 0, sources: item.sources,
        },
      },
    ])
  }, [])

  const value = useMemo(
    () => ({
      messages, pending, historyVersion, send, reset, restore,
      attachment, uploading, uploadError, attach, detach,
    }),
    [messages, pending, historyVersion, send, reset, restore, attachment, uploading, uploadError, attach, detach],
  )
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useChat(): ChatValue {
  const v = useContext(Ctx)
  if (!v) throw new Error('useChat doit etre utilise sous <ChatProvider>')
  return v
}
