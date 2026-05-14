import { useQuery } from '@tanstack/react-query'
import { Fish, TrendingUp } from 'lucide-react'
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { getLatestFishGrowth } from '@/services/api'
import { useThemeStore } from '@/stores/themeStore'
import type { FishGrowthRecord } from '@/types'

interface Props {
  data: FishGrowthRecord | null
  tankId?: string
}

function fmt(iso: string) {
  const d = new Date(iso)
  return `${d.getMonth() + 1}/${d.getDate()}`
}

interface KpiRowProps {
  label: string
  value: React.ReactNode
}

function KpiRow({ label, value }: KpiRowProps) {
  return (
    <div className="elevated-box py-2 px-3">
      <p className="text-xs font-medium mb-0.5" style={{ color: 'var(--text-muted)' }}>{label}</p>
      <p className="text-lg font-bold leading-tight" style={{ color: 'var(--text-primary)' }}>{value}</p>
    </div>
  )
}

export default function FishGrowthPanel({ data, tankId }: Props) {
  const isDark = useThemeStore((s) => s.isDark)

  const { data: history = [] } = useQuery<FishGrowthRecord[]>({
    queryKey: ['fish-growth-mini', tankId],
    queryFn: () => getLatestFishGrowth(tankId, 30),
    enabled: !!tankId,
    refetchInterval: 60_000,
    select: (rows) => [...rows].reverse(),
  })

  const chartData = history.map((r) => ({
    date:  fmt(r.measured_at),
    체중:  r.avg_weight_g   != null ? +r.avg_weight_g.toFixed(0)   : null,
    체장:  r.avg_length_cm  != null ? +r.avg_length_cm.toFixed(1)  : null,
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

  const fcr = data?.feed_conversion_ratio
  const fcrColor =
    fcr == null ? 'var(--text-primary)'
    : fcr <= 1.2 ? 'var(--ok)'
    : fcr <= 1.6 ? 'var(--warn)'
    : 'var(--danger)'

  const growthRate = data?.daily_growth_rate_pct

  return (
    <div className="card">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Fish size={15} style={{ color: 'var(--ok)' }} />
          <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
            성장 관리
          </h2>
        </div>
        <div className="flex items-center gap-2">
          {growthRate != null && growthRate > 0 && (
            <span className="flex items-center gap-1 text-xs font-semibold" style={{ color: 'var(--ok)' }}>
              <TrendingUp size={11} />
              +{growthRate.toFixed(2)}%/day
            </span>
          )}
          {data?.model_version && (
            <span className="badge-info">v{data.model_version}</span>
          )}
        </div>
      </div>

      {/* KPI grid */}
      {data ? (
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
          <KpiRow
            label="어류 수"
            value={<>{data.fish_count ?? '—'}<span className="text-xs font-normal ml-0.5" style={{ color: 'var(--text-muted)' }}>마리</span></>}
          />
          <KpiRow
            label="평균 체장"
            value={<>{data.avg_length_cm?.toFixed(1) ?? '—'}<span className="text-xs font-normal ml-0.5" style={{ color: 'var(--text-muted)' }}>cm</span></>}
          />
          <KpiRow
            label="평균 체중"
            value={<>{data.avg_weight_g?.toFixed(0) ?? '—'}<span className="text-xs font-normal ml-0.5" style={{ color: 'var(--text-muted)' }}>g</span></>}
          />
          <KpiRow
            label="바이오매스"
            value={<>{data.biomass_kg?.toFixed(1) ?? '—'}<span className="text-xs font-normal ml-0.5" style={{ color: 'var(--text-muted)' }}>kg</span></>}
          />
          <KpiRow
            label="일일 성장률"
            value={
              <span style={{ color: (growthRate ?? 0) > 0 ? 'var(--ok)' : 'var(--text-primary)' }}>
                {growthRate != null ? `+${growthRate.toFixed(2)}%` : '—'}
              </span>
            }
          />
          <KpiRow
            label="FCR"
            value={<span style={{ color: fcrColor }}>{fcr?.toFixed(2) ?? '—'}</span>}
          />
        </div>
      ) : (
        <p className="text-sm" style={{ color: 'var(--text-muted)' }}>데이터 없음</p>
      )}

      {/* Chart: weight (Area) + length (Line, right axis) */}
      <div className="mt-4">
        {chartData.length > 1 ? (
          <>
            <ResponsiveContainer width="100%" height={120}>
              <ComposedChart data={chartData} margin={{ top: 4, right: 36, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={grid} vertical={false} />
                <XAxis
                  dataKey="date"
                  tick={{ fill: axisFill, fontSize: 10 }}
                  tickLine={false}
                  axisLine={false}
                  interval="preserveStartEnd"
                />
                <YAxis
                  yAxisId="weight"
                  tick={{ fill: axisFill, fontSize: 10 }}
                  tickLine={false}
                  axisLine={false}
                  domain={[0, 'auto']}
                  unit="g"
                />
                <YAxis
                  yAxisId="length"
                  orientation="right"
                  tick={{ fill: axisFill, fontSize: 10 }}
                  tickLine={false}
                  axisLine={false}
                  domain={[0, 'auto']}
                  unit="cm"
                />
                <Tooltip contentStyle={tooltipStyle} labelStyle={{ color: axisFill }} itemStyle={{ fontSize: 11 }} />
                <Area
                  yAxisId="weight"
                  type="monotone"
                  dataKey="체중"
                  stroke="var(--ok)"
                  fill={isDark ? 'rgba(16,185,129,0.10)' : 'rgba(5,150,105,0.07)'}
                  strokeWidth={2}
                  dot={false}
                  connectNulls
                  name="체중(g)"
                />
                <Line
                  yAxisId="length"
                  type="monotone"
                  dataKey="체장"
                  stroke="var(--teal-400)"
                  strokeDasharray="5 3"
                  strokeWidth={1.5}
                  dot={false}
                  connectNulls
                  name="체장(cm)"
                />
              </ComposedChart>
            </ResponsiveContainer>
            <div className="flex gap-4 mt-1.5 justify-end">
              <span className="flex items-center gap-1 text-xs" style={{ color: 'var(--text-muted)' }}>
                <span className="w-3 h-0.5 inline-block rounded" style={{ backgroundColor: 'var(--ok)' }} />
                체중
              </span>
              <span className="flex items-center gap-1 text-xs" style={{ color: 'var(--text-muted)' }}>
                <span className="flex gap-0.5">
                  <span className="w-2 h-0.5 rounded inline-block" style={{ backgroundColor: 'var(--teal-400)' }} />
                  <span className="w-1 h-0.5 rounded inline-block" style={{ backgroundColor: 'var(--teal-400)' }} />
                </span>
                체장
              </span>
              <span className="text-xs" style={{ color: 'var(--text-muted)' }}>최근 30회</span>
            </div>
          </>
        ) : (
          <div
            className="h-28 rounded-xl flex items-center justify-center"
            style={{ backgroundColor: 'var(--bg-elevated)' }}
          >
            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
              {tankId ? '성장 추세 데이터 로딩 중…' : '수조를 선택하세요'}
            </span>
          </div>
        )}
      </div>
    </div>
  )
}
