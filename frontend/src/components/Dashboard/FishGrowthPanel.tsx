import { useQuery } from '@tanstack/react-query'
import { Fish } from 'lucide-react'
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
} from 'recharts'
import { getLatestFishGrowth } from '@/services/api'
import type { FishGrowthRecord } from '@/types'

interface Props {
  data: FishGrowthRecord | null
  tankId?: string
}

function fmt(iso: string) {
  const d = new Date(iso)
  return `${d.getMonth() + 1}/${d.getDate()}`
}

export default function FishGrowthPanel({ data, tankId }: Props) {
  const { data: history = [] } = useQuery<FishGrowthRecord[]>({
    queryKey: ['fish-growth-mini', tankId],
    queryFn: () => getLatestFishGrowth(tankId, 14),
    enabled: !!tankId,
    refetchInterval: 60_000,
    select: (rows) => [...rows].reverse(),
  })

  const chartData = history.map((r) => ({
    date: fmt(r.measured_at),
    체중: r.avg_weight_g != null ? +r.avg_weight_g.toFixed(0) : null,
  }))

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Fish className="w-4 h-4 text-emerald-400" />
          <h2 className="font-medium text-slate-200">성장 관리</h2>
        </div>
        {data?.model_version && (
          <span className="text-xs text-slate-500">v{data.model_version}</span>
        )}
      </div>

      {data ? (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          <div>
            <span className="metric-label">어류 수</span>
            <span className="metric-value">{data.fish_count ?? '—'}</span>
          </div>
          <div>
            <span className="metric-label">평균 체장</span>
            <span className="metric-value">
              {data.avg_length_cm?.toFixed(1) ?? '—'}
              <span className="text-sm font-normal text-slate-400 ml-1">cm</span>
            </span>
          </div>
          <div>
            <span className="metric-label">평균 체중</span>
            <span className="metric-value">
              {data.avg_weight_g?.toFixed(0) ?? '—'}
              <span className="text-sm font-normal text-slate-400 ml-1">g</span>
            </span>
          </div>
          <div>
            <span className="metric-label">총 바이오매스</span>
            <span className="metric-value">
              {data.biomass_kg?.toFixed(1) ?? '—'}
              <span className="text-sm font-normal text-slate-400 ml-1">kg</span>
            </span>
          </div>
          <div>
            <span className="metric-label">일일 성장률</span>
            <span className={`metric-value ${(data.daily_growth_rate_pct ?? 0) > 0 ? 'text-emerald-400' : 'text-slate-100'}`}>
              {data.daily_growth_rate_pct != null
                ? `+${data.daily_growth_rate_pct.toFixed(2)}%`
                : '—'}
            </span>
          </div>
          <div>
            <span className="metric-label">FCR</span>
            <span className="metric-value">
              {data.feed_conversion_ratio?.toFixed(2) ?? '—'}
            </span>
          </div>
        </div>
      ) : (
        <p className="text-slate-500 text-sm">데이터 없음</p>
      )}

      {/* Mini weight trend chart */}
      <div className="mt-4">
        {chartData.length > 1 ? (
          <ResponsiveContainer width="100%" height={80}>
            <LineChart data={chartData} margin={{ top: 2, right: 4, left: -28, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
              <XAxis
                dataKey="date"
                tick={{ fill: '#64748b', fontSize: 10 }}
                tickLine={false}
                axisLine={false}
                interval="preserveStartEnd"
              />
              <Tooltip
                contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 6, fontSize: 11 }}
                labelStyle={{ color: '#94a3b8' }}
              />
              <Line
                type="monotone"
                dataKey="체중"
                stroke="#34d399"
                dot={false}
                strokeWidth={2}
                connectNulls
              />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="h-20 bg-slate-700/50 rounded-lg flex items-center justify-center">
            <span className="text-slate-500 text-xs">
              {tankId ? '체중 추세 데이터 로딩 중…' : '수조를 선택하세요'}
            </span>
          </div>
        )}
        {chartData.length > 1 && (
          <p className="text-xs text-slate-600 mt-1 text-right">평균 체중 추세 (최근 14회)</p>
        )}
      </div>
    </div>
  )
}
