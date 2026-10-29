import { motion } from 'framer-motion'
import { useChat } from '../../context/ChatContext'
import { useAsync } from '../../hooks/useAsync'
import { api } from '../../lib/api'
import { formatRelative, modeMeta } from '../../lib/format'
import { Badge } from '../ui/Badge'
import { Icon } from '../ui/Icons'
import { ErrorBox, Skeleton } from '../ui/Skeleton'

/** Historique REEL de l'utilisateur (GET /me/history) : jamais celui d'un autre compte. */
export function HistoryPanel() {
  const { historyVersion, restore } = useChat()
  const { data, error, loading, reload } = useAsync(() => api.history(40), [historyVersion])

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between px-4 py-4">
        <h2 className="text-sm font-semibold">Mon historique</h2>
        <button type="button" onClick={reload} aria-label="Actualiser l'historique" className="rounded-lg p-1.5 text-muted hover:bg-line/60 hover:text-ink">
          <Icon name="refresh" size={15} />
        </button>
      </div>

      <div className="flex-1 space-y-2 overflow-y-auto px-3 pb-4">
        {loading && !data && [0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-16" />)}
        {error && <ErrorBox message={error.message} onRetry={reload} />}
        {data && data.length === 0 && (
          <p className="px-2 py-6 text-center text-sm text-muted">Aucune question pour l'instant.</p>
        )}
        {data?.map((item, i) => {
          const meta = modeMeta(item.mode)
          return (
            <motion.button
              key={item.request_id} type="button" onClick={() => restore(item)}
              className="w-full rounded-xl border border-line bg-surface/60 p-3 text-left transition hover:border-brand/50 hover:bg-brand/5"
              initial={{ opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.25, delay: Math.min(i, 8) * 0.04 }}
            >
              <div className="line-clamp-2 text-sm">{item.question ?? '—'}</div>
              <div className="mt-2 flex items-center justify-between gap-2">
                <Badge tone={meta.tone}>{meta.label}</Badge>
                <span className="text-xs text-muted">{formatRelative(item.ts)}</span>
              </div>
            </motion.button>
          )
        })}
      </div>
    </div>
  )
}
