import { Monitor, Moon, Sun } from 'lucide-react'
import { useTheme } from '../stores/theme'

export default function ThemeToggle() {
  const mode = useTheme((s) => s.mode)
  const setMode = useTheme((s) => s.setMode)
  const next = mode === 'light' ? 'dark' : mode === 'dark' ? 'system' : 'light'
  const Icon = mode === 'light' ? Sun : mode === 'dark' ? Moon : Monitor
  const label = mode === 'light' ? '浅色' : mode === 'dark' ? '深色' : '跟随系统'
  return (
    <button
      title={`主题：${label}（点击切换到${next === 'light' ? '浅色' : next === 'dark' ? '深色' : '跟随系统'}）`}
      onClick={() => setMode(next)}
      className="rounded-lg border border-border p-2 text-muted transition hover:bg-surface-2 hover:text-text"
    >
      <Icon size={16} />
    </button>
  )
}
