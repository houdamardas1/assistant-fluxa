import type { ReactNode } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { MotionConfig, motion } from 'framer-motion'
import { AuthProvider, useAuth } from './context/AuthContext'
import type { Role } from './lib/types'
import { LogoMark } from './components/ui/Icons'
import AppShell from './pages/AppShell'
import Audit from './pages/Audit'
import Chat from './pages/Chat'
import Dashboard from './pages/Dashboard'
import Documents from './pages/Documents'
import Login from './pages/Login'

function Splash() {
  return (
    <div className="grid h-screen place-items-center" role="status" aria-label="Chargement">
      <motion.div animate={{ scale: [1, 1.12, 1], opacity: [0.7, 1, 0.7] }} transition={{ duration: 1.4, repeat: Infinity }}>
        <LogoMark size={56} />
      </motion.div>
    </div>
  )
}

function RequireAuth({ children }: { children: ReactNode }) {
  const { status } = useAuth()
  const location = useLocation()
  if (status === 'loading') return <Splash />
  if (status === 'anonymous') return <Navigate to="/login" replace state={{ from: location.pathname }} />
  return <>{children}</>
}

function RequireRole({ role, children }: { role: Role; children: ReactNode }) {
  const { user } = useAuth()
  if (user?.role !== role) return <Navigate to="/assistant" replace />
  return <>{children}</>
}

export default function App() {
  return (
    // "user" : respecte la preference systeme "reduire les animations".
    <MotionConfig reducedMotion="user">
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route element={<RequireAuth><AppShell /></RequireAuth>}>
            <Route path="/assistant" element={<Chat />} />
            <Route path="/tableau-de-bord" element={<Dashboard />} />
            <Route path="/documents" element={<Documents />} />
            <Route path="/audit" element={<RequireRole role="direction"><Audit /></RequireRole>} />
          </Route>
          <Route path="*" element={<Navigate to="/assistant" replace />} />
        </Routes>
      </AuthProvider>
    </MotionConfig>
  )
}
