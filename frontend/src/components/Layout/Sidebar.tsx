// Left navigation sidebar — primary page navigation.
// TODO (Phase 2): Add active state highlight based on current route.
// TODO (Phase 3): Add Settings and User Management links.

import { AlertTriangle, BarChart3, Fish, Gauge, Settings, Sliders } from 'lucide-react'
import { NavLink } from 'react-router-dom'

const navItems = [
  { to: '/dashboard', icon: Gauge, label: '대시보드' },
  { to: '/control', icon: Sliders, label: '제어 패널' },
  { to: '/growth', icon: Fish, label: '성장 관리' },
  { to: '/feeding', icon: BarChart3, label: '먹이 관리' },
  { to: '/alerts', icon: AlertTriangle, label: '알림' },
  { to: '/settings', icon: Settings, label: '설정' },
]

export default function Sidebar() {
  return (
    <aside className="w-56 bg-slate-800 border-r border-slate-700 flex flex-col shrink-0">
      {/* Logo */}
      <div className="h-14 flex items-center px-4 border-b border-slate-700">
        <span className="text-sky-400 font-bold text-lg tracking-tight">AI</span>
        <span className="text-slate-100 font-bold text-lg tracking-tight">Aquafarm</span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-4 px-2 space-y-1">
        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                isActive
                  ? 'bg-sky-500/20 text-sky-400 font-medium'
                  : 'text-slate-400 hover:bg-slate-700 hover:text-slate-200'
              }`
            }
          >
            <Icon className="w-4 h-4 shrink-0" />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Version */}
      <div className="p-4 border-t border-slate-700">
        <p className="text-xs text-slate-600">v0.1.0 — Phase 1</p>
      </div>
    </aside>
  )
}
