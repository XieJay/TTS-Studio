import { create } from 'zustand'

type Mode = 'light' | 'dark' | 'system'
const KEY = 'tts-theme'

function systemDark(): boolean {
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

function apply(mode: Mode): void {
  const dark = mode === 'dark' || (mode === 'system' && systemDark())
  document.documentElement.classList.toggle('dark', dark)
}

function initial(): Mode {
  const m = localStorage.getItem(KEY)
  return m === 'dark' || m === 'system' ? m : 'light'
}

interface ThemeState {
  mode: Mode
  setMode: (m: Mode) => void
}

export const useTheme = create<ThemeState>((set) => ({
  mode: initial(),
  setMode: (mode) => {
    localStorage.setItem(KEY, mode)
    apply(mode)
    set({ mode })
  },
}))

apply(initial())
