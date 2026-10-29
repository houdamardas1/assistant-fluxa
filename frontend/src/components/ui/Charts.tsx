import { useState } from 'react'
import { motion } from 'framer-motion'

export const PALETTE = [
  'rgb(var(--brand))', 'rgb(var(--gold))', 'rgb(var(--info))', 'rgb(var(--plum))', 'rgb(var(--danger))',
]

export function HBarChart({ data, unit = '' }: { data: { label: string; value: number }[]; unit?: string }) {
  const max = Math.max(1, ...data.map((d) => d.value))
  if (data.length === 0) return <p className="text-sm text-muted">Aucune donnée.</p>
  return (
    <ul className="space-y-3">
      {data.map((d, i) => (
        <li key={d.label}>
          <div className="flex items-baseline justify-between gap-3 text-sm">
            <span className="truncate">{d.label}</span>
            <span className="shrink-0 tabular-nums text-muted">{d.value.toLocaleString('fr-FR')}{unit}</span>
          </div>
          <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-line/70">
            <motion.div
              className="h-full rounded-full"
              style={{ background: `linear-gradient(90deg, ${PALETTE[0]}, ${PALETTE[1]})` }}
              initial={{ width: 0 }}
              animate={{ width: `${(d.value / max) * 100}%` }}
              transition={{ duration: 0.8, delay: i * 0.06, ease: 'easeOut' }}
            />
          </div>
        </li>
      ))}
    </ul>
  )
}

export function Donut({
  data, centerValue, centerLabel,
}: {
  data: { label: string; value: number }[]
  centerValue: string
  centerLabel: string
}) {
  const total = data.reduce((a, d) => a + d.value, 0)
  const r = 56
  const c = 2 * Math.PI * r
  let offset = 0
  const segments = data.map((d, i) => {
    const len = total > 0 ? (d.value / total) * c : 0
    const seg = { ...d, len, offset, color: PALETTE[i % PALETTE.length] }
    offset += len
    return seg
  })

  return (
    <div className="flex flex-wrap items-center gap-6">
      <div className="relative h-40 w-40 shrink-0">
        <svg viewBox="0 0 160 160" className="h-full w-full -rotate-90">
          <circle cx="80" cy="80" r={r} fill="none" strokeWidth="18" style={{ stroke: 'rgb(var(--line))' }} />
          {segments.map((s, i) => (
            <motion.circle
              key={s.label}
              cx="80" cy="80" r={r} fill="none" strokeWidth="18"
              style={{ stroke: s.color }}
              strokeDashoffset={-s.offset}
              initial={{ strokeDasharray: `0 ${c}` }}
              animate={{ strokeDasharray: `${Math.max(s.len - 2, 0)} ${c - Math.max(s.len - 2, 0)}` }}
              transition={{ duration: 0.9, delay: 0.1 + i * 0.12, ease: 'easeOut' }}
            />
          ))}
        </svg>
        <div className="absolute inset-0 grid place-items-center text-center">
          <div>
            <div className="text-2xl font-semibold tabular-nums">{centerValue}</div>
            <div className="text-xs text-muted">{centerLabel}</div>
          </div>
        </div>
      </div>
      <ul className="min-w-0 flex-1 space-y-2 text-sm">
        {segments.map((s) => (
          <li key={s.label} className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: s.color }} />
            <span className="truncate">{s.label}</span>
            <span className="ml-auto tabular-nums text-muted">{s.value.toLocaleString('fr-FR')}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function AreaChart({ points }: { points: { label: string; value: number }[] }) {
  const [hover, setHover] = useState<number | null>(null)
  const W = 640, H = 220
  const pad = { l: 34, r: 14, t: 14, b: 28 }
  const top = Math.max(4, Math.ceil(Math.max(0, ...points.map((p) => p.value)) / 4) * 4)
  const x = (i: number) => pad.l + (points.length <= 1 ? 0 : (i * (W - pad.l - pad.r)) / (points.length - 1))
  const y = (v: number) => pad.t + (1 - v / top) * (H - pad.t - pad.b)

  const line = points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)} ${y(p.value).toFixed(1)}`).join(' ')
  const baseY = H - pad.b
  const area = points.length
    ? `${line} L${x(points.length - 1).toFixed(1)} ${baseY} L${x(0).toFixed(1)} ${baseY} Z`
    : ''
  const step = Math.max(1, Math.ceil(points.length / 7))
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => Math.round(t * top))

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Évolution quotidienne du nombre de requêtes">
        <defs>
          <linearGradient id="area-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" style={{ stopColor: 'rgb(var(--brand))', stopOpacity: 0.35 }} />
            <stop offset="1" style={{ stopColor: 'rgb(var(--brand))', stopOpacity: 0 }} />
          </linearGradient>
        </defs>

        {ticks.map((t) => (
          <g key={t}>
            <line x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} strokeDasharray="3 5" style={{ stroke: 'rgb(var(--line))' }} />
            <text x={pad.l - 8} y={y(t) + 4} textAnchor="end" fontSize="10" style={{ fill: 'rgb(var(--muted))' }}>{t}</text>
          </g>
        ))}

        {points.map((p, i) =>
          i % step === 0 ? (
            <text key={p.label} x={x(i)} y={H - 8} textAnchor="middle" fontSize="10" style={{ fill: 'rgb(var(--muted))' }}>
              {p.label}
            </text>
          ) : null,
        )}

        {area && (
          <motion.path d={area} fill="url(#area-fill)" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.8, delay: 0.5 }} />
        )}
        {line && (
          <motion.path
            d={line} fill="none" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
            style={{ stroke: 'rgb(var(--brand))' }}
            initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1.2, ease: 'easeInOut' }}
          />
        )}

        {points.map((p, i) => (
          <g key={`pt-${p.label}`} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
            <rect x={x(i) - (W - pad.l - pad.r) / Math.max(points.length - 1, 1) / 2} y={pad.t} width={(W - pad.l - pad.r) / Math.max(points.length - 1, 1)} height={H - pad.t - pad.b} fill="transparent" />
            <circle cx={x(i)} cy={y(p.value)} r={hover === i ? 5 : 3} style={{ fill: 'rgb(var(--surface))', stroke: 'rgb(var(--brand))' }} strokeWidth="2" />
          </g>
        ))}
      </svg>

      {hover !== null && points[hover] && (
        <div
          className="pointer-events-none absolute -translate-x-1/2 -translate-y-full rounded-lg border border-line bg-surface px-2.5 py-1.5 text-xs shadow-soft"
          style={{ left: `${(x(hover) / W) * 100}%`, top: `${(y(points[hover].value) / H) * 100}%` }}
        >
          <div className="font-medium">{points[hover].label}</div>
          <div className="tabular-nums text-muted">{points[hover].value} requête(s)</div>
        </div>
      )}
    </div>
  )
}
