import { createContext, useContext, useEffect, useState, ReactNode } from 'react'

export type ThemeMode = 'Светлая' | 'Тёмная' | 'Система'

type ThemeCtx = {
  mode: ThemeMode
  setMode: (m: ThemeMode) => void
  /** the actually-applied theme: 'light' | 'dark' (resolved from system if mode is 'Система') */
  resolved: 'light' | 'dark'
}

const Ctx = createContext<ThemeCtx | null>(null)

const STORAGE_KEY = 'gt-theme-mode'

function readStored(): ThemeMode {
  if (typeof localStorage === 'undefined') return 'Светлая'
  const v = localStorage.getItem(STORAGE_KEY)
  if (v === 'Светлая' || v === 'Тёмная' || v === 'Система') return v
  return 'Светлая'
}

function systemPrefersDark(): boolean {
  if (typeof window === 'undefined' || !window.matchMedia) return false
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>(() => readStored())
  const [systemDark, setSystemDark] = useState<boolean>(() => systemPrefersDark())

  // Track system preference changes (when mode === 'Система')
  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = (e: MediaQueryListEvent) => setSystemDark(e.matches)
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])

  const resolved: 'light' | 'dark' =
    mode === 'Тёмная' ? 'dark' : mode === 'Светлая' ? 'light' : systemDark ? 'dark' : 'light'

  // Apply data-theme attribute on <html>
  useEffect(() => {
    const html = document.documentElement
    if (resolved === 'dark') html.setAttribute('data-theme', 'dark')
    else html.removeAttribute('data-theme')
  }, [resolved])

  const setMode = (m: ThemeMode) => {
    setModeState(m)
    localStorage.setItem(STORAGE_KEY, m)
  }

  return <Ctx.Provider value={{ mode, setMode, resolved }}>{children}</Ctx.Provider>
}

export function useTheme(): ThemeCtx {
  const v = useContext(Ctx)
  if (!v) throw new Error('useTheme must be used inside <ThemeProvider>')
  return v
}
