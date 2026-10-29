import { useCallback, useState } from 'react'

export function useTheme() {
  const [dark, setDark] = useState<boolean>(() => document.documentElement.classList.contains('dark'))

  const toggle = useCallback(() => {
    const next = !document.documentElement.classList.contains('dark')
    document.documentElement.classList.toggle('dark', next)
    try {
      localStorage.setItem('mei.theme', next ? 'dark' : 'light')
    } catch {
      /* stockage indisponible */
    }
    setDark(next)
  }, [])

  return { dark, toggle }
}
