import type { ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AudioLines, Home, Mic, Settings as SettingsIcon, SlidersHorizontal } from 'lucide-react'
import { NavLink } from 'react-router-dom'
import { apiGet } from '../api/client'
import type { ProviderInfo } from '../api/types'
import ThemeToggle from './ThemeToggle'

const NAV = [
  { to: '/', label: '任务', icon: Home },
  { to: '/playground', label: '试炼场', icon: SlidersHorizontal },
  { to: '/voices', label: '音色库', icon: Mic },
  { to: '/settings', label: '设置', icon: SettingsIcon },
]

export default function Layout({ children }: { children: ReactNode }) {
  const { data: providers } = useQuery({
    queryKey: ['providers'],
    queryFn: () => apiGet<ProviderInfo[]>('/api/providers'),
  })
  const ready = providers?.filter((p) => p.configured).length ?? 0
  return (
    <div className="min-h-screen bg-bg">
      <header className="sticky top-0 z-40 border-b border-border bg-surface/85 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-6 px-4">
          <div className="flex items-center gap-2 font-semibold">
            <AudioLines size={20} className="text-primary" />
            <span>TTS Studio</span>
          </div>
          <nav className="flex gap-1">
            {NAV.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  `flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm transition ${
                    isActive ? 'bg-primary/10 font-medium text-primary' : 'text-muted hover:bg-surface-2 hover:text-text'
                  }`
                }
              >
                <Icon size={15} />
                {label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3">
            <span className="hidden text-xs text-muted sm:inline">可用引擎 {ready}</span>
            <ThemeToggle />
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
    </div>
  )
}
