import { useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useAsync } from '../hooks/useAsync'
import { api } from '../lib/api'
import { cleanName, fileLabel, roleLabel, TYPE_LABELS } from '../lib/format'
import { Badge } from '../components/ui/Badge'
import { Icon } from '../components/ui/Icons'
import { ErrorBox, Skeleton } from '../components/ui/Skeleton'

type Filter = 'all' | 'entreprise' | 'public_reglementaire'

const FILTERS: { id: Filter; label: string }[] = [
  { id: 'all', label: 'Tous' },
  { id: 'entreprise', label: "Documents d'entreprise" },
  { id: 'public_reglementaire', label: 'Textes réglementaires' },
]

export default function Documents() {
  const { data, error, loading, reload } = useAsync(() => api.corpusStats(), [])
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<Filter>('all')

  const files = useMemo(() => {
    const q = query.trim().toLowerCase()
    return (data?.files ?? []).filter(
      (f) =>
        (filter === 'all' || f.type === filter) &&
        (!q || `${f.file} ${f.entreprise ?? ''} ${f.departements.join(' ')}`.toLowerCase().includes(q)),
    )
  }, [data, query, filter])

  const maxChunks = Math.max(1, ...(data?.files ?? []).map((f) => f.chunks))

  return (
    <div className="h-full overflow-y-auto px-4 py-8 sm:px-8">
      <div className="mx-auto max-w-6xl">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight">Documents accessibles</h2>
            <p className="mt-1 text-sm text-muted">
              {data
                ? `${data.total_files} document(s) · ${data.total_chunks.toLocaleString('fr-FR')} passages indexés, dans la limite de votre profil.`
                : 'Chargement du catalogue…'}
            </p>
          </div>
          <div className="relative w-full sm:w-72">
            <Icon name="search" size={16} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-muted" />
            <input className="field !pl-10" placeholder="Rechercher un document…" aria-label="Rechercher un document" value={query} onChange={(e) => setQuery(e.target.value)} />
          </div>
        </div>

        <div className="mt-5 flex flex-wrap gap-2" role="tablist" aria-label="Filtrer par type">
          {FILTERS.map((f) => (
            <button
              key={f.id} type="button" role="tab" aria-selected={filter === f.id} onClick={() => setFilter(f.id)}
              className={`rounded-full px-4 py-1.5 text-sm transition ${filter === f.id ? 'bg-brand text-white dark:text-slate-950' : 'border border-line bg-surface/70 text-muted hover:text-ink'}`}
            >
              {f.label}
            </button>
          ))}
        </div>

        {error && <div className="mt-6"><ErrorBox message={error.message} onRetry={reload} /></div>}

        <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {loading && !data && [0, 1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-44" />)}
          <AnimatePresence mode="popLayout">
            {files.map((f, i) => (
              <motion.article
                key={f.file} layout className="card flex flex-col p-5"
                initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, scale: 0.96 }}
                transition={{ duration: 0.3, delay: Math.min(i, 9) * 0.04 }} whileHover={{ y: -3 }}
              >
                <div className="flex items-start gap-3">
                  <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-brand/10 text-brand"><Icon name="file" size={19} /></span>
                  <div className="min-w-0">
                    <h3 className="truncate font-semibold" title={f.file}>{fileLabel(f.file)}</h3>
                    <p className="truncate text-xs text-muted">{f.file}</p>
                  </div>
                </div>

                <div className="mt-4 flex flex-wrap gap-1.5">
                  <Badge tone="plum">{TYPE_LABELS[f.type] ?? f.type}</Badge>
                  {f.entreprise && <Badge tone="neutral">{cleanName(f.entreprise)}</Badge>}
                  {f.departements.map((d) => <Badge key={d} tone="info">{roleLabel(d)}</Badge>)}
                  {f.demo && <Badge tone="warn">Démonstration</Badge>}
                </div>

                <div className="mt-auto pt-5">
                  <div className="flex items-baseline justify-between text-xs text-muted">
                    <span><span className="text-sm font-semibold tabular-nums text-ink">{f.chunks.toLocaleString('fr-FR')}</span> passages</span>
                    {f.max_page > 0 && <span>jusqu'à la page {f.max_page}</span>}
                  </div>
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-line/70">
                    <motion.div className="h-full rounded-full bg-brand" initial={{ width: 0 }} animate={{ width: `${(f.chunks / maxChunks) * 100}%` }} transition={{ duration: 0.7, delay: 0.15 }} />
                  </div>
                </div>
              </motion.article>
            ))}
          </AnimatePresence>
        </div>

        {data && files.length === 0 && (
          <p className="mt-10 text-center text-sm text-muted">
            {data.total_files === 0 ? 'Aucun document n’est accessible avec votre profil.' : 'Aucun document ne correspond à votre recherche.'}
          </p>
        )}
      </div>
    </div>
  )
}
