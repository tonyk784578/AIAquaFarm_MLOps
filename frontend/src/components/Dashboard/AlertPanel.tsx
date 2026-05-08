import { useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle } from 'lucide-react'
import { resolveAlert } from '@/services/api'
import type { Alert } from '@/types'

interface Props {
  alerts: Alert[]
}

const CATEGORY_LABELS: Record<string, string> = {
  water_quality: '수질',
  fish_growth: '성장',
  feeding: '급이',
  equipment: '장비',
  system: '시스템',
}

export default function AlertPanel({ alerts }: Props) {
  const qc = useQueryClient()

  const resolveMut = useMutation({
    mutationFn: (id: number) => resolveAlert(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['dashboard-summary'] })
      qc.invalidateQueries({ queryKey: ['alerts'] })
      qc.invalidateQueries({ queryKey: ['alerts-header'] })
    },
  })

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-red-400" />
          <h2 className="font-medium text-slate-200">알림</h2>
        </div>
        {alerts.length > 0 && (
          <span className="text-xs bg-red-500/20 text-red-400 px-2 py-0.5 rounded-full">
            {alerts.length}
          </span>
        )}
      </div>

      {alerts.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-32 text-slate-500">
          <CheckCircle className="w-8 h-8 mb-1 text-emerald-500/40" />
          <span className="text-sm">활성 알림 없음</span>
        </div>
      ) : (
        <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
          {alerts.map((alert) => (
            <div
              key={alert.id}
              className={`p-3 rounded-lg border text-sm ${
                alert.severity === 'critical'
                  ? 'bg-red-500/10 border-red-500/30'
                  : alert.severity === 'warning'
                  ? 'bg-yellow-500/10 border-yellow-500/30'
                  : 'bg-slate-700/50 border-slate-600'
              }`}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 mb-0.5">
                    <span
                      className={`text-xs px-1.5 py-0.5 rounded font-medium ${
                        alert.severity === 'critical'
                          ? 'bg-red-500/20 text-red-400'
                          : alert.severity === 'warning'
                          ? 'bg-yellow-500/20 text-yellow-400'
                          : 'bg-slate-600 text-slate-400'
                      }`}
                    >
                      {CATEGORY_LABELS[alert.category] ?? alert.category}
                    </span>
                    <span className="text-xs text-slate-500">{alert.tank_id}</span>
                  </div>
                  <p className="font-medium text-slate-200 truncate">{alert.title}</p>
                  <p className="text-xs text-slate-400 mt-0.5 line-clamp-2">{alert.message}</p>
                </div>
                <button
                  onClick={() => resolveMut.mutate(alert.id)}
                  disabled={resolveMut.isPending}
                  title="해결"
                  className="shrink-0 p-1 rounded-lg text-slate-500 hover:text-emerald-400 hover:bg-emerald-400/10 transition-colors disabled:opacity-40"
                >
                  <CheckCircle className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
