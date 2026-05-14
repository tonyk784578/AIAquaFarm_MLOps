import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle, Filter, RefreshCw } from 'lucide-react'
import { listAlerts, resolveAlert } from '@/services/api'
import type { Alert, AlertCategory, AlertSeverity } from '@/types'

const SEVERITY_OPTIONS: Array<AlertSeverity | 'all'> = ['all', 'critical', 'warning', 'info']
const CATEGORY_OPTIONS: Array<AlertCategory | 'all'> = [
  'all', 'water_quality', 'fish_growth', 'feeding', 'equipment', 'system',
]
const TANK_OPTIONS = ['all', 'TANK-01', 'TANK-02', 'TANK-03']

const SEVERITY_LABELS: Record<string, string> = {
  critical: '위험', warning: '경고', info: '정보',
}
const CATEGORY_LABELS: Record<string, string> = {
  water_quality: '수질', fish_growth: '성장', feeding: '급이', equipment: '장비', system: '시스템',
}

function severityColor(s: AlertSeverity) {
  if (s === 'critical') return 'var(--danger)'
  if (s === 'warning')  return 'var(--warn)'
  return 'var(--info)'
}

function severityBg(s: AlertSeverity) {
  if (s === 'critical') return 'rgba(220,38,38,0.07)'
  if (s === 'warning')  return 'rgba(217,119,6,0.07)'
  return 'rgba(37,99,235,0.07)'
}

function formatRelative(iso: string) {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000
  if (diff < 60) return `${Math.round(diff)}초 전`
  if (diff < 3600) return `${Math.round(diff / 60)}분 전`
  if (diff < 86400) return `${Math.round(diff / 3600)}시간 전`
  return `${Math.round(diff / 86400)}일 전`
}

export default function AlertsPage() {
  const [activeOnly, setActiveOnly] = useState(true)
  const [severity, setSeverity] = useState<AlertSeverity | 'all'>('all')
  const [category, setCategory] = useState<AlertCategory | 'all'>('all')
  const [tank, setTank] = useState<string>('all')
  const qc = useQueryClient()

  const { data: alerts = [], isFetching, refetch } = useQuery<Alert[]>({
    queryKey: ['alerts', activeOnly, tank],
    queryFn: () => listAlerts({ tank_id: tank === 'all' ? undefined : tank, active_only: activeOnly, limit: 100 }),
    refetchInterval: 15_000,
  })

  const resolveMut = useMutation({
    mutationFn: (id: number) => resolveAlert(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts'] }),
  })

  const filtered = alerts.filter((a) => {
    if (severity !== 'all' && a.severity !== severity) return false
    if (category !== 'all' && a.category !== category) return false
    return true
  })

  const critCount = alerts.filter((a) => a.severity === 'critical').length
  const warnCount = alerts.filter((a) => a.severity === 'warning').length

  const filterBtnStyle = (active: boolean) =>
    active
      ? { background: 'linear-gradient(135deg, var(--teal-500), var(--blue-500))', color: '#fff', borderRadius: 8, padding: '4px 12px', fontSize: 12, fontWeight: 600, border: 'none', cursor: 'pointer' }
      : { backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--bg-border)', color: 'var(--text-secondary)', borderRadius: 8, padding: '4px 12px', fontSize: 12, fontWeight: 500, cursor: 'pointer' }

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="page-title flex items-center gap-2">
            <AlertTriangle size={18} style={{ color: 'var(--danger)' }} />
            알림
          </h1>
          {critCount > 0 && <span className="badge-danger">위험 {critCount}</span>}
          {warnCount > 0 && <span className="badge-warn">경고 {warnCount}</span>}
        </div>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="flex items-center gap-1.5 text-xs transition-colors"
          style={{ color: 'var(--text-secondary)' }}
        >
          <RefreshCw size={13} className={isFetching ? 'animate-spin' : ''} />
          새로고침
        </button>
      </div>

      {/* Filter bar */}
      <div className="card">
        <div className="flex flex-wrap gap-3 items-center">
          <div className="flex items-center gap-1.5 text-xs" style={{ color: 'var(--text-muted)' }}>
            <Filter size={13} />필터
          </div>

          <div className="flex gap-1.5">
            {[true, false].map((v) => (
              <button key={String(v)} onClick={() => setActiveOnly(v)} style={filterBtnStyle(activeOnly === v)}>
                {v ? '미해결' : '전체'}
              </button>
            ))}
          </div>

          <div className="w-px h-4" style={{ backgroundColor: 'var(--bg-border)' }} />

          <div className="flex gap-1.5 flex-wrap">
            {SEVERITY_OPTIONS.map((s) => (
              <button key={s} onClick={() => setSeverity(s)} style={filterBtnStyle(severity === s)}>
                {s === 'all' ? '모든 심각도' : SEVERITY_LABELS[s]}
              </button>
            ))}
          </div>

          <div className="w-px h-4" style={{ backgroundColor: 'var(--bg-border)' }} />

          <select
            value={category}
            onChange={(e) => setCategory(e.target.value as AlertCategory | 'all')}
            className="input-base"
            style={{ width: 'auto', padding: '4px 10px' }}
          >
            {CATEGORY_OPTIONS.map((c) => (
              <option key={c} value={c}>{c === 'all' ? '모든 카테고리' : CATEGORY_LABELS[c]}</option>
            ))}
          </select>

          <select
            value={tank}
            onChange={(e) => setTank(e.target.value)}
            className="input-base"
            style={{ width: 'auto', padding: '4px 10px' }}
          >
            {TANK_OPTIONS.map((t) => (
              <option key={t} value={t}>{t === 'all' ? '모든 수조' : t}</option>
            ))}
          </select>

          <span className="ml-auto text-xs" style={{ color: 'var(--text-muted)' }}>{filtered.length}건</span>
        </div>
      </div>

      {/* Alert list */}
      {filtered.length === 0 ? (
        <div
          className="flex flex-col items-center justify-center h-48 rounded-2xl"
          style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--bg-border)' }}
        >
          <CheckCircle size={40} className="mb-2" style={{ color: 'var(--ok)', opacity: 0.4 }} />
          <p className="text-sm" style={{ color: 'var(--text-muted)' }}>조건에 맞는 알림 없음</p>
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map((alert) => (
            <div
              key={alert.id}
              className="rounded-2xl p-4"
              style={{
                backgroundColor: severityBg(alert.severity),
                border: `1px solid ${severityColor(alert.severity)}40`,
              }}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <span
                      className="text-xs px-2 py-0.5 rounded-lg font-semibold"
                      style={{ color: severityColor(alert.severity), backgroundColor: `${severityColor(alert.severity)}18` }}
                    >
                      {SEVERITY_LABELS[alert.severity]}
                    </span>
                    <span
                      className="text-xs px-2 py-0.5 rounded-lg font-medium"
                      style={{ backgroundColor: 'var(--bg-elevated)', color: 'var(--text-secondary)' }}
                    >
                      {CATEGORY_LABELS[alert.category] ?? alert.category}
                    </span>
                    <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{alert.tank_id}</span>
                    <span className="text-xs ml-auto" style={{ color: 'var(--text-muted)' }}>
                      {formatRelative(alert.created_at)}
                    </span>
                  </div>
                  <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{alert.title}</p>
                  <p className="text-xs mt-0.5" style={{ color: 'var(--text-secondary)' }}>{alert.message}</p>
                  {alert.metric_name && (
                    <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
                      {alert.metric_name}: {alert.metric_value}
                      {alert.threshold_value && ` (임계값: ${alert.threshold_value})`}
                    </p>
                  )}
                </div>

                {alert.is_active && (
                  <button
                    onClick={() => resolveMut.mutate(alert.id)}
                    disabled={resolveMut.isPending}
                    className="shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors disabled:opacity-50"
                    style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--bg-border)', color: 'var(--text-secondary)' }}
                  >
                    <CheckCircle size={13} />해결
                  </button>
                )}
                {!alert.is_active && alert.resolved_at && (
                  <span className="shrink-0 text-xs flex items-center gap-1" style={{ color: 'var(--ok)' }}>
                    <CheckCircle size={13} />해결됨
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
