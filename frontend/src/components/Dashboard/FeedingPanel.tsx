import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Play, Utensils } from 'lucide-react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { getFeedingHistory, triggerFeeding } from '@/services/api'
import { useThemeStore } from '@/stores/themeStore'
import type { FeedingRecord } from '@/types'

interface Props {
  tankId?: string
}

const TRIGGER_LABELS: Record<string, string> = {
  ai: 'AI',
  manual: '수동',
  schedule: '스케줄',
}

export default function FeedingPanel({ tankId }: Props) {
  const qc = useQueryClient()
  const isDark = useThemeStore((s) => s.isDark)

  const { data: records = [] } = useQuery<FeedingRecord[]>({
    queryKey: ['feeding-latest', tankId],
    queryFn: () => getFeedingHistory(tankId, 7),
    enabled: !!tankId,
    refetchInterval: 20_000,
  })

  const latest = records[0] ?? null
  const activityPct = latest?.activity_score != null ? Math.round(latest.activity_score * 100) : 0
  const activityColor =
    activityPct >= 70 ? 'var(--ok)'
    : activityPct >= 40 ? 'var(--warn)'
    : 'var(--danger)'

  const triggerMut = useMutation({
    mutationFn: () => triggerFeeding(tankId!, latest?.recommended_amount_kg ?? 1.0),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['feeding-latest', tankId] }),
  })

  // Build chart data: oldest → newest (records is newest-first)
  const chartData = [...records].reverse().map((r, i) => ({
    session: `S${i + 1}`,
    실제:    r.actual_amount_kg        != null ? +r.actual_amount_kg.toFixed(2)        : 0,
    권장:    r.recommended_amount_kg   != null ? +r.recommended_amount_kg.toFixed(2)   : 0,
    낭비:    r.feed_waste_estimate_pct != null ? +r.feed_waste_estimate_pct.toFixed(1)  : 0,
    source:  r.trigger_source,
  }))

  const grid      = isDark ? '#243044' : '#E2E8F0'
  const axisFill  = isDark ? '#4B6280' : '#94A3B8'
  const tooltipStyle = {
    backgroundColor: isDark ? '#0C1528' : '#FFFFFF',
    border: `1px solid ${isDark ? '#243044' : '#DDE3EE'}`,
    borderRadius: 8,
    fontSize: 12,
    color: isDark ? '#EEF4FF' : '#0F172A',
  }

  return (
    <div className="card">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Utensils size={15} style={{ color: 'var(--warn)' }} />
          <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
            먹이 관리
          </h2>
        </div>
        {tankId && (
          <button
            onClick={() => triggerMut.mutate()}
            disabled={triggerMut.isPending || !tankId}
            className="btn-primary flex items-center gap-1.5 text-xs"
            style={{ padding: '6px 12px' }}
          >
            <Play size={11} />
            {triggerMut.isPending ? '급이 중…' : 'AI 급이'}
          </button>
        )}
      </div>

      <div className="space-y-4">
        {/* Activity bar */}
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
              먹이 활성도
            </span>
            <span className="text-xs font-bold tabular-nums" style={{ color: activityColor }}>
              {latest ? `${activityPct}%` : '—'}
            </span>
          </div>
          <div className="h-2 rounded-full overflow-hidden" style={{ backgroundColor: 'var(--bg-elevated)' }}>
            <div
              className="h-full rounded-full transition-all duration-700"
              style={{ width: `${activityPct}%`, backgroundColor: activityColor }}
            />
          </div>
        </div>

        {/* Latest stat grid */}
        <div className="grid grid-cols-2 gap-2">
          {[
            {
              label: '최근 급이량',
              value: latest?.actual_amount_kg?.toFixed(2),
              unit: 'kg',
              color: 'var(--text-primary)',
            },
            {
              label: 'AI 권장량',
              value: latest?.recommended_amount_kg?.toFixed(2),
              unit: 'kg',
              color: 'var(--warn)',
            },
            {
              label: '사료 낭비',
              value: latest?.feed_waste_estimate_pct?.toFixed(1),
              unit: '%',
              color:
                (latest?.feed_waste_estimate_pct ?? 0) > 15
                  ? 'var(--danger)'
                  : (latest?.feed_waste_estimate_pct ?? 0) > 8
                  ? 'var(--warn)'
                  : 'var(--ok)',
            },
            {
              label: '트리거',
              value: latest?.trigger_source ? TRIGGER_LABELS[latest.trigger_source] : null,
              unit: '',
              color: latest?.trigger_source === 'ai' ? 'var(--info)' : 'var(--text-secondary)',
            },
          ].map(({ label, value, unit, color }) => (
            <div
              key={label}
              className="elevated-box py-2 px-3"
            >
              <p className="text-xs mb-0.5" style={{ color: 'var(--text-muted)' }}>{label}</p>
              <p className="text-lg font-bold" style={{ color }}>
                {value ?? '—'}
                {value && unit && (
                  <span className="text-xs font-normal ml-0.5" style={{ color: 'var(--text-muted)' }}>
                    {unit}
                  </span>
                )}
              </p>
            </div>
          ))}
        </div>

        {/* Bar chart: last 7 sessions actual vs recommended */}
        {chartData.length > 0 && (
          <div>
            <p className="text-xs mb-2" style={{ color: 'var(--text-muted)' }}>
              최근 {chartData.length}회 급이량 비교
            </p>
            <ResponsiveContainer width="100%" height={100}>
              <BarChart data={chartData} barCategoryGap="25%" barGap={2} margin={{ top: 4, right: 4, left: -28, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={grid} vertical={false} />
                <XAxis
                  dataKey="session"
                  tick={{ fill: axisFill, fontSize: 10 }}
                  tickLine={false}
                  axisLine={false}
                />
                <YAxis
                  tick={{ fill: axisFill, fontSize: 10 }}
                  tickLine={false}
                  axisLine={false}
                  unit="kg"
                  width={36}
                />
                <Tooltip
                  contentStyle={tooltipStyle}
                  labelStyle={{ color: axisFill }}
                  itemStyle={{ fontSize: 11 }}
                  formatter={(v: number, name: string) => [`${v} kg`, name]}
                />
                <Bar dataKey="권장" name="권장량" radius={[3, 3, 0, 0]}>
                  {chartData.map((_entry, idx) => (
                    <Cell
                      key={idx}
                      fill={isDark ? 'rgba(37,99,235,0.35)' : 'rgba(37,99,235,0.2)'}
                    />
                  ))}
                </Bar>
                <Bar dataKey="실제" name="실제급이" radius={[3, 3, 0, 0]}>
                  {chartData.map((_entry, idx) => (
                    <Cell
                      key={idx}
                      fill={isDark ? 'rgba(245,158,11,0.85)' : 'rgba(217,119,6,0.7)'}
                    />
                  ))}
                  <LabelList
                    dataKey="낭비"
                    position="top"
                    style={{ fill: axisFill, fontSize: 9 }}
                    formatter={(v: number) => (v > 0 ? `${v}%` : '')}
                  />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
            <div className="flex gap-4 mt-1 justify-end">
              <span className="flex items-center gap-1 text-xs" style={{ color: 'var(--text-muted)' }}>
                <span className="w-3 h-0.5 inline-block rounded" style={{ backgroundColor: isDark ? 'rgba(37,99,235,0.6)' : 'rgba(37,99,235,0.5)' }} />
                권장량
              </span>
              <span className="flex items-center gap-1 text-xs" style={{ color: 'var(--text-muted)' }}>
                <span className="w-3 h-0.5 inline-block rounded" style={{ backgroundColor: 'var(--warn)' }} />
                실제급이
              </span>
            </div>
          </div>
        )}
      </div>

      {!tankId && (
        <div className="mt-4 flex items-center justify-center h-10">
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>수조를 선택하세요</span>
        </div>
      )}
    </div>
  )
}
