import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  CartesianGrid, Legend, Line, LineChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { Fish, RefreshCw, TrendingUp } from 'lucide-react'
import { getLatestFishGrowth } from '@/services/api'
import { useThemeStore } from '@/stores/themeStore'
import type { FishGrowthRecord } from '@/types'

const TANK_OPTIONS = ['전체', 'TANK-01', 'TANK-02', 'TANK-03']

function formatDate(iso: string) {
  const d = new Date(iso)
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`
}

export default function GrowthPage() {
  const [tank, setTank] = useState<string>('전체')
  const isDark = useThemeStore((s) => s.isDark)

  const { data: records = [], isFetching, refetch } = useQuery<FishGrowthRecord[]>({
    queryKey: ['fish-growth', tank],
    queryFn: () => getLatestFishGrowth(tank === '전체' ? undefined : tank, 30),
    refetchInterval: 30_000,
  })

  const latest = records[0] ?? null
  const chartData = [...records].reverse().map((r) => ({
    time: formatDate(r.measured_at),
    체중: r.avg_weight_g   != null ? +r.avg_weight_g.toFixed(1)   : null,
    체장: r.avg_length_cm  != null ? +r.avg_length_cm.toFixed(1)  : null,
    바이오매스: r.biomass_kg != null ? +r.biomass_kg.toFixed(2)   : null,
  }))

  const grid      = isDark ? '#243044' : '#E2E8F0'
  const axisFill  = isDark ? '#4B6280' : '#94A3B8'
  const tooltipStyle = {
    backgroundColor: isDark ? '#0C1528' : '#FFFFFF',
    border: `1px solid ${isDark ? '#243044' : '#DDE3EE'}`,
    borderRadius: 8,
    fontSize: 12,
  }

  const kpiItems = [
    { label: '어류 수',    value: latest?.fish_count?.toString(),                   unit: '마리' },
    { label: '평균 체장',  value: latest?.avg_length_cm?.toFixed(1),                unit: 'cm'   },
    { label: '평균 체중',  value: latest?.avg_weight_g?.toFixed(0),                 unit: 'g'    },
    { label: '바이오매스', value: latest?.biomass_kg?.toFixed(1),                   unit: 'kg'   },
    {
      label: '일일 성장률',
      value: latest?.daily_growth_rate_pct != null
        ? `+${latest.daily_growth_rate_pct.toFixed(2)}%`
        : null,
      unit: '',
    },
    { label: 'FCR',        value: latest?.feed_conversion_ratio?.toFixed(2),        unit: ''     },
  ]

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="page-title flex items-center gap-2">
          <Fish size={18} style={{ color: 'var(--ok)' }} />
          성장 관리
        </h1>
        <div className="flex items-center gap-3">
          <select
            value={tank}
            onChange={(e) => setTank(e.target.value)}
            className="input-base"
            style={{ width: 'auto', padding: '6px 12px' }}
          >
            {TANK_OPTIONS.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
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
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        {kpiItems.map(({ label, value, unit }) => (
          <div key={label} className="metric-card">
            <p className="text-xs font-medium mb-1" style={{ color: 'var(--text-muted)' }}>{label}</p>
            <p className="text-xl font-bold" style={{ color: 'var(--text-primary)' }}>
              {value ?? '—'}
              {value && unit && (
                <span className="text-xs font-normal ml-0.5" style={{ color: 'var(--text-muted)' }}>{unit}</span>
              )}
            </p>
          </div>
        ))}
      </div>

      {/* Chart */}
      <div className="card">
        <div className="flex items-center gap-2 mb-4">
          <TrendingUp size={15} style={{ color: 'var(--ok)' }} />
          <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>성장 추세 (최근 30회)</h2>
        </div>
        {chartData.length === 0 ? (
          <div className="h-48 flex items-center justify-center text-sm" style={{ color: 'var(--text-muted)' }}>
            데이터 없음
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={chartData} margin={{ top: 4, right: 16, left: -8, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={grid} />
              <XAxis dataKey="time" tick={{ fill: axisFill, fontSize: 11 }} tickLine={false} interval="preserveStartEnd" />
              <YAxis yAxisId="weight" tick={{ fill: axisFill, fontSize: 11 }} tickLine={false} label={{ value: 'g / cm', angle: -90, position: 'insideLeft', fill: axisFill, fontSize: 11 }} />
              <YAxis yAxisId="bio" orientation="right" tick={{ fill: axisFill, fontSize: 11 }} tickLine={false} label={{ value: 'kg', angle: 90, position: 'insideRight', fill: axisFill, fontSize: 11 }} />
              <Tooltip contentStyle={tooltipStyle} labelStyle={{ color: axisFill }} />
              <Legend wrapperStyle={{ fontSize: 12, color: axisFill }} />
              <Line yAxisId="weight" type="monotone" dataKey="체중"      stroke="var(--ok)"   dot={false} strokeWidth={2} connectNulls />
              <Line yAxisId="weight" type="monotone" dataKey="체장"      stroke="var(--info)" dot={false} strokeWidth={2} connectNulls />
              <Line yAxisId="bio"    type="monotone" dataKey="바이오매스" stroke="var(--warn)" dot={false} strokeWidth={1.5} strokeDasharray="4 2" connectNulls />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* History table */}
      <div className="card p-0 overflow-hidden">
        <div className="px-5 py-3" style={{ borderBottom: '1px solid var(--bg-border)' }}>
          <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>최근 측정 이력</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr style={{ borderBottom: '1px solid var(--bg-border)' }}>
                {['시각','수조','어류 수','체장 (cm)','체중 (g)','바이오매스 (kg)','FCR','신뢰도'].map((h) => (
                  <th
                    key={h}
                    className={`px-4 py-3 text-xs font-semibold ${h === '시각' || h === '수조' ? 'text-left' : 'text-right'}`}
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
                  <td colSpan={8} className="text-center py-10 text-sm" style={{ color: 'var(--text-muted)' }}>
                    측정 기록 없음
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
                    <td className="px-4 py-3 text-sm" style={{ color: 'var(--text-secondary)' }}>{formatDate(r.measured_at)}</td>
                    <td className="px-4 py-3 text-sm" style={{ color: 'var(--text-muted)' }}>{r.tank_id}</td>
                    <td className="px-4 py-3 text-right text-sm" style={{ color: 'var(--text-primary)' }}>{r.fish_count ?? '—'}</td>
                    <td className="px-4 py-3 text-right text-sm" style={{ color: 'var(--text-primary)' }}>{r.avg_length_cm?.toFixed(1) ?? '—'}</td>
                    <td className="px-4 py-3 text-right text-sm" style={{ color: 'var(--text-primary)' }}>{r.avg_weight_g?.toFixed(0) ?? '—'}</td>
                    <td className="px-4 py-3 text-right text-sm" style={{ color: 'var(--text-primary)' }}>{r.biomass_kg?.toFixed(2) ?? '—'}</td>
                    <td className="px-4 py-3 text-right text-sm" style={{ color: 'var(--text-primary)' }}>{r.feed_conversion_ratio?.toFixed(2) ?? '—'}</td>
                    <td className="px-4 py-3 text-right">
                      {r.inference_confidence != null ? (
                        <span className={r.inference_confidence >= 0.8 ? 'badge-ok' : 'badge-warn'}>
                          {(r.inference_confidence * 100).toFixed(0)}%
                        </span>
                      ) : '—'}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
