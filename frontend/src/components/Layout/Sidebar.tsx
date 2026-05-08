// Left navigation sidebar — primary page navigation.

import { Activity, AlertTriangle, BarChart3, Fish, Gauge, LogOut, Settings, Sliders } from 'lucide-react'
import { NavLink } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'

const navItems = [
  { to: '/dashboard', icon: Gauge, label: '대시보드' },
  { to: '/control', icon: Sliders, label: '제어 패널' },
  { to: '/growth', icon: Fish, label: '성장 관리' },
  { to: '/feeding', icon: BarChart3, label: '먹이 관리' },
  { to: '/alerts', icon: AlertTriangle, label: '알림' },
  { to: '/mlops', icon: Activity, label: 'MLOps' },
  { to: '/settings', icon: Settings, label: '설정' },
]

export default function Sidebar() {
  const { user, logout } = useAuth()

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

      {/* User + logout */}
      <div className="p-3 border-t border-slate-700 space-y-2">
        {user && (
          <div className="px-2 py-1">
            <p className="text-xs text-slate-400 truncate">{user.username}</p>
            {user.is_superuser && (
              <p className="text-xs text-amber-500/70">관리자</p>
            )}
          </div>
        )}
        <button
          onClick={logout}
          className="flex items-center gap-2 w-full px-2 py-1.5 rounded-lg text-xs
                     text-slate-500 hover:text-red-400 hover:bg-red-400/10 transition-colors"
        >
          <LogOut className="w-3.5 h-3.5" />
          로그아웃
        </button>
        <p className="text-xs text-slate-700 px-2">v0.1.0 — Phase 5</p>
      </div>
    </aside>
  )
}
