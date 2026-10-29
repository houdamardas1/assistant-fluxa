import type { ReactNode } from 'react'
import type { Tone } from '../../lib/format'

const TONES: Record<Tone, string> = {
  ok: 'bg-ok/10 text-ok ring-ok/25',
  info: 'bg-info/10 text-info ring-info/25',
  warn: 'bg-warn/10 text-warn ring-warn/25',
  danger: 'bg-danger/10 text-danger ring-danger/25',
  plum: 'bg-plum/10 text-plum ring-plum/25',
  neutral: 'bg-muted/10 text-muted ring-muted/25',
}

export function Badge({ tone = 'neutral', children, className = '' }: { tone?: Tone; children: ReactNode; className?: string }) {
  return (
    <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${TONES[tone]} ${className}`}>
      {children}
    </span>
  )
}
