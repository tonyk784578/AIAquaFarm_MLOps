import { Activity, AlertTriangle, BarChart3, Droplets, Fish, Gauge, LogOut, Settings, Sliders } from 'lucide-react'
import { NavLink } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'

const navItems = [
  { to: '/dashboard',     icon: Gauge,         label: '대시보드' },
  { to: '/water-quality', icon: Droplets,      label: '수질 모니터링' },
  { to: '/control',       icon: Sliders,       label: '제어 패널' },
  { to: '/growth',        icon: Fish,          label: '성장 관리' },
  { to: '/feeding',       icon: BarChart3,     label: '먹이 관리' },
  { to: '/alerts',        icon: AlertTriangle, label: '알림' },
  { to: '/mlops',         icon: Activity,      label: 'MLOps' },
  { to: '/settings',      icon: Settings,      label: '설정' },
]

export default function Sidebar() {
  const { user, logout } = useAuth()

  return (
    <aside
      className="w-56 flex flex-col shrink-0"
      style={{
        backgroundColor: 'var(--bg-surface)',
        borderRight: '1px solid var(--bg-border)',
        boxShadow: 'var(--shadow-sidebar)',
      }}
    >
      {/* Logo */}
      <div
        className="h-14 flex items-center px-5 shrink-0"
        style={{ borderBottom: '1px solid var(--bg-border)' }}
      >
        <span
          className="font-extrabold text-lg tracking-tight"
          style={{
            background: 'linear-gradient(135deg, var(--teal-500), var(--blue-500))',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            backgroundClip: 'text',
          }}
        >
          AI
        </span>
        <span
          className="font-extrabold text-lg tracking-tight"
          style={{ color: 'var(--text-primary)' }}
        >
          Aquafarm
        </span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-3 px-2 space-y-0.5 overflow-y-auto">
        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
          >
            <Icon size={15} className="shrink-0" />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* User + logout */}
      <div className="p-3 shrink-0" style={{ borderTop: '1px solid var(--bg-border)' }}>
        {user && (
          <div className="px-3 py-2 mb-1 rounded-xl" style={{ backgroundColor: 'var(--bg-elevated)' }}>
            <p className="text-xs font-semibold truncate" style={{ color: 'var(--text-primary)' }}>
              {user.username}
            </p>
            {user.is_superuser ? (
              <p className="text-xs mt-0.5" style={{ color: 'var(--warn)' }}>관리자</p>
            ) : (
              <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>운영자</p>
            )}
          </div>
        )}
        <button
          onClick={logout}
          className="nav-item w-full mt-0.5"
          style={{ color: 'var(--text-muted)' }}
          onMouseEnter={(e) => {
            e.currentTarget.style.color = 'var(--danger)'
            e.currentTarget.style.backgroundColor = 'rgba(220,38,38,0.07)'
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.color = 'var(--text-muted)'
            e.currentTarget.style.backgroundColor = ''
          }}
        >
          <LogOut size={14} className="shrink-0" />
          로그아웃
        </button>
      </div>
    </aside>
  )
}
