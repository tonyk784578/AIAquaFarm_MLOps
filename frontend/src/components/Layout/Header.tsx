import { Bell, Moon, Sun, Wifi } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { listAlerts } from '@/services/api'
import { useThemeStore } from '@/stores/themeStore'

export default function Header() {
  const { isDark, toggle } = useThemeStore()

  const { data: alerts = [] } = useQuery({
    queryKey: ['alerts-header'],
    queryFn: () => listAlerts({ active_only: true, limit: 100 }),
    refetchInterval: 15_000,
  })

  const critCount = alerts.filter((a) => a.severity === 'critical').length
  const totalActive = alerts.length

  return (
    <header
      className="h-14 flex items-center justify-between px-6 shrink-0"
      style={{
        backgroundColor: 'var(--bg-surface)',
        borderBottom: '1px solid var(--bg-border)',
        boxShadow: 'var(--shadow-topbar)',
      }}
    >
      {/* Left: breadcrumb / title */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1.5">
          <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
            스마트 RAS 양식장
          </span>
          <span style={{ color: 'var(--bg-border)' }}>·</span>
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
            AI 플랫폼
          </span>
        </div>
      </div>

      {/* Right: status + actions */}
      <div className="flex items-center gap-2">
        {/* Real-time indicator */}
        <div
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg"
          style={{ backgroundColor: 'var(--bg-elevated)' }}
        >
          <Wifi size={12} style={{ color: 'var(--ok)' }} />
          <span className="text-xs font-medium" style={{ color: 'var(--ok)' }}>실시간</span>
        </div>

        {/* Dark mode toggle */}
        <button
          onClick={toggle}
          className="p-2 rounded-lg transition-colors"
          style={{ color: 'var(--text-secondary)', backgroundColor: 'transparent' }}
          title={isDark ? '라이트 모드로 전환' : '다크 모드로 전환'}
          onMouseEnter={(e) => {
            e.currentTarget.style.backgroundColor = 'var(--bg-elevated)'
            e.currentTarget.style.color = 'var(--text-primary)'
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.backgroundColor = 'transparent'
            e.currentTarget.style.color = 'var(--text-secondary)'
          }}
        >
          {isDark ? <Sun size={16} /> : <Moon size={16} />}
        </button>

        {/* Alert bell */}
        <Link
          to="/alerts"
          className="relative p-2 rounded-lg transition-colors"
          style={{ color: 'var(--text-secondary)' }}
          title={`활성 알림 ${totalActive}건`}
          onMouseEnter={(e) => {
            e.currentTarget.style.backgroundColor = 'var(--bg-elevated)'
            e.currentTarget.style.color = 'var(--text-primary)'
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.backgroundColor = 'transparent'
            e.currentTarget.style.color = 'var(--text-secondary)'
          }}
        >
          <Bell
            size={16}
            style={{ color: critCount > 0 ? 'var(--danger)' : undefined }}
            className={critCount > 0 ? 'animate-pulse' : ''}
          />
          {totalActive > 0 && (
            <span
              className="absolute -top-0.5 -right-0.5 min-w-[1rem] h-4 flex items-center justify-center rounded-full text-[10px] font-bold text-white leading-none px-0.5"
              style={{ backgroundColor: critCount > 0 ? 'var(--danger)' : 'var(--warn)' }}
            >
              {totalActive > 99 ? '99+' : totalActive}
            </span>
          )}
        </Link>
      </div>
    </header>
  )
}
