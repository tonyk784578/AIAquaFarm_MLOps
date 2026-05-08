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

function severityClass(s: AlertSeverity) {
  if (s === 'critical') return 'bg-red-500/10 border-red-500/30 text-red-400'
  if (s === 'warning') return 'bg-yellow-500/10 border-yellow-500/30 text-yellow-400'
  return 'bg-slate-700/50 border-slate-600 text-slate-400'
}

function badgeClass(s: AlertSeverity) {
  if (s === 'critical') return 'bg-red-500/20 text-red-400'
  if (s === 'warning') return 'bg-yellow-500/20 text-yellow-400'
  return 'bg-slate-600 text-slate-400'
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
    queryFn: () =>
      listAlerts({ tank_id: tank === 'all' ? undefined : tank, active_only: activeOnly, limit: 100 }),
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

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <AlertTriangle className="w-5 h-5 text-red-400" />
          <h1 className="text-lg font-semibold text-slate-100">알림</h1>
          {critCount > 0 && (
            <span className="text-xs bg-red-500/20 text-red-400 px-2 py-0.5 rounded-full">
              위험 {critCount}
            </span>
          )}
          {warnCount > 0 && (
            <span className="text-xs bg-yellow-500/20 text-yellow-400 px-2 py-0.5 rounded-full">
              경고 {warnCount}
            </span>
          )}
        </div>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 transition-colors"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isFetching ? 'animate-spin' : ''}`} />
          새로고침
        </button>
      </div>

      {/* Filter bar */}
      <div className="bg-slate-800 rounded-xl border border-slate-700 p-4">
        <div className="flex flex-wrap gap-4 items-center">
          <div className="flex items-center gap-1.5 text-xs text-slate-400">
            <Filter className="w-3.5 h-3.5" />
            필터
          </div>

          {/* Active toggle */}
          <div className="flex gap-1">
            {[true, false].map((v) => (
              <button
                key={String(v)}
                onClick={() => setActiveOnly(v)}
                className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
                  activeOnly === v ? 'bg-sky-500/20 text-sky-400' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {v ? '미해결' : '전체'}
              </button>
            ))}
          </div>

          <div className="w-px h-4 bg-slate-700" />

          {/* Severity */}
          <div className="flex gap-1">
            {SEVERITY_OPTIONS.map((s) => (
              <button
                key={s}
                onClick={() => setSeverity(s)}
                className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-colors ${
                  severity === s ? 'bg-sky-500/20 text-sky-400' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {s === 'all' ? '모든 심각도' : SEVERITY_LABELS[s]}
              </button>
            ))}
          </div>

          <div className="w-px h-4 bg-slate-700" />

          {/* Category */}
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value as AlertCategory | 'all')}
            className="bg-slate-700 border border-slate-600 text-slate-300 text-xs rounded-lg px-2.5 py-1 outline-none focus:ring-1 focus:ring-sky-500"
          >
            {CATEGORY_OPTIONS.map((c) => (
              <option key={c} value={c}>
                {c === 'all' ? '모든 카테고리' : CATEGORY_LABELS[c]}
              </option>
            ))}
          </select>

          {/* Tank */}
          <select
            value={tank}
            onChange={(e) => setTank(e.target.value)}
            className="bg-slate-700 border border-slate-600 text-slate-300 text-xs rounded-lg px-2.5 py-1 outline-none focus:ring-1 focus:ring-sky-500"
          >
            {TANK_OPTIONS.map((t) => (
              <option key={t} value={t}>{t === 'all' ? '모든 수조' : t}</option>
            ))}
          </select>

          <span className="ml-auto text-xs text-slate-500">{filtered.length}건</span>
        </div>
      </div>

      {/* Alert list */}
      {filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-48 text-slate-500 bg-slate-800 rounded-xl border border-slate-700">
          <CheckCircle className="w-10 h-10 mb-2 text-emerald-500/40" />
          <p>조건에 맞는 알림 없음</p>
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map((alert) => (
            <div
              key={alert.id}
              className={`rounded-xl border p-4 ${severityClass(alert.severity)}`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${badgeClass(alert.severity)}`}>
                      {SEVERITY_LABELS[alert.severity]}
                    </span>
                    <span className="text-xs px-2 py-0.5 rounded-full bg-slate-700 text-slate-300">
                      {CATEGORY_LABELS[alert.category] ?? alert.category}
                    </span>
                    <span className="text-xs text-slate-500">{alert.tank_id}</span>
                    <span className="text-xs text-slate-600 ml-auto">
                      {formatRelative(alert.created_at)}
                    </span>
                  </div>
                  <p className="font-medium text-slate-100 text-sm">{alert.title}</p>
                  <p className="text-xs text-slate-400 mt-0.5">{alert.message}</p>
                  {alert.metric_name && (
                    <p className="text-xs text-slate-500 mt-1">
                      {alert.metric_name}: {alert.metric_value}
                      {alert.threshold_value && ` (임계값: ${alert.threshold_value})`}
                    </p>
                  )}
                </div>

                {alert.is_active && (
                  <button
                    onClick={() => resolveMut.mutate(alert.id)}
                    disabled={resolveMut.isPending}
                    className="shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-300 hover:text-slate-100 text-xs transition-colors disabled:opacity-50"
                  >
                    <CheckCircle className="w-3.5 h-3.5" />
                    해결
                  </button>
                )}
                {!alert.is_active && alert.resolved_at && (
                  <span className="shrink-0 text-xs text-emerald-400 flex items-center gap-1">
                    <CheckCircle className="w-3.5 h-3.5" />
                    해결됨
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
