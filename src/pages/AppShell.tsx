import { useState } from 'react'
import { NavLink, useLocation, useOutlet } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { ChatProvider } from '../context/ChatContext'
import { useAuth } from '../context/AuthContext'
import { useHealth, type HealthState } from '../hooks/useHealth'
import { useTheme } from '../hooks/useTheme'
import { roleLabel } from '../lib/format'
import type { Role } from '../lib/types'
import { Badge } from '../components/ui/Badge'
import { Icon, LogoMark, type IconName } from '../components/ui/Icons'

interface NavItem {
  to: string
  label: string
  icon: IconName
  only?: Role
}

const NAV: NavItem[] = [
  { to: '/assistant', label: 'Assistant', icon: 'chat' },
  { to: '/tableau-de-bord', label: 'Tableau de bord', icon: 'chart' },
  { to: '/documents', label: 'Documents', icon: 'file' },
  { to: '/audit', label: "Journal d'audit", icon: 'shield', only: 'direction' },
]

const TITLES: Record<string, string> = Object.fromEntries(NAV.map((n) => [n.to, n.label]))

function SidebarNav({ items, variant, onNavigate }: { items: NavItem[]; variant: string; onNavigate?: () => void }) {
  return (
    <nav className="space-y-1" aria-label="Navigation principale">
      {items.map((it) => (
        <NavLink
          key={it.to} to={it.to} onClick={onNavigate}
          className="relative flex items-center rounded-xl px-3 py-2.5 text-sm font-medium text-muted transition hover:text-ink"
        >
          {({ isActive }) => (
            <>
              {isActive && (
                <motion.span
                  layoutId={`nav-active-${variant}`}
                  className="absolute inset-0 rounded-xl bg-brand/10 ring-1 ring-brand/25"
                  transition={{ type: 'spring', stiffness: 380, damping: 32 }}
                />
              )}
              <span className={`relative z-10 flex items-center gap-3 ${isActive ? 'text-brand' : ''}`}>
                <Icon name={it.icon} />
                {it.label}
              </span>
            </>
          )}
        </NavLink>
      ))}
    </nav>
  )
}

function Brand() {
  return (
    <div className="flex items-center gap-3 px-2">
      <LogoMark size={36} />
      <div className="leading-tight">
        <div className="text-sm font-semibold">Morocco Enterprise</div>
        <div className="text-sm font-semibold text-brand">Intelligence</div>
      </div>
    </div>
  )
}

function HealthPill({ state }: { state: HealthState }) {
  const map: Record<HealthState, { dot: string; label: string; ping: boolean }> = {
    online: { dot: 'bg-ok', label: 'API en ligne', ping: true },
    degraded: { dot: 'bg-warn', label: 'Index non chargé', ping: false },
    offline: { dot: 'bg-danger', label: 'API hors ligne', ping: false },
    checking: { dot: 'bg-muted', label: 'Vérification…', ping: false },
  }
  const s = map[state]
  return (
    <span className="hidden items-center gap-2 rounded-full border border-line bg-surface/70 px-3 py-1.5 text-xs text-muted sm:inline-flex" role="status">
      <span className="relative flex h-2.5 w-2.5">
        {s.ping && <span className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-60 ${s.dot}`} />}
        <span className={`relative inline-flex h-2.5 w-2.5 rounded-full ${s.dot}`} />
      </span>
      {s.label}
    </span>
  )
}

export default function AppShell() {
  const { user, logout } = useAuth()
  const location = useLocation()
  const outlet = useOutlet()
  const health = useHealth()
  const { dark, toggle } = useTheme()
  const [menuOpen, setMenuOpen] = useState(false)

  const items = NAV.filter((n) => !n.only || n.only === user?.role)

  return (
    <ChatProvider>
      <div className="flex h-screen overflow-hidden">
        <aside className="hidden w-64 shrink-0 flex-col border-r border-line bg-surface/60 p-4 backdrop-blur md:flex">
          <Brand />
          <div className="mt-8 flex-1"><SidebarNav items={items} variant="desktop" /></div>
          <div className="rounded-xl border border-line bg-bg/50 p-3 text-xs text-muted">
            Les réponses sont limitées aux documents autorisés pour votre profil.
          </div>
        </aside>

        <AnimatePresence>
          {menuOpen && (
            <motion.div className="fixed inset-0 z-40 md:hidden" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
              <button type="button" aria-label="Fermer le menu" className="absolute inset-0 bg-black/50" onClick={() => setMenuOpen(false)} />
              <motion.aside className="absolute left-0 top-0 flex h-full w-72 flex-col border-r border-line bg-surface p-4" initial={{ x: -288 }} animate={{ x: 0 }} exit={{ x: -288 }} transition={{ type: 'spring', stiffness: 360, damping: 36 }}>
                <div className="flex items-center justify-between">
                  <Brand />
                  <button type="button" aria-label="Fermer" onClick={() => setMenuOpen(false)} className="rounded-lg p-2 text-muted hover:bg-line/60"><Icon name="x" /></button>
                </div>
                <div className="mt-8"><SidebarNav items={items} variant="mobile" onNavigate={() => setMenuOpen(false)} /></div>
              </motion.aside>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex h-16 shrink-0 items-center justify-between gap-3 border-b border-line bg-surface/60 px-4 backdrop-blur sm:px-6">
            <div className="flex items-center gap-3">
              <button type="button" aria-label="Ouvrir le menu" onClick={() => setMenuOpen(true)} className="rounded-lg p-2 text-muted hover:bg-line/60 md:hidden"><Icon name="menu" /></button>
              <h1 className="text-lg font-semibold tracking-tight">{TITLES[location.pathname] ?? 'Morocco Enterprise Intelligence'}</h1>
            </div>

            <div className="flex items-center gap-2 sm:gap-3">
              <HealthPill state={health} />
              <button type="button" onClick={toggle} aria-label={dark ? 'Passer au thème clair' : 'Passer au thème sombre'} className="rounded-xl border border-line bg-surface/70 p-2.5 text-muted transition hover:text-ink">
                <Icon name={dark ? 'sun' : 'moon'} size={17} />
              </button>
              <div className="hidden items-center gap-2 rounded-xl border border-line bg-surface/70 py-1.5 pl-3 pr-2 sm:flex">
                <div className="text-right leading-tight">
                  <div className="text-sm font-medium" data-testid="user-name">{user?.display_name}</div>
                  <div className="text-xs text-muted">{user?.tenant_id}</div>
                </div>
                <Badge tone="ok">{roleLabel(user?.role)}</Badge>
              </div>
              <button type="button" onClick={logout} aria-label="Se déconnecter" className="rounded-xl border border-line bg-surface/70 p-2.5 text-muted transition hover:text-danger">
                <Icon name="logout" size={17} />
              </button>
            </div>
          </header>

          <main className="min-h-0 flex-1">
            <motion.div key={location.pathname} className="h-full" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}>
              {outlet}
            </motion.div>
          </main>
        </div>
      </div>
    </ChatProvider>
  )
}
