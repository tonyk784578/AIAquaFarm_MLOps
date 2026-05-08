import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Fish, RefreshCw, TrendingUp } from 'lucide-react'
import { getLatestFishGrowth } from '@/services/api'
import type { FishGrowthRecord } from '@/types'

const TANK_OPTIONS = ['전체', 'TANK-01', 'TANK-02', 'TANK-03']

function kpi(label: string, value: string | null, unit = '') {
  return (
    <div className="bg-slate-800 rounded-xl p-4 border border-slate-700">
      <p className="text-xs text-slate-400 mb-1">{label}</p>
      <p className="text-2xl font-bold text-slate-100">
        {value ?? '—'}
        {value && unit && (
          <span className="text-sm font-normal text-slate-400 ml-1">{unit}</span>
        )}
      </p>
    </div>
  )
}

function formatDate(iso: string) {
  const d = new Date(iso)
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`
}

export default function GrowthPage() {
  const [tank, setTank] = useState<string>('전체')

  const { data: records = [], isFetching, refetch } = useQuery<FishGrowthRecord[]>({
    queryKey: ['fish-growth', tank],
    queryFn: () => getLatestFishGrowth(tank === '전체' ? undefined : tank, 30),
    refetchInterval: 30_000,
  })

  const latest = records[0] ?? null

  const chartData = [...records]
    .reverse()
    .map((r) => ({
      time: formatDate(r.measured_at),
      체중: r.avg_weight_g != null ? +r.avg_weight_g.toFixed(1) : null,
      체장: r.avg_length_cm != null ? +r.avg_length_cm.toFixed(1) : null,
      바이오매스: r.biomass_kg != null ? +r.biomass_kg.toFixed(2) : null,
    }))

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Fish className="w-5 h-5 text-emerald-400" />
          <h1 className="text-lg font-semibold text-slate-100">성장 관리</h1>
        </div>
        <div className="flex items-center gap-3">
          {/* Tank selector */}
          <select
            value={tank}
            onChange={(e) => setTank(e.target.value)}
            className="bg-slate-800 border border-slate-600 text-slate-200 text-sm rounded-lg px-3 py-1.5 focus:ring-1 focus:ring-sky-500 outline-none"
          >
            {TANK_OPTIONS.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isFetching ? 'animate-spin' : ''}`} />
            새로고침
          </button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        {kpi('어류 수', latest?.fish_count?.toString() ?? null, '마리')}
        {kpi('평균 체장', latest?.avg_length_cm?.toFixed(1) ?? null, 'cm')}
        {kpi('평균 체중', latest?.avg_weight_g?.toFixed(0) ?? null, 'g')}
        {kpi('바이오매스', latest?.biomass_kg?.toFixed(1) ?? null, 'kg')}
        {kpi(
          '일일 성장률',
          latest?.daily_growth_rate_pct != null
            ? `+${latest.daily_growth_rate_pct.toFixed(2)}%`
            : null,
        )}
        {kpi('FCR', latest?.feed_conversion_ratio?.toFixed(2) ?? null)}
      </div>

      {/* Growth Trend Chart */}
      <div className="bg-slate-800 rounded-xl border border-slate-700 p-5">
        <div className="flex items-center gap-2 mb-4">
          <TrendingUp className="w-4 h-4 text-emerald-400" />
          <h2 className="text-sm font-medium text-slate-200">성장 추세 (최근 30회)</h2>
        </div>
        {chartData.length === 0 ? (
          <div className="h-48 flex items-center justify-center text-slate-500 text-sm">
            데이터 없음
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={chartData} margin={{ top: 4, right: 16, left: -8, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis
                dataKey="time"
                tick={{ fill: '#94a3b8', fontSize: 11 }}
                tickLine={false}
                interval="preserveStartEnd"
              />
              <YAxis
                yAxisId="weight"
                tick={{ fill: '#94a3b8', fontSize: 11 }}
                tickLine={false}
                label={{ value: 'g / cm', angle: -90, position: 'insideLeft', fill: '#64748b', fontSize: 11 }}
              />
              <YAxis
                yAxisId="bio"
                orientation="right"
                tick={{ fill: '#94a3b8', fontSize: 11 }}
                tickLine={false}
                label={{ value: 'kg', angle: 90, position: 'insideRight', fill: '#64748b', fontSize: 11 }}
              />
              <Tooltip
                contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }}
                labelStyle={{ color: '#94a3b8' }}
              />
              <Legend wrapperStyle={{ fontSize: 12, color: '#94a3b8' }} />
              <Line
                yAxisId="weight"
                type="monotone"
                dataKey="체중"
                stroke="#34d399"
                dot={false}
                strokeWidth={2}
                connectNulls
              />
              <Line
                yAxisId="weight"
                type="monotone"
                dataKey="체장"
                stroke="#60a5fa"
                dot={false}
                strokeWidth={2}
                connectNulls
              />
              <Line
                yAxisId="bio"
                type="monotone"
                dataKey="바이오매스"
                stroke="#f59e0b"
                dot={false}
                strokeWidth={1.5}
                strokeDasharray="4 2"
                connectNulls
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* History Table */}
      <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
        <div className="px-5 py-3 border-b border-slate-700">
          <h2 className="text-sm font-medium text-slate-200">최근 측정 이력</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-slate-400 border-b border-slate-700">
                <th className="text-left px-4 py-2.5 font-medium">시각</th>
                <th className="text-left px-4 py-2.5 font-medium">수조</th>
                <th className="text-right px-4 py-2.5 font-medium">어류 수</th>
                <th className="text-right px-4 py-2.5 font-medium">체장 (cm)</th>
                <th className="text-right px-4 py-2.5 font-medium">체중 (g)</th>
                <th className="text-right px-4 py-2.5 font-medium">바이오매스 (kg)</th>
                <th className="text-right px-4 py-2.5 font-medium">FCR</th>
                <th className="text-right px-4 py-2.5 font-medium">신뢰도</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700/50">
              {records.length === 0 ? (
                <tr>
                  <td colSpan={8} className="text-center py-8 text-slate-500">
                    측정 기록 없음
                  </td>
                </tr>
              ) : (
                records.map((r) => (
                  <tr key={r.id} className="hover:bg-slate-700/30 transition-colors">
                    <td className="px-4 py-2.5 text-slate-300">{formatDate(r.measured_at)}</td>
                    <td className="px-4 py-2.5 text-slate-400">{r.tank_id}</td>
                    <td className="px-4 py-2.5 text-right text-slate-200">{r.fish_count ?? '—'}</td>
                    <td className="px-4 py-2.5 text-right text-slate-200">{r.avg_length_cm?.toFixed(1) ?? '—'}</td>
                    <td className="px-4 py-2.5 text-right text-slate-200">{r.avg_weight_g?.toFixed(0) ?? '—'}</td>
                    <td className="px-4 py-2.5 text-right text-slate-200">{r.biomass_kg?.toFixed(2) ?? '—'}</td>
                    <td className="px-4 py-2.5 text-right text-slate-200">{r.feed_conversion_ratio?.toFixed(2) ?? '—'}</td>
                    <td className="px-4 py-2.5 text-right">
                      {r.inference_confidence != null ? (
                        <span className={`text-xs px-1.5 py-0.5 rounded ${r.inference_confidence >= 0.8 ? 'text-emerald-400 bg-emerald-400/10' : 'text-yellow-400 bg-yellow-400/10'}`}>
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
