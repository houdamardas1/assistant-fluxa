import { useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useAsync } from '../hooks/useAsync'
import { api } from '../lib/api'
import { eventMeta, fileLabel, formatDateTime, formatMs, modeMeta, roleLabel } from '../lib/format'
import type { AuditEvent, Source } from '../lib/types'
import { Badge } from '../components/ui/Badge'
import { Icon } from '../components/ui/Icons'
import { ErrorBox, Skeleton } from '../components/ui/Skeleton'

function parseSources(raw: string | null): Source[] {
  if (!raw) return []
  try {
    const v = JSON.parse(raw)
    return Array.isArray(v) ? (v as Source[]) : []
  } catch {
    return []
  }
}

function Detail({ e }: { e: AuditEvent }) {
  const sources = parseSources(e.sources)
  const line = (label: string, value: string | null | undefined) =>
    value ? (
      <div>
        <dt className="text-xs font-semibold uppercase tracking-wide text-muted">{label}</dt>
        <dd className="mt-0.5 whitespace-pre-wrap break-words text-sm">{value}</dd>
      </div>
    ) : null

  return (
    <motion.dl
      className="grid gap-3 border-t border-line bg-bg/40 px-4 py-4 sm:grid-cols-2"
      initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.25 }}
      style={{ overflow: 'hidden' }}
    >
      {line('Question', e.question)}
      {line('Réponse (extrait)', e.answer_excerpt)}
      {line('Détail', e.detail)}
      {line('Référence', e.request_id)}
      {line('Adresse', e.client_ip)}
      {line('Département', e.departement ? roleLabel(e.departement) : null)}
      {sources.length > 0 && (
        <div className="sm:col-span-2">
          <dt className="text-xs font-semibold uppercase tracking-wide text-muted">Sources citées</dt>
          <dd className="mt-1 flex flex-wrap gap-1.5">
            {sources.map((s) => (
              <Badge key={s.n} tone="neutral">[{s.n}] {s.fichier ? fileLabel(s.fichier) : 'Document'}{s.page !== null ? `, p. ${s.page}` : ''}</Badge>
            ))}
          </dd>
        </div>
      )}
    </motion.dl>
  )
}

export default function Audit() {
  const { data, error, loading, reload } = useAsync(() => api.auditRecent(200), [])
  const [type, setType] = useState<string>('all')
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState<number | null>(null)

  const types = useMemo(() => {
    const c: Record<string, number> = {}
    data?.forEach((e) => { c[e.event_type] = (c[e.event_type] ?? 0) + 1 })
    return Object.entries(c).sort((a, b) => b[1] - a[1])
  }, [data])

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase()
    return (data ?? []).filter(
      (e) => (type === 'all' || e.event_type === type) &&
        (!q || `${e.user_id ?? ''} ${e.question ?? ''} ${e.detail ?? ''}`.toLowerCase().includes(q)),
    )
  }, [data, type, query])

  return (
    <div className="h-full overflow-y-auto px-4 py-8 sm:px-8">
      <div className="mx-auto max-w-6xl">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight">Journal d'audit</h2>
            <p className="mt-1 text-sm text-muted">Derniers événements de votre organisation (réservé à la Direction).</p>
          </div>
          <div className="flex items-center gap-2">
            <div className="relative w-64">
              <Icon name="search" size={16} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-muted" />
              <input className="field !pl-10" placeholder="Utilisateur, question…" aria-label="Filtrer le journal" value={query} onChange={(e) => setQuery(e.target.value)} />
            </div>
            <button type="button" onClick={reload} aria-label="Actualiser" className="rounded-xl border border-line bg-surface/70 p-3 text-muted hover:text-ink"><Icon name="refresh" size={16} /></button>
          </div>
        </div>

        <div className="mt-5 flex flex-wrap gap-2">
          <button type="button" onClick={() => setType('all')} className={`rounded-full px-3.5 py-1.5 text-sm transition ${type === 'all' ? 'bg-brand text-white dark:text-slate-950' : 'border border-line bg-surface/70 text-muted hover:text-ink'}`}>
            Tous ({data?.length ?? 0})
          </button>
          {types.map(([t, n]) => (
            <button key={t} type="button" onClick={() => setType(t)} className={`rounded-full px-3.5 py-1.5 text-sm transition ${type === t ? 'bg-brand text-white dark:text-slate-950' : 'border border-line bg-surface/70 text-muted hover:text-ink'}`}>
              {eventMeta(t).label} ({n})
            </button>
          ))}
        </div>

        {error && <div className="mt-6"><ErrorBox message={error.message} onRetry={reload} /></div>}

        <div className="card mt-6 divide-y divide-line overflow-hidden">
          {loading && !data && [0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="m-3 h-12" />)}
          {data && rows.length === 0 && <p className="p-8 text-center text-sm text-muted">Aucun événement ne correspond.</p>}
          {rows.map((e, i) => {
            const ev = eventMeta(e.event_type)
            const expanded = open === e.id
            return (
              <motion.div key={e.id} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.2, delay: Math.min(i, 12) * 0.02 }}>
                <button
                  type="button" aria-expanded={expanded} onClick={() => setOpen(expanded ? null : e.id)}
                  className="flex w-full flex-wrap items-center gap-x-4 gap-y-1.5 px-4 py-3 text-left transition hover:bg-brand/5"
                >
                  <span className="w-32 shrink-0 text-xs tabular-nums text-muted">{formatDateTime(e.ts)}</span>
                  <Badge tone={ev.tone} className="w-40 justify-center">{ev.label}</Badge>
                  <span className="w-28 shrink-0 truncate text-sm font-medium">{e.user_id ?? '—'}</span>
                  <span className="hidden w-32 shrink-0 text-xs text-muted md:inline">{e.role ? roleLabel(e.role) : '—'}</span>
                  {e.mode && <Badge tone={modeMeta(e.mode).tone} className="hidden lg:inline-flex">{modeMeta(e.mode).label}</Badge>}
                  <span className="min-w-[10rem] flex-1 truncate text-sm text-muted">{e.question ?? e.detail ?? ''}</span>
                  <span className="w-16 shrink-0 text-right text-xs tabular-nums text-muted">{formatMs(e.latency_ms)}</span>
                  <Icon name="chevron" size={15} className={`shrink-0 text-muted transition-transform ${expanded ? 'rotate-90' : ''}`} />
                </button>
                <AnimatePresence initial={false}>{expanded && <Detail e={e} />}</AnimatePresence>
              </motion.div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
