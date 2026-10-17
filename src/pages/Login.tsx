import { useState, type FormEvent } from 'react'
import { Navigate } from 'react-router-dom'
import { motion, useAnimationControls } from 'framer-motion'
import { useAuth } from '../context/AuthContext'
import { useHealth } from '../hooks/useHealth'
import { ApiError, apiBase } from '../lib/api'
import { Icon, LogoMark, type IconName } from '../components/ui/Icons'

const FEATURES: { icon: IconName; title: string; text: string }[] = [
  { icon: 'lock', title: 'Accès par rôle', text: 'Chaque profil ne voit que les documents qu\'il est autorisé à consulter.' },
  { icon: 'database', title: 'Réponses sourcées', text: 'Chaque réponse cite le document et la page dont elle provient.' },
  { icon: 'activity', title: 'Traçabilité complète', text: 'Chaque requête est journalisée dans un registre d\'audit.' },
]

export default function Login() {
  const { status, login } = useAuth()
  const health = useHealth()
  const shake = useAnimationControls()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (status === 'authenticated') return <Navigate to="/assistant" replace />

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      await login(username.trim(), password)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Erreur inattendue.')
      void shake.start({ x: [0, -10, 10, -6, 6, 0], transition: { duration: 0.4 } })
    } finally {
      setBusy(false)
    }
  }

  const pill =
    health === 'online' ? { dot: 'bg-ok', text: 'API connectée' }
    : health === 'degraded' ? { dot: 'bg-warn', text: 'API connectée · index non chargé' }
    : health === 'offline' ? { dot: 'bg-danger', text: `API injoignable (${apiBase})` }
    : { dot: 'bg-muted', text: 'Vérification de l\'API…' }

  return (
    <div className="relative min-h-screen overflow-hidden">
      <div className="pointer-events-none absolute inset-0" aria-hidden="true">
        <div className="grid-bg absolute inset-0" />
        <div className="absolute -left-24 -top-24 h-96 w-96 animate-blob rounded-full bg-brand/25 blur-3xl" />
        <div className="absolute -bottom-32 right-0 h-[28rem] w-[28rem] animate-blob rounded-full bg-gold/20 blur-3xl" style={{ animationDelay: '-6s' }} />
        <div className="absolute left-1/3 top-1/2 h-72 w-72 animate-blob rounded-full bg-plum/15 blur-3xl" style={{ animationDelay: '-12s' }} />
      </div>

      <div className="relative mx-auto grid min-h-screen max-w-6xl items-center gap-12 px-6 py-10 lg:grid-cols-2">
        <motion.div className="hidden lg:block" initial={{ opacity: 0, x: -24 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.6 }}>
          <div className="flex items-center gap-3">
            <LogoMark size={44} />
            <div>
              <div className="text-lg font-semibold leading-tight">Fluxa</div>
              <div className="text-lg font-semibold leading-tight text-brand">Intelligence</div>
            </div>
          </div>
          <h1 className="mt-10 text-4xl font-semibold leading-tight tracking-tight">
            Interrogez les documents de votre entreprise, <span className="text-brand">en toute confiance.</span>
          </h1>
          <ul className="mt-10 space-y-5">
            {FEATURES.map((f, i) => (
              <motion.li key={f.title} className="flex gap-4" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 + i * 0.12, duration: 0.45 }}>
                <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-brand/10 text-brand ring-1 ring-brand/20">
                  <Icon name={f.icon} size={20} />
                </span>
                <div>
                  <div className="font-medium">{f.title}</div>
                  <div className="text-sm text-muted">{f.text}</div>
                </div>
              </motion.li>
            ))}
          </ul>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 24, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ duration: 0.5 }}>
          <motion.div animate={shake} className="card mx-auto w-full max-w-md p-8">
            <div className="mb-6 flex items-center gap-3 lg:hidden">
              <LogoMark size={36} />
              <span className="font-semibold">Fluxa</span>
            </div>
            <h2 className="text-2xl font-semibold tracking-tight">Connexion</h2>
            <p className="mt-1 text-sm text-muted">Utilisez votre compte professionnel.</p>

            <form onSubmit={submit} className="mt-6 space-y-4" noValidate>
              <div>
                <label htmlFor="username" className="mb-1.5 block text-sm font-medium">Identifiant</label>
                <input id="username" className="field" autoComplete="username" autoFocus value={username} onChange={(e) => setUsername(e.target.value)} />
              </div>
              <div>
                <label htmlFor="password" className="mb-1.5 block text-sm font-medium">Mot de passe</label>
                <input id="password" type="password" className="field" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
              </div>

              {error && (
                <motion.p role="alert" className="rounded-xl border border-danger/30 bg-danger/5 px-3 py-2 text-sm text-danger" initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }}>
                  {error}
                </motion.p>
              )}

              <button type="submit" className="btn-primary w-full" disabled={busy || !username.trim() || !password}>
                {busy ? (
                  <>
                    <motion.span className="h-4 w-4 rounded-full border-2 border-current border-t-transparent" animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 0.8, ease: 'linear' }} />
                    Connexion…
                  </>
                ) : 'Se connecter'}
              </button>
            </form>

            <div className="mt-6 flex items-center justify-center gap-2 text-xs text-muted" role="status">
              <span className={`h-2 w-2 rounded-full ${pill.dot}`} />
              {pill.text}
            </div>
          </motion.div>
        </motion.div>
      </div>
    </div>
  )
}
