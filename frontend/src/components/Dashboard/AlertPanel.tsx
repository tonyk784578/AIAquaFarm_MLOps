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

function severityColor(s: Alert['severity']): string {
  if (s === 'critical') return 'var(--danger)'
  if (s === 'warning')  return 'var(--warn)'
  return 'var(--info)'
}

function severityBg(s: Alert['severity']): string {
  if (s === 'critical') return 'rgba(220,38,38,0.07)'
  if (s === 'warning')  return 'rgba(217,119,6,0.07)'
  return 'rgba(37,99,235,0.07)'
}

function severityBorder(s: Alert['severity']): string {
  if (s === 'critical') return 'rgba(220,38,38,0.25)'
  if (s === 'warning')  return 'rgba(217,119,6,0.25)'
  return 'rgba(37,99,235,0.25)'
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
          <AlertTriangle size={15} style={{ color: 'var(--danger)' }} />
          <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>알림</h2>
        </div>
        {alerts.length > 0 && (
          <span className="badge-danger">{alerts.length}</span>
        )}
      </div>

      {alerts.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-32">
          <CheckCircle size={32} className="mb-2" style={{ color: 'var(--ok)', opacity: 0.4 }} />
          <span className="text-sm" style={{ color: 'var(--text-muted)' }}>활성 알림 없음</span>
        </div>
      ) : (
        <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
          {alerts.map((alert) => (
            <div
              key={alert.id}
              className="p-3 rounded-xl"
              style={{
                backgroundColor: severityBg(alert.severity),
                border: `1px solid ${severityBorder(alert.severity)}`,
              }}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 mb-1 flex-wrap">
                    <span
                      className="text-xs px-1.5 py-0.5 rounded-md font-semibold"
                      style={{
                        color: severityColor(alert.severity),
                        backgroundColor: severityBg(alert.severity),
                      }}
                    >
                      {CATEGORY_LABELS[alert.category] ?? alert.category}
                    </span>
                    <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{alert.tank_id}</span>
                  </div>
                  <p className="text-sm font-semibold truncate" style={{ color: 'var(--text-primary)' }}>
                    {alert.title}
                  </p>
                  <p className="text-xs mt-0.5 line-clamp-2" style={{ color: 'var(--text-secondary)' }}>
                    {alert.message}
                  </p>
                </div>
                <button
                  onClick={() => resolveMut.mutate(alert.id)}
                  disabled={resolveMut.isPending}
                  title="해결"
                  className="shrink-0 p-1.5 rounded-lg transition-colors disabled:opacity-40"
                  style={{ color: 'var(--text-muted)' }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.color = 'var(--ok)'
                    e.currentTarget.style.backgroundColor = 'rgba(5,150,105,0.1)'
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.color = 'var(--text-muted)'
                    e.currentTarget.style.backgroundColor = 'transparent'
                  }}
                >
                  <CheckCircle size={14} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
