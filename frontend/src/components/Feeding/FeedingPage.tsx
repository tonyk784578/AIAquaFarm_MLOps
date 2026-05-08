import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BarChart2, Play, RefreshCw, Utensils } from 'lucide-react'
import { getFeedingHistory, stopFeeding, triggerFeeding } from '@/services/api'
import type { FeedingRecord } from '@/types'

const TANK_OPTIONS = ['TANK-01', 'TANK-02', 'TANK-03']

const TRIGGER_LABELS: Record<string, string> = {
  ai: 'AI',
  manual: '수동',
  schedule: '스케줄',
}

function formatDate(iso: string) {
  const d = new Date(iso)
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`
}

function ActivityBar({ score }: { score: number | null }) {
  const pct = score != null ? Math.round(score * 100) : 0
  const color =
    pct >= 70 ? 'bg-emerald-400' : pct >= 40 ? 'bg-amber-400' : 'bg-red-400'
  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="text-slate-400">먹이활성도</span>
        <span className={pct >= 70 ? 'text-emerald-400' : pct >= 40 ? 'text-amber-400' : 'text-red-400'}>
          {score != null ? `${pct}%` : '—'}
        </span>
      </div>
      <div className="h-2.5 bg-slate-700 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 ${color}`}
          style={{ width: `${pct}%` }}
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
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Utensils className="w-5 h-5 text-amber-400" />
          <h1 className="text-lg font-semibold text-slate-100">급이 관리</h1>
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

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: status + trigger */}
        <div className="space-y-4">
          {/* Tank selector */}
          <div className="bg-slate-800 rounded-xl border border-slate-700 p-4 space-y-3">
            <label className="text-xs text-slate-400 font-medium">수조 선택</label>
            <div className="flex gap-2">
              {TANK_OPTIONS.map((t) => (
                <button
                  key={t}
                  onClick={() => setTank(t)}
                  className={`flex-1 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                    tank === t
                      ? 'bg-sky-500/20 text-sky-400 border border-sky-500/40'
                      : 'bg-slate-700 text-slate-400 hover:text-slate-200'
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>

          {/* Current status */}
          <div className="bg-slate-800 rounded-xl border border-slate-700 p-4 space-y-4">
            <h2 className="text-sm font-medium text-slate-200">현재 상태</h2>
            <ActivityBar score={latest?.activity_score ?? null} />
            <div className="grid grid-cols-2 gap-3">
              <div>
                <p className="text-xs text-slate-400 mb-0.5">최근 급이량</p>
                <p className="text-lg font-bold text-slate-100">
                  {latest?.actual_amount_kg?.toFixed(2) ?? '—'}
                  <span className="text-xs font-normal text-slate-400 ml-1">kg</span>
                </p>
              </div>
              <div>
                <p className="text-xs text-slate-400 mb-0.5">AI 권장량</p>
                <p className="text-lg font-bold text-amber-400">
                  {latest?.recommended_amount_kg?.toFixed(2) ?? '—'}
                  <span className="text-xs font-normal text-slate-400 ml-1">kg</span>
                </p>
              </div>
              <div>
                <p className="text-xs text-slate-400 mb-0.5">사료 낭비</p>
                <p className="text-lg font-bold text-slate-100">
                  {latest?.feed_waste_estimate_pct?.toFixed(1) ?? '—'}
                  <span className="text-xs font-normal text-slate-400 ml-1">%</span>
                </p>
              </div>
              <div>
                <p className="text-xs text-slate-400 mb-0.5">트리거</p>
                <p className="text-lg font-bold text-slate-100">
                  {latest?.trigger_source ? TRIGGER_LABELS[latest.trigger_source] : '—'}
                </p>
              </div>
            </div>
          </div>

          {/* Manual trigger */}
          <div className="bg-slate-800 rounded-xl border border-slate-700 p-4 space-y-3">
            <h2 className="text-sm font-medium text-slate-200">수동 급이</h2>
            <div>
              <label className="text-xs text-slate-400">급이량 (kg)</label>
              <input
                type="number"
                min="0.1"
                max="10"
                step="0.1"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                className="mt-1 w-full bg-slate-700 border border-slate-600 text-slate-100 text-sm rounded-lg px-3 py-2 outline-none focus:ring-1 focus:ring-amber-500"
              />
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => triggerMut.mutate()}
                disabled={triggerMut.isPending}
                className="flex-1 flex items-center justify-center gap-1.5 bg-amber-500 hover:bg-amber-400 disabled:opacity-50 text-slate-900 font-medium text-sm py-2 rounded-lg transition-colors"
              >
                <Play className="w-3.5 h-3.5" />
                {triggerMut.isPending ? '급이 중…' : '급이 시작'}
              </button>
              <button
                onClick={() => stopMut.mutate()}
                disabled={stopMut.isPending}
                className="px-3 py-2 bg-red-500/20 hover:bg-red-500/30 text-red-400 text-sm rounded-lg transition-colors disabled:opacity-50"
              >
                정지
              </button>
            </div>
            {triggerMut.isError && (
              <p className="text-xs text-red-400">급이 명령 실패</p>
            )}
          </div>
        </div>

        {/* Right: history table */}
        <div className="lg:col-span-2 bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
          <div className="px-5 py-3 border-b border-slate-700 flex items-center gap-2">
            <BarChart2 className="w-4 h-4 text-amber-400" />
            <h2 className="text-sm font-medium text-slate-200">급이 이력 (최근 30회)</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-slate-400 border-b border-slate-700">
                  <th className="text-left px-4 py-2.5 font-medium">시각</th>
                  <th className="text-right px-4 py-2.5 font-medium">급이량 (kg)</th>
                  <th className="text-right px-4 py-2.5 font-medium">권장량 (kg)</th>
                  <th className="text-right px-4 py-2.5 font-medium">활성도</th>
                  <th className="text-right px-4 py-2.5 font-medium">낭비 (%)</th>
                  <th className="text-center px-4 py-2.5 font-medium">트리거</th>
                  <th className="text-center px-4 py-2.5 font-medium">완료</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700/50">
                {records.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="text-center py-10 text-slate-500">
                      급이 기록 없음
                    </td>
                  </tr>
                ) : (
                  records.map((r) => (
                    <tr key={r.id} className="hover:bg-slate-700/30 transition-colors">
                      <td className="px-4 py-2.5 text-slate-300">{formatDate(r.started_at)}</td>
                      <td className="px-4 py-2.5 text-right text-slate-200">
                        {r.actual_amount_kg?.toFixed(2) ?? '—'}
                      </td>
                      <td className="px-4 py-2.5 text-right text-amber-400">
                        {r.recommended_amount_kg?.toFixed(2) ?? '—'}
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        {r.activity_score != null ? (
                          <span className={`text-xs px-1.5 py-0.5 rounded ${
                            r.activity_score >= 0.7
                              ? 'text-emerald-400 bg-emerald-400/10'
                              : r.activity_score >= 0.4
                              ? 'text-amber-400 bg-amber-400/10'
                              : 'text-red-400 bg-red-400/10'
                          }`}>
                            {(r.activity_score * 100).toFixed(0)}%
                          </span>
                        ) : '—'}
                      </td>
                      <td className="px-4 py-2.5 text-right text-slate-300">
                        {r.feed_waste_estimate_pct?.toFixed(1) ?? '—'}
                      </td>
                      <td className="px-4 py-2.5 text-center">
                        <span className={`text-xs px-1.5 py-0.5 rounded ${
                          r.trigger_source === 'ai'
                            ? 'text-sky-400 bg-sky-400/10'
                            : r.trigger_source === 'schedule'
                            ? 'text-purple-400 bg-purple-400/10'
                            : 'text-slate-400 bg-slate-600'
                        }`}>
                          {TRIGGER_LABELS[r.trigger_source] ?? r.trigger_source}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-center">
                        {r.is_emergency_stopped ? (
                          <span className="text-xs text-red-400">긴급정지</span>
                        ) : r.is_completed ? (
                          <span className="text-xs text-emerald-400">완료</span>
                        ) : (
                          <span className="text-xs text-amber-400">진행 중</span>
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
