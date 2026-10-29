import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { motion } from 'framer-motion'
import { useAuth } from '../context/AuthContext'
import { useChat } from '../context/ChatContext'
import { useAsync } from '../hooks/useAsync'
import { api } from '../lib/api'
import { firstName, roleLabel, suggestionsFrom } from '../lib/format'
import { AssistantMessage, ErrorMessage, TypingMessage, UserMessage } from '../components/chat/Message'
import { HistoryPanel } from '../components/chat/HistoryPanel'
import { Icon, LogoMark } from '../components/ui/Icons'
import { Skeleton } from '../components/ui/Skeleton'
import { FileAttachButton, FileChip } from '../components/chat/FileAttach'

const MAX_LEN = 1000

export default function Chat() {
  const { user } = useAuth()
  const { messages, pending, send, reset, attachment, uploading, uploadError, attach, detach } = useChat()
  const stats = useAsync(() => api.corpusStats(), [])
  const [text, setText] = useState('')
  const areaRef = useRef<HTMLTextAreaElement>(null)
  const endRef = useRef<HTMLDivElement>(null)

  // Zone de saisie qui grandit avec le texte (jusqu'a 160 px).
  useEffect(() => {
    const el = areaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`
  }, [text])

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, pending])

  const submit = (q: string = text) => {
    const value = q.trim()
    if (!value || pending) return
    setText('')
    void send(value)
  }

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      submit()
    }
  }

  const suggestions = stats.data ? suggestionsFrom(stats.data) : []
  const empty = messages.length === 0 && !pending

  return (
    <div className="flex h-full">
      <section className="flex min-w-0 flex-1 flex-col">
        <div className="flex-1 overflow-y-auto px-4 sm:px-8">
          <div className="mx-auto max-w-3xl space-y-6 py-8">
            {empty && (
              <motion.div className="pt-6 text-center" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}>
                <div className="mx-auto w-fit"><LogoMark size={56} /></div>
                <h2 className="mt-5 text-3xl font-semibold tracking-tight">
                  Bonjour {user ? firstName(user.display_name) : ''}
                </h2>
                <p className="mx-auto mt-2 max-w-lg text-muted">
                  Posez une question sur les documents auxquels votre profil{' '}
                  <span className="font-medium text-ink">({roleLabel(user?.role)})</span> a accès.
                  {stats.data && (
                    <> {stats.data.total_files} document(s) et {stats.data.total_chunks.toLocaleString('fr-FR')} passages sont disponibles.</>
                  )}
                </p>

                <div className="mx-auto mt-8 grid max-w-2xl gap-3 text-left sm:grid-cols-2">
                  {stats.loading && [0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-16" />)}
                  {suggestions.map((s, i) => (
                    <motion.button
                      key={s} type="button" onClick={() => submit(s)}
                      className="group rounded-2xl border border-line bg-surface/70 p-4 text-left text-sm transition hover:border-brand/50 hover:bg-brand/5 hover:shadow-glow"
                      initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 + i * 0.07, duration: 0.35 }}
                      whileHover={{ y: -2 }}
                    >
                      <Icon name="sparkles" size={15} className="mb-2 text-brand" />
                      <span className="block">{s}</span>
                    </motion.button>
                  ))}
                </div>
                {stats.error && <p className="mt-4 text-sm text-muted">Suggestions indisponibles : {stats.error.message}</p>}
              </motion.div>
            )}

            {messages.map((m) =>
              m.role === 'user' ? (
                <UserMessage key={m.id} content={m.content} />
              ) : m.kind === 'error' ? (
                <ErrorMessage key={m.id} message={m.message} />
              ) : (
                <AssistantMessage key={m.id} msgId={m.id} result={m.result} latencyMs={m.latencyMs} animate={m.animate} />
              ),
            )}

            {pending && <TypingMessage startedAt={pending.startedAt} totalFiles={stats.data?.total_files ?? null} />}
            <div ref={endRef} />
          </div>
        </div>

        <div className="border-t border-line bg-bg/70 px-4 py-4 backdrop-blur sm:px-8">
          <div className="mx-auto max-w-3xl">
            <FileChip attachment={attachment} uploading={uploading} error={uploadError} onRemove={detach} />
            <div className="flex items-end gap-2 rounded-2xl border border-line bg-surface p-2 shadow-soft transition focus-within:border-brand focus-within:ring-4 focus-within:ring-brand/15">
              <FileAttachButton onPick={(f) => void attach(f)} disabled={uploading || !!pending} />
              <textarea
                ref={areaRef} rows={1} value={text} maxLength={MAX_LEN} aria-label="Votre question"
                onChange={(e) => setText(e.target.value)} onKeyDown={onKeyDown}
                placeholder={attachment ? `Posez une question sur « ${attachment.nom} »…` : 'Posez votre question…'}
                className="max-h-40 min-h-[44px] flex-1 resize-none bg-transparent px-3 py-2.5 text-[15px] placeholder:text-muted/70"
              />
              <motion.button
                type="button" onClick={() => submit()} disabled={!text.trim() || !!pending} aria-label="Envoyer"
                className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-brand text-white transition disabled:opacity-40 dark:text-slate-950"
                whileTap={{ scale: 0.92 }}
              >
                <Icon name="send" size={18} />
              </motion.button>
            </div>
            <div className="mt-2 flex items-center justify-between px-1 text-xs text-muted">
              <span>Entrée pour envoyer · Maj+Entrée pour un saut de ligne</span>
              <span className="flex items-center gap-3">
                {text.length > MAX_LEN * 0.8 && <span className="tabular-nums">{text.length}/{MAX_LEN}</span>}
                {messages.length > 0 && !pending && (
                  <button type="button" onClick={reset} className="rounded-md px-1.5 py-0.5 hover:bg-line/60 hover:text-ink">Nouvelle conversation</button>
                )}
              </span>
            </div>
          </div>
        </div>
      </section>

      <aside className="hidden w-80 shrink-0 border-l border-line bg-surface/40 xl:block">
        <HistoryPanel />
      </aside>
    </div>
  )
}
