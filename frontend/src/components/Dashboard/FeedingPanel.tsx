import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Play, Utensils } from 'lucide-react'
import { getFeedingHistory, triggerFeeding } from '@/services/api'
import type { FeedingRecord } from '@/types'

interface Props {
  tankId?: string
}

export default function FeedingPanel({ tankId }: Props) {
  const qc = useQueryClient()

  const { data: records = [] } = useQuery<FeedingRecord[]>({
    queryKey: ['feeding-latest', tankId],
    queryFn: () => getFeedingHistory(tankId, 1),
    enabled: !!tankId,
    refetchInterval: 20_000,
  })

  const latest = records[0] ?? null
  const activityPct = latest?.activity_score != null ? Math.round(latest.activity_score * 100) : 0
  const barColor =
    activityPct >= 70 ? 'bg-emerald-400' : activityPct >= 40 ? 'bg-amber-400' : 'bg-red-400'

  const triggerMut = useMutation({
    mutationFn: () =>
      triggerFeeding(tankId!, latest?.recommended_amount_kg ?? 1.0),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['feeding-latest', tankId] }),
  })

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Utensils className="w-4 h-4 text-amber-400" />
          <h2 className="font-medium text-slate-200">먹이 관리</h2>
        </div>
        {tankId && (
          <button
            onClick={() => triggerMut.mutate()}
            disabled={triggerMut.isPending || !tankId}
            title="AI 권장량으로 급이"
            className="flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg bg-amber-500/20 text-amber-400 hover:bg-amber-500/30 disabled:opacity-40 transition-colors"
          >
            <Play className="w-3 h-3" />
            {triggerMut.isPending ? '급이 중…' : 'AI 급이'}
          </button>
        )}
      </div>

      {/* Activity score bar */}
      <div className="space-y-3">
        <div>
          <div className="flex items-center justify-between mb-1">
            <span className="metric-label">먹이활성도</span>
            <span className={`text-xs ${activityPct >= 70 ? 'text-emerald-400' : activityPct >= 40 ? 'text-amber-400' : 'text-red-400'}`}>
              {latest ? `${activityPct}%` : '—'}
            </span>
          </div>
          <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-700 ${barColor}`}
              style={{ width: `${activityPct}%` }}
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <span className="metric-label">최근 급이량</span>
            <span className="metric-value">
              {latest?.actual_amount_kg?.toFixed(2) ?? '—'}
              <span className="text-sm font-normal text-slate-400 ml-1">kg</span>
            </span>
          </div>
          <div>
            <span className="metric-label">AI 권장 급이량</span>
            <span className="metric-value text-amber-400">
              {latest?.recommended_amount_kg?.toFixed(2) ?? '—'}
              <span className="text-sm font-normal text-slate-400 ml-1">kg</span>
            </span>
          </div>
          <div>
            <span className="metric-label">사료 낭비 추정</span>
            <span className="metric-value">
              {latest?.feed_waste_estimate_pct?.toFixed(1) ?? '—'}
              <span className="text-sm font-normal text-slate-400 ml-1">%</span>
            </span>
          </div>
          <div>
            <span className="metric-label">트리거</span>
            <span className="metric-value text-sm">
              {latest?.trigger_source === 'ai' ? 'AI'
                : latest?.trigger_source === 'manual' ? '수동'
                : latest?.trigger_source === 'schedule' ? '스케줄'
                : '—'}
            </span>
          </div>
        </div>
      </div>

      {!tankId && (
        <div className="mt-4 h-10 flex items-center justify-center">
          <span className="text-slate-500 text-xs">수조를 선택하세요</span>
        </div>
      )}
    </div>
  )
}
