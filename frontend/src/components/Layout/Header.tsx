import { Activity, Bell, Wifi } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { listAlerts } from '@/services/api'

export default function Header() {
  const { data: alerts = [] } = useQuery({
    queryKey: ['alerts-header'],
    queryFn: () => listAlerts({ active_only: true, limit: 100 }),
    refetchInterval: 15_000,
  })

  const critCount = alerts.filter((a) => a.severity === 'critical').length
  const totalActive = alerts.length

  return (
    <header className="h-14 bg-slate-800 border-b border-slate-700 flex items-center justify-between px-6 shrink-0">
      <div className="flex items-center gap-2">
        <Activity className="w-5 h-5 text-sky-400" />
        <span className="text-sm font-medium text-slate-300">AIAquafarm</span>
        <span className="text-slate-600">|</span>
        <span className="text-xs text-slate-400">스마트 RAS 양식장 AI 플랫폼</span>
      </div>

      <div className="flex items-center gap-4">
        {/* Real-time connection indicator */}
        <div className="flex items-center gap-1.5">
          <Wifi className="w-3.5 h-3.5 text-emerald-400" />
          <span className="text-xs text-slate-400">실시간</span>
        </div>

        {/* Notification bell */}
        <Link
          to="/alerts"
          className="relative flex items-center text-slate-400 hover:text-slate-200 transition-colors"
          title={`활성 알림 ${totalActive}건`}
        >
          <Bell className={`w-5 h-5 ${critCount > 0 ? 'text-red-400 animate-pulse' : ''}`} />
          {totalActive > 0 && (
            <span
              className={`absolute -top-1.5 -right-1.5 min-w-[1.1rem] h-[1.1rem] flex items-center justify-center rounded-full text-[10px] font-bold text-white leading-none px-0.5 ${
                critCount > 0 ? 'bg-red-500' : 'bg-amber-500'
              }`}
            >
              {totalActive > 99 ? '99+' : totalActive}
            </span>
          )}
        </Link>
      </div>
    </header>
  )
}
