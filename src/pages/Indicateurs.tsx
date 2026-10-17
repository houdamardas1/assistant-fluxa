import { useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useAsync } from '../hooks/useAsync'
import { api } from '../lib/api'
import { fileLabel } from '../lib/format'
import type { Tone } from '../lib/format'
import type { KpiItem, KpiPerimetre } from '../lib/types'
import { Badge } from '../components/ui/Badge'
import { Icon } from '../components/ui/Icons'
import { ErrorBox, Skeleton } from '../components/ui/Skeleton'

const PERIMETRES: Record<KpiPerimetre, { label: string; tone: Tone }> = {
  social: { label: 'Comptes sociaux', tone: 'neutral' },
  consolide: { label: 'Consolid\u00e9', tone: 'info' },
  non_precise: { label: 'P\u00e9rim\u00e8tre non pr\u00e9cis\u00e9', tone: 'warn' },
}

function formatValue(v: number): string {
  return v.toLocaleString('fr-FR', { maximumFractionDigits: 3 })
}

function formatVariation(v: number): string {
  const s = Math.abs(v).toLocaleString('fr-FR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
  return (v > 0 ? '+' : v < 0 ? '\u2212' : '') + s + ' %'
}

function FilterRow({
  label, value, onChange, options, all,
}: { label: string; value: string; onChange: (v: string) => void; options: string[]; all: string }) {
  const items = [{ id: 'all', label: all }, ...options.map((o) => ({ id: o, label: o }))]
  return (
    <div className="mt-4 flex flex-wrap gap-2" role="tablist" aria-label={label}>
      {items.map((f) => (
        <button
          key={f.id} type="button" role="tab" aria-selected={value === f.id} onClick={() => onChange(f.id)}
          className={`rounded-full px-4 py-1.5 text-sm transition ${value === f.id ? 'bg-brand text-white dark:text-slate-950' : 'border border-line bg-surface/70 text-muted hover:text-ink'}`}
        >
          {f.label}
        </button>
      ))}
    </div>
  )
}

function Tile({ k, index }: { k: KpiItem; index: number }) {
  const per = PERIMETRES[k.perimetre] ?? PERIMETRES.non_precise
  const v = k.variation_pct
  return (
    <motion.article
      layout className="card flex flex-col p-5"
      initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, scale: 0.96 }}
      transition={{ duration: 0.3, delay: Math.min(index, 9) * 0.04 }} whileHover={{ y: -3 }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h4 className="text-sm text-muted">{k.libelle}</h4>
          <p className="text-xs text-muted">Exercice {k.annee}</p>
        </div>
        {k.verifie && <Badge tone="ok">Donn\u00e9e v\u00e9rifi\u00e9e</Badge>}
      </div>

      <div className="mt-3 text-3xl font-semibold tabular-nums tracking-tight">
        {formatValue(k.valeur)}
        <span className="ml-1 text-base font-medium text-muted">{k.unite}</span>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <Badge tone={per.tone}>{per.label}</Badge>
        {v !== null && k.annee_precedente !== null && (
          <Badge tone={v >= 0 ? 'ok' : 'danger'}>
            <span aria-hidden="true">{v >= 0 ? '\u25b2' : '\u25bc'}</span>
            {formatVariation(v)} vs {k.annee_precedente}
          </Badge>
        )}
      </div>

      {k.avertissement && <p className="mt-3 text-xs text-warn">{k.avertissement}</p>}

      <p className="mt-auto pt-4 text-xs text-muted" title={k.document}>
        <Icon name="file" size={13} className="mr-1 inline align-[-2px]" />
        {fileLabel(k.document)} \u00b7 page {k.page}
      </p>
    </motion.article>
  )
}

export default function Indicateurs() {
  const { data, error, loading, reload } = useAsync(() => api.kpi(), [])
  const [entreprise, setEntreprise] = useState('all')
  const [indicateur, setIndicateur] = useState('all')

  const items = useMemo(() => data ?? [], [data])
  const entreprises = useMemo(() => Array.from(new Set(items.map((k) => k.entreprise))), [items])
  const indicateurs = useMemo(() => Array.from(new Set(items.map((k) => k.libelle))), [items])

  const groupes = useMemo(() => {
    const m = new Map<string, KpiItem[]>()
    items
      .filter((k) => (entreprise === 'all' || k.entreprise === entreprise) && (indicateur === 'all' || k.libelle === indicateur))
      .forEach((k) => m.set(k.entreprise, [...(m.get(k.entreprise) ?? []), k]))
    return Array.from(m.entries())
  }, [items, entreprise, indicateur])

  return (
    <div className="h-full overflow-y-auto px-4 py-8 sm:px-8">
      <div className="mx-auto max-w-6xl">
        <h2 className="text-2xl font-semibold tracking-tight">Indicateurs v\u00e9rifi\u00e9s</h2>
        <p className="mt-1 text-sm text-muted">
          {data
            ? `${data.length} indicateur(s) \u00b7 valeurs relev\u00e9es dans les documents, dans la limite de votre profil.`
            : 'Chargement des indicateurs\u2026'}
        </p>

        {entreprises.length > 1 && (
          <FilterRow label="Filtrer par entreprise" value={entreprise} onChange={setEntreprise} options={entreprises} all="Toutes les entreprises" />
        )}
        {indicateurs.length > 1 && (
          <FilterRow label="Filtrer par indicateur" value={indicateur} onChange={setIndicateur} options={indicateurs} all="Tous les indicateurs" />
        )}

        {error && <div className="mt-6"><ErrorBox message={error.message} onRetry={reload} /></div>}

        {loading && !data && (
          <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {[0, 1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-44" />)}
          </div>
        )}

        {groupes.map(([nom, liste]) => (
          <section key={nom} className="mt-8" aria-label={nom}>
            <h3 className="mb-3 text-lg font-semibold tracking-tight">{nom}</h3>
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              <AnimatePresence mode="popLayout">
                {liste.map((k, i) => <Tile key={k.id} k={k} index={i} />)}
              </AnimatePresence>
            </div>
          </section>
        ))}

        {data && groupes.length === 0 && (
          <p className="mt-10 text-center text-sm text-muted">
            {data.length === 0
              ? 'Aucun indicateur n\u2019est accessible avec votre profil.'
              : 'Aucun indicateur ne correspond \u00e0 ces filtres.'}
          </p>
        )}

        {data && data.length > 0 && (
          <p className="mt-10 text-xs text-muted">
            Chaque valeur est reprise du document et de la page indiqu\u00e9s, et contr\u00f4l\u00e9e dans le texte de cette page.
            La variation n\u2019est calcul\u00e9e qu\u2019entre deux exercices de m\u00eame p\u00e9rim\u00e8tre pr\u00e9cis\u00e9.
          </p>
        )}
      </div>
    </div>
  )
}
