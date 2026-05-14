import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BarChart2, Play, RefreshCw, Utensils } from 'lucide-react'
import { getFeedingHistory, stopFeeding, triggerFeeding } from '@/services/api'
import type { FeedingRecord } from '@/types'

const TANK_OPTIONS = ['TANK-01', 'TANK-02', 'TANK-03']

const TRIGGER_LABELS: Record<string, string> = {
  ai: 'AI', manual: '수동', schedule: '스케줄',
}

function formatDate(iso: string) {
  const d = new Date(iso)
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`
}

function ActivityBar({ score }: { score: number | null }) {
  const pct = score != null ? Math.round(score * 100) : 0
  const color = pct >= 70 ? 'var(--ok)' : pct >= 40 ? 'var(--warn)' : 'var(--danger)'
  return (
    <div>
      <div className="flex justify-between text-xs mb-1.5">
        <span style={{ color: 'var(--text-secondary)' }}>먹이활성도</span>
        <span className="font-bold" style={{ color }}>{score != null ? `${pct}%` : '—'}</span>
      </div>
      <div className="h-2.5 rounded-full overflow-hidden" style={{ backgroundColor: 'var(--bg-elevated)' }}>
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
    </div>
  )
}

export default function FeedingPage() {
  const [tank, setTank] = useState(TANK_OPTIONS[0])
  const [amount, setAmount] = useState('1.0')
  const qc = useQueryClient()

  const { data: records = [], isFetching, refetch } = useQuery<FeedingRecord[]>({
    queryKey: ['feeding', tank],
    queryFn: () => getFeedingHistory(tank, 30),
    refetchInterval: 20_000,
  })

  const latest = records[0] ?? null

  const triggerMut = useMutation({
    mutationFn: () => triggerFeeding(tank, parseFloat(amount) || 1.0),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['feeding', tank] }),
  })
  const stopMut = useMutation({
    mutationFn: () => stopFeeding(tank),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['feeding', tank] }),
  })

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="page-title flex items-center gap-2">
          <Utensils size={18} style={{ color: 'var(--warn)' }} />
          급이 관리
        </h1>
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

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Left column */}
        <div className="space-y-4">
          {/* Tank selector */}
          <div className="card">
            <p className="section-title">수조 선택</p>
            <div className="flex gap-2">
              {TANK_OPTIONS.map((t) => (
                <button
                  key={t}
                  onClick={() => setTank(t)}
                  className="flex-1 py-1.5 rounded-lg text-xs font-semibold transition-all"
                  style={
                    tank === t
                      ? { background: 'linear-gradient(135deg, var(--teal-500), var(--blue-500))', color: '#fff' }
                      : { backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--bg-border)', color: 'var(--text-secondary)' }
                  }
                >
                  {t}
                </button>
              ))}
            </div>
          </div>

          {/* Status */}
          <div className="card space-y-4">
            <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>현재 상태</h2>
            <ActivityBar score={latest?.activity_score ?? null} />
            <div className="grid grid-cols-2 gap-3">
              {[
                { label: '최근 급이량',  value: latest?.actual_amount_kg?.toFixed(2),      unit: 'kg', color: 'var(--text-primary)' },
                { label: 'AI 권장량',   value: latest?.recommended_amount_kg?.toFixed(2),  unit: 'kg', color: 'var(--warn)'         },
                { label: '사료 낭비',   value: latest?.feed_waste_estimate_pct?.toFixed(1), unit: '%',  color: 'var(--text-primary)' },
                { label: '트리거',      value: latest?.trigger_source ? TRIGGER_LABELS[latest.trigger_source] : null, unit: '', color: 'var(--text-primary)' },
              ].map(({ label, value, unit, color }) => (
                <div key={label}>
                  <p className="text-xs mb-0.5" style={{ color: 'var(--text-muted)' }}>{label}</p>
                  <p className="text-lg font-bold" style={{ color }}>
                    {value ?? '—'}
                    {value && unit && <span className="text-xs font-normal ml-0.5" style={{ color: 'var(--text-muted)' }}>{unit}</span>}
                  </p>
                </div>
              ))}
            </div>
          </div>

          {/* Manual trigger */}
          <div className="card space-y-3">
            <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>수동 급이</h2>
            <div>
              <label className="text-xs" style={{ color: 'var(--text-secondary)' }}>급이량 (kg)</label>
              <input
                type="number" min="0.1" max="10" step="0.1"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                className="input-base mt-1"
              />
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => triggerMut.mutate()}
                disabled={triggerMut.isPending}
                className="btn-primary flex-1 flex items-center justify-center gap-1.5"
              >
                <Play size={13} />
                {triggerMut.isPending ? '급이 중…' : '급이 시작'}
              </button>
              <button
                onClick={() => stopMut.mutate()}
                disabled={stopMut.isPending}
                className="px-3 py-2 rounded-lg text-sm font-semibold transition-colors disabled:opacity-50"
                style={{ backgroundColor: 'rgba(220,38,38,0.1)', color: 'var(--danger)', border: '1px solid rgba(220,38,38,0.2)' }}
              >
                정지
              </button>
            </div>
            {triggerMut.isError && (
              <p className="text-xs" style={{ color: 'var(--danger)' }}>급이 명령 실패</p>
            )}
          </div>
        </div>

        {/* History table */}
        <div
          className="lg:col-span-2 rounded-2xl overflow-hidden"
          style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--bg-border)', boxShadow: 'var(--shadow-sm)' }}
        >
          <div className="px-5 py-3 flex items-center gap-2" style={{ borderBottom: '1px solid var(--bg-border)' }}>
            <BarChart2 size={14} style={{ color: 'var(--warn)' }} />
            <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>급이 이력 (최근 30회)</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr style={{ borderBottom: '1px solid var(--bg-border)' }}>
                  {['시각','급이량(kg)','권장량(kg)','활성도','낭비(%)','트리거','완료'].map((h) => (
                    <th
                      key={h}
                      className={`px-4 py-3 text-xs font-semibold ${h === '시각' ? 'text-left' : 'text-right last:text-center'}`}
                      style={{ color: 'var(--text-muted)' }}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {records.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="text-center py-10 text-sm" style={{ color: 'var(--text-muted)' }}>
                      급이 기록 없음
                    </td>
                  </tr>
                ) : (
                  records.map((r) => (
                    <tr
                      key={r.id}
                      style={{ borderBottom: '1px solid var(--bg-border)' }}
                      onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = 'var(--bg-elevated)' }}
                      onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = '' }}
                    >
                      <td className="px-4 py-3 text-sm" style={{ color: 'var(--text-secondary)' }}>{formatDate(r.started_at)}</td>
                      <td className="px-4 py-3 text-right text-sm" style={{ color: 'var(--text-primary)' }}>{r.actual_amount_kg?.toFixed(2) ?? '—'}</td>
                      <td className="px-4 py-3 text-right text-sm font-medium" style={{ color: 'var(--warn)' }}>{r.recommended_amount_kg?.toFixed(2) ?? '—'}</td>
                      <td className="px-4 py-3 text-right">
                        {r.activity_score != null ? (
                          <span className={r.activity_score >= 0.7 ? 'badge-ok' : r.activity_score >= 0.4 ? 'badge-warn' : 'badge-danger'}>
                            {(r.activity_score * 100).toFixed(0)}%
                          </span>
                        ) : '—'}
                      </td>
                      <td className="px-4 py-3 text-right text-sm" style={{ color: 'var(--text-primary)' }}>{r.feed_waste_estimate_pct?.toFixed(1) ?? '—'}</td>
                      <td className="px-4 py-3 text-right">
                        <span
                          className={
                            r.trigger_source === 'ai'       ? 'badge-info'
                            : r.trigger_source === 'schedule' ? 'badge-info'
                            : 'badge-info'
                          }
                        >
                          {TRIGGER_LABELS[r.trigger_source] ?? r.trigger_source}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-center">
                        {r.is_emergency_stopped ? (
                          <span className="badge-danger">긴급정지</span>
                        ) : r.is_completed ? (
                          <span className="badge-ok">완료</span>
                        ) : (
                          <span className="badge-warn">진행 중</span>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  )
}
