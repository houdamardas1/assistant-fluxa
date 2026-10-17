import type { ReactNode } from 'react'
import { motion } from 'framer-motion'
import { useAuth } from '../context/AuthContext'
import { useAsync } from '../hooks/useAsync'
import { api } from '../lib/api'
import { cleanName, DEPT_LABELS, eventMeta, firstName, formatDay, roleLabel, TYPE_LABELS } from '../lib/format'
import { Badge } from '../components/ui/Badge'
import { AreaChart, Donut, HBarChart } from '../components/ui/Charts'
import { KpiCard } from '../components/ui/KpiCard'
import { Icon } from '../components/ui/Icons'
import { ErrorBox, Skeleton } from '../components/ui/Skeleton'

function Section({ title, subtitle, children, delay = 0, className = '' }: {
  title: string; subtitle?: string; children: ReactNode; delay?: number; className?: string
}) {
  return (
    <motion.section className={`card p-5 ${className}`} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45, delay }}>
      <h3 className="font-semibold">{title}</h3>
      {subtitle && <p className="mt-0.5 text-xs text-muted">{subtitle}</p>}
      <div className="mt-4">{children}</div>
    </motion.section>
  )
}

export default function Dashboard() {
  const { user } = useAuth()
  const direction = user?.role === 'direction'

  const stats = useAsync(() => api.corpusStats(), [])
  const history = useAsync(() => api.history(200), [])
  const summary = useAsync(() => (direction ? api.auditSummary() : Promise.resolve(null)), [direction])
  const series = useAsync(() => (direction ? api.auditTimeseries(14) : Promise.resolve(null)), [direction])

  const s = stats.data
  const answered = history.data?.filter((h) => h.event_type === 'ACCESS_GRANTED').length ?? 0
  const refused = history.data?.filter((h) => h.event_type === 'ACCESS_DENIED').length ?? 0
  const requests14 = series.data?.days.reduce((a, d) => a + d.requests, 0) ?? 0
  const sum = summary.data

  return (
    <div className="h-full overflow-y-auto px-4 py-8 sm:px-8">
      <div className="mx-auto max-w-6xl space-y-6">
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
          <h2 className="text-2xl font-semibold tracking-tight">Bonjour {user ? firstName(user.display_name) : ''}</h2>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-muted">
            <Badge tone="ok">{roleLabel(user?.role)}</Badge>
            <span>Organisation : <span className="font-medium text-ink">{user?.tenant_id}</span></span>
            <span>· Données issues de l'index et du journal d'audit en temps réel.</span>
          </div>
        </motion.div>

        {stats.error && <ErrorBox message={stats.error.message} onRetry={stats.reload} />}

        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {stats.loading && !s ? (
            [0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-32" />)
          ) : s ? (
            <>
              <KpiCard label="Documents accessibles" value={s.total_files} icon="file" hint={`jusqu'à ${s.total_pages.toLocaleString('fr-FR')} pages`} />
              <KpiCard label="Passages indexés" value={s.total_chunks} icon="database" delay={0.05} hint="extraits interrogeables" />
              <KpiCard label="Mes questions" value={history.data ? answered + refused : null} icon="chat" delay={0.1} hint={history.data ? `dont ${refused} refusée(s)` : undefined} />
              {direction ? (
                <KpiCard label="Requêtes (14 jours)" value={series.data ? requests14 : null} icon="activity" delay={0.15} hint="toute l'organisation" />
              ) : (
                <KpiCard label="Entreprises couvertes" value={s.by_company.length} icon="shield" delay={0.15} hint="dans votre périmètre" />
              )}
            </>
          ) : null}
        </div>

        {direction && (
          <>
            {(summary.error || series.error) && (
              <ErrorBox message={(summary.error ?? series.error)!.message} onRetry={() => { summary.reload(); series.reload() }} />
            )}
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <KpiCard label="Accès refusés" value={sum ? sum.counts.ACCESS_DENIED ?? 0 : null} icon="shield" hint="tentatives hors périmètre" />
              <KpiCard label="Sans réponse" value={sum ? sum.counts.NO_ANSWER ?? 0 : null} icon="alert" delay={0.05} hint="information absente" />
              <KpiCard label="Latence moyenne" value={sum?.latency.avg_ms ?? null} suffix="ms" icon="clock" delay={0.1} hint={sum ? `sur ${sum.latency.n} requêtes` : undefined} />
              <KpiCard label="Latence p95" value={sum?.latency.p95_ms ?? null} suffix="ms" icon="clock" delay={0.15} hint="95 % des requêtes plus rapides" />
            </div>

            <Section title="Activité des 14 derniers jours" subtitle="Requêtes traitées par jour (UTC)" delay={0.1}>
              {series.loading && !series.data ? <Skeleton className="h-52" /> : series.data ? (
                <AreaChart points={series.data.days.map((d) => ({ label: formatDay(d.day), value: d.requests }))} />
              ) : null}
            </Section>

            <div className="grid gap-4 lg:grid-cols-2">
              <Section title="Issue des requêtes" subtitle="Tous événements du journal" delay={0.15}>
                {sum ? (
                  <HBarChart
                    data={Object.entries(sum.counts)
                      .map(([k, v]) => ({ label: eventMeta(k).label, value: v }))
                      .sort((a, b) => b.value - a.value)}
                  />
                ) : <Skeleton className="h-40" />}
              </Section>
              <Section title="Requêtes par profil" subtitle="Rôle de l'utilisateur" delay={0.2}>
                {sum ? (
                  <HBarChart data={Object.entries(sum.by_role).map(([k, v]) => ({ label: roleLabel(k), value: v }))} />
                ) : <Skeleton className="h-40" />}
              </Section>
            </div>
          </>
        )}

        {s && (
          <div className="grid gap-4 lg:grid-cols-2">
            <Section title="Passages indexés par entreprise" subtitle="Documents d'entreprise de votre périmètre" delay={0.1}>
              <HBarChart data={s.by_company.map((c) => ({ label: cleanName(c.name), value: c.chunks }))} />
            </Section>
            <Section title="Types de documents" subtitle="Nombre de documents accessibles" delay={0.15}>
              <Donut
                data={s.by_type.map((t) => ({ label: TYPE_LABELS[t.type] ?? t.type, value: t.files }))}
                centerValue={String(s.total_files)} centerLabel="documents"
              />
            </Section>
            <Section title="Couverture par département" subtitle="Passages rattachés à chaque département" delay={0.2} className="lg:col-span-2">
              <HBarChart data={s.by_department.map((d) => ({ label: DEPT_LABELS[d.name] ?? d.name, value: d.chunks }))} />
            </Section>
          </div>
        )}

        {!direction && (
          <div className="flex items-start gap-3 rounded-2xl border border-line bg-surface/60 p-4 text-sm text-muted">
            <Icon name="lock" size={16} className="mt-0.5 shrink-0" />
            Les indicateurs d'activité de l'organisation (requêtes, refus, latence) sont réservés au profil Direction.
          </div>
        )}
      </div>
    </div>
  )
}
