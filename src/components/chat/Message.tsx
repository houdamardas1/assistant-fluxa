import { useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { useTypewriter } from '../../hooks/useTypewriter'
import { useElapsed } from '../../hooks/useElapsed'
import { cleanName, fileLabel, formatMs, modeMeta, roleLabel, TYPE_LABELS } from '../../lib/format'
import type { AskResponse, Mode, Source } from '../../lib/types'
import { Badge } from '../ui/Badge'
import { Icon, LogoMark, type IconName } from '../ui/Icons'

// ---------------------------------------------------------------- citations

type Part = { type: 'text'; value: string } | { type: 'cite'; nums: number[] }
const CITATION = /\[(?:Sources?\s*)?\d{1,2}(?:\s*(?:,|;|et|&)\s*(?:Sources?\s*)?\d{1,2})*\]/gi

export function parseCitations(text: string): Part[] {
  const out: Part[] = []
  let last = 0
  for (const m of text.matchAll(CITATION)) {
    const index = m.index ?? 0
    if (index > last) out.push({ type: 'text', value: text.slice(last, index) })
    out.push({ type: 'cite', nums: (m[0].match(/\d+/g) ?? []).map(Number) })
    last = index + m[0].length
  }
  if (last < text.length) out.push({ type: 'text', value: text.slice(last) })
  return out
}

function AnswerText({ text, caret, onCite }: { text: string; caret: boolean; onCite: (n: number) => void }) {
  // masque une citation "[Sour" coupee en cours de frappe
  const visible = text.replace(/\[[^\]]*$/, '')
  const parts = useMemo(() => parseCitations(visible), [visible])
  return (
    <div className="whitespace-pre-wrap break-words text-[15px] leading-relaxed" data-testid="answer-text">
      {parts.map((p, i) =>
        p.type === 'text' ? (
          <span key={i}>{p.value}</span>
        ) : (
          <span key={i} className="mx-0.5 inline-flex gap-0.5 align-baseline">
            {p.nums.map((n) => (
              <button
                key={n} type="button" onClick={() => onCite(n)} aria-label={`Voir la source ${n}`}
                className="rounded-md bg-brand/15 px-1.5 text-xs font-semibold text-brand transition hover:bg-brand/30"
              >
                {n}
              </button>
            ))}
          </span>
        ),
      )}
      {caret && <span className="ml-0.5 inline-block h-4 w-[2px] translate-y-0.5 animate-caret bg-brand" />}
    </div>
  )
}

// ------------------------------------------------------------ sous-elements

function ConfidenceRing({ value, grounded }: { value: number; grounded: boolean }) {
  const r = 11
  const c = 2 * Math.PI * r
  const pct = Math.round(Math.min(Math.max(value, 0), 1) * 100)
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-muted" title={grounded
        ? "Score de fondement : part des affirmations citées dont les chiffres figurent dans les extraits cités (calculé, non estimé par le modèle)"
        : "Confiance du vérificateur (estimée par le modèle)"}>
      <svg width="28" height="28" viewBox="0 0 28 28" className="-rotate-90">
        <circle cx="14" cy="14" r={r} fill="none" strokeWidth="3" style={{ stroke: 'rgb(var(--line))' }} />
        <motion.circle
          cx="14" cy="14" r={r} fill="none" strokeWidth="3" strokeLinecap="round"
          strokeDasharray={c} style={{ stroke: 'rgb(var(--ok))' }}
          initial={{ strokeDashoffset: c }} animate={{ strokeDashoffset: c * (1 - pct / 100) }}
          transition={{ duration: 0.9, ease: 'easeOut' }}
        />
      </svg>
      <span className="tabular-nums">{grounded ? 'Fondement ' : ''}{pct} %</span>
    </span>
  )
}

function VerifiedBadge() {
  return (
    <span
      className="inline-flex items-center gap-1 text-xs font-medium"
      style={{ color: 'rgb(var(--ok))' }}
      title="Valeur issue de la base de KPI vérifiée, sans appel au modèle de génération"
    >
      <Icon name="check" size={13} />
      Donnée vérifiée
    </span>
  )
}

function SourceCard({ source, domId, highlighted, index }: { source: Source; domId: string; highlighted: boolean; index: number }) {
  return (
    <motion.li
      id={domId}
      className={`rounded-xl border p-3 text-sm transition-colors ${highlighted ? 'border-brand bg-brand/10' : 'border-line bg-bg/50'}`}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0, scale: highlighted ? 1.015 : 1 }}
      transition={{ duration: 0.3, delay: 0.05 * index }}
    >
      <div className="flex items-start gap-3">
        <span className="grid h-6 w-6 shrink-0 place-items-center rounded-lg bg-brand/15 text-xs font-bold text-brand">{source.n}</span>
        <div className="min-w-0 flex-1">
          <div className="truncate font-medium">{source.fichier ? fileLabel(source.fichier) : 'Document'}</div>
          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted">
            {source.page !== null && <span>Page {source.page}</span>}
            {source.entreprise && <Badge tone="neutral">{cleanName(source.entreprise)}</Badge>}
            {source.type && <Badge tone="plum">{TYPE_LABELS[source.type] ?? source.type}</Badge>}
            {source.verifie && <Badge tone="neutral">Valeur vérifiée</Badge>}
            {source.demo && <Badge tone="warn">Donnée de démonstration</Badge>}
          </div>
        </div>
      </div>
    </motion.li>
  )
}

const SPECIAL: Partial<Record<Mode, { panel: string; icon: IconName; iconClass: string }>> = {
  ABSENT: { panel: 'border-warn/30 bg-warn/5', icon: 'alert', iconClass: 'text-warn' },
  HORS_PERIMETRE: { panel: 'border-danger/30 bg-danger/5', icon: 'lock', iconClass: 'text-danger' },
  BLOQUE: { panel: 'border-danger/30 bg-danger/5', icon: 'shield', iconClass: 'text-danger' },
  CLARIFICATION: { panel: 'border-info/30 bg-info/5', icon: 'sparkles', iconClass: 'text-info' },
}

function Avatar() {
  return <div className="mt-0.5 shrink-0"><LogoMark size={32} /></div>
}

// ------------------------------------------------------------------ messages

export function UserMessage({ content }: { content: string }) {
  return (
    <motion.div className="flex justify-end" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}>
      <div className="max-w-[85%] whitespace-pre-wrap break-words rounded-2xl rounded-br-md bg-brand px-4 py-2.5 text-[15px] text-white shadow-soft dark:text-slate-950">
        {content}
      </div>
    </motion.div>
  )
}

export function AssistantMessage({
  msgId, result, latencyMs, animate,
}: { msgId: string; result: AskResponse; latencyMs: number | null; animate: boolean }) {
  const meta = modeMeta(result.mode)
  const verified = result.sources.length > 0 && result.sources.every((s) => s.verifie === true)
  const special = SPECIAL[result.mode]
  // Le titre du mode est deja affiche dans l'en-tete : on retire sa repetition
  // en tete du texte (la copie conserve la reponse complete).
  const [premiere, ...suite] = result.answer.split('\n')
  const texte = premiere.trim() === meta.label && suite.length > 0
    ? suite.join('\n').replace(/^\s+/, '')
    : result.answer
  const { shown, done } = useTypewriter(texte, animate)
  const [highlight, setHighlight] = useState<number | null>(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!copied) return
    const id = setTimeout(() => setCopied(false), 1600)
    return () => clearTimeout(id)
  }, [copied])

  const cite = (n: number) => {
    setHighlight(n)
    document.getElementById(`src-${msgId}-${n}`)?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(result.answer)
      setCopied(true)
    } catch {
      /* presse-papiers indisponible */
    }
  }

  return (
    <motion.div className="flex gap-3" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}>
      <Avatar />
      <div className="min-w-0 flex-1">
        <div className={`rounded-2xl rounded-tl-md border px-4 py-3 shadow-soft ${special ? special.panel : 'border-line bg-surface/80'}`}>
          {special && (
            <div className={`mb-2 flex items-center gap-2 text-sm font-semibold ${special.iconClass}`}>
              <Icon name={special.icon} size={16} />
              {meta.label}
            </div>
          )}
          <AnswerText text={shown} caret={!done} onCite={cite} />
        </div>

        {done && (
          <motion.div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-2 px-1" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.3 }}>
            {!special && <Badge tone={meta.tone}>{meta.label}</Badge>}
            {result.departement && <Badge tone="neutral">{roleLabel(result.departement)}</Badge>}
            {(result.mode === 'RAG' || result.mode === 'MULTI_INTENT') && (
              verified ? <VerifiedBadge /> : <ConfidenceRing value={result.fondement ?? result.confidence} grounded={result.fondement != null} />
            )}
            {latencyMs !== null && (
              <span className="inline-flex items-center gap-1 text-xs text-muted"><Icon name="clock" size={13} />{formatMs(latencyMs)}</span>
            )}
            <button type="button" onClick={copy} className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs text-muted hover:bg-line/60 hover:text-ink">
              <Icon name={copied ? 'check' : 'copy'} size={13} />
              {copied ? 'Copié' : 'Copier'}
            </button>
            <span className="text-xs text-muted/70" title="Référence de la requête (journal d'audit)">Réf. {result.request_id.slice(0, 8)}</span>
          </motion.div>
        )}

        {done && result.sources.length > 0 && (
          <div className="mt-3 px-1">
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
              Sources citées ({result.sources.length})
            </div>
            <ul className="grid gap-2 sm:grid-cols-2">
              {result.sources.map((s, i) => (
                <SourceCard key={s.n} source={s} index={i} domId={`src-${msgId}-${s.n}`} highlighted={highlight === s.n} />
              ))}
            </ul>
          </div>
        )}
      </div>
    </motion.div>
  )
}

export function ErrorMessage({ message }: { message: string }) {
  return (
    <motion.div className="flex gap-3" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}>
      <Avatar />
      <div role="alert" className="flex items-start gap-2 rounded-2xl rounded-tl-md border border-danger/30 bg-danger/5 px-4 py-3 text-sm text-danger">
        <Icon name="alert" size={16} className="mt-0.5 shrink-0" />
        <span>{message}</span>
      </div>
    </motion.div>
  )
}

export function TypingMessage({ startedAt, totalFiles }: { startedAt: number; totalFiles: number | null }) {
  const elapsed = useElapsed(startedAt)
  return (
    <motion.div className="flex gap-3" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }} aria-live="polite">
      <Avatar />
      <div className="rounded-2xl rounded-tl-md border border-line bg-surface/80 px-4 py-3 shadow-soft">
        <div className="flex items-center gap-3">
          <span className="flex gap-1" aria-hidden="true">
            {[0, 1, 2].map((i) => (
              <motion.span
                key={i} className="h-2 w-2 rounded-full bg-brand"
                animate={{ y: [0, -5, 0], opacity: [0.5, 1, 0.5] }}
                transition={{ duration: 0.9, repeat: Infinity, delay: i * 0.15 }}
              />
            ))}
          </span>
          <span className="text-sm text-muted">
            {totalFiles ? `Recherche dans vos ${totalFiles} documents autorisés…` : 'Recherche et vérification en cours…'}
          </span>
          <span className="text-xs tabular-nums text-muted/80">{elapsed} s</span>
        </div>
        {elapsed >= 20 && (
          <p className="mt-2 text-xs text-muted">La limite de débit du modèle peut allonger l'attente ; la requête est toujours en cours.</p>
        )}
      </div>
    </motion.div>
  )
}
