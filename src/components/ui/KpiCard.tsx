import { motion } from 'framer-motion'
import { useCountUp } from '../../hooks/useCountUp'
import { Icon, type IconName } from './Icons'

export function KpiCard({
  label, value, suffix, hint, icon, delay = 0,
}: {
  label: string
  value: number | null
  suffix?: string
  hint?: string
  icon: IconName
  delay?: number
}) {
  const n = useCountUp(value ?? 0)
  return (
    <motion.div
      className="card p-5"
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, delay }}
    >
      <div className="flex items-center justify-between">
        <span className="text-sm text-muted">{label}</span>
        <span className="grid h-9 w-9 place-items-center rounded-xl bg-brand/10 text-brand">
          <Icon name={icon} size={18} />
        </span>
      </div>
      <div className="mt-3 text-3xl font-semibold tabular-nums tracking-tight">
        {value === null ? '—' : n.toLocaleString('fr-FR')}
        {value !== null && suffix && <span className="ml-1 text-base font-medium text-muted">{suffix}</span>}
      </div>
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
    </motion.div>
  )
}
