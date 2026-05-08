// Water quality monitoring panel — displays latest sensor data and 24h chart.

import { useQuery } from '@tanstack/react-query'
import { Droplets, Wifi, WifiOff } from 'lucide-react'
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { getWaterQualityHistory } from '@/services/api'
import { useWebSocket } from '@/hooks/useWebSocket'
import type { WaterQualityReading } from '@/types'

interface Props {
  data: WaterQualityReading | null
  tankId?: string
}

interface MetricProps {
  label: string
  value: number | null
  unit: string
  warning?: boolean
  critical?: boolean
}

function Metric({ label, value, unit, warning, critical }: MetricProps) {
  const colorClass = critical
    ? 'text-red-400'
    : warning
    ? 'text-yellow-400'
    : 'text-slate-100'

  return (
    <div className="flex flex-col gap-0.5">
      <span className="metric-label">{label}</span>
      <span className={`metric-value ${colorClass}`}>
        {value != null ? value.toFixed(2) : '—'}
        <span className="text-sm font-normal text-slate-400 ml-1">{unit}</span>
      </span>
    </div>
  )
}

// Format bucket timestamp for chart x-axis
function formatBucket(isoString: string): string {
  const d = new Date(isoString)
  return `${d.getHours().toString().padStart(2, '0')}:00`
}

export default function WaterQualityPanel({ data: initialData, tankId }: Props) {
  // Real-time WebSocket update (overrides polled data when available)
  const { status: wsStatus, lastMessage } = useWebSocket(tankId ?? 'ALL', {
    enabled: !!tankId,
  })

  const liveReading: WaterQualityReading | null =
    lastMessage?.type === 'water_quality'
      ? (lastMessage.data as WaterQualityReading)
      : null

  const data = liveReading ?? initialData

  // 24 h history from TimescaleDB (used for chart)
  const { data: history = [] } = useQuery({
    queryKey: ['wq-history', tankId],
    queryFn: () =>
      tankId
        ? getWaterQualityHistory(tankId, { limit: 24 })
        : Promise.resolve([]),
    enabled: !!tankId,
    refetchInterval: 60_000,
    select: (rows) =>
      [...rows]
        .reverse()
        .map((r: Record<string, unknown>) => ({
          bucket: formatBucket(r.bucket as string),
          ammonia: r.ammonia_ppm != null ? Number((r.ammonia_ppm as number).toFixed(3)) : null,
          nitrite: r.nitrite_ppm != null ? Number((r.nitrite_ppm as number).toFixed(3)) : null,
        })),
  })

  const ammoniaWarn = (data?.ammonia_ppm ?? 0) >= 0.5
  const ammoniaAlert = (data?.ammonia_ppm ?? 0) >= 1.0
  const nitriteWarn = (data?.nitrite_ppm ?? 0) >= 0.1

  return (
    <div className="card">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Droplets className="w-4 h-4 text-sky-400" />
          <h2 className="font-medium text-slate-200">수질 모니터링</h2>
          {tankId && (
            wsStatus === 'connected' ? (
              <Wifi className="w-3 h-3 text-emerald-400" aria-label="실시간 연결됨" />
            ) : (
              <WifiOff className="w-3 h-3 text-slate-500" aria-label="WebSocket 연결 없음" />
            )
          )}
        </div>
        {data && (
          <span className="text-xs text-slate-500">
            {new Date(data.measured_at).toLocaleTimeString('ko-KR')}
          </span>
        )}
      </div>

      {/* Current readings grid */}
      {data ? (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          <Metric label="수온" value={data.temperature_c} unit="°C" />
          <Metric label="pH" value={data.ph} unit="" />
          <Metric label="용존산소" value={data.dissolved_oxygen_mgl} unit="mg/L" />
          <Metric
            label="암모니아 (가상)"
            value={data.ammonia_ppm}
            unit="ppm"
            warning={ammoniaWarn && !ammoniaAlert}
            critical={ammoniaAlert}
          />
          <Metric
            label="아질산 (가상)"
            value={data.nitrite_ppm}
            unit="ppm"
            warning={nitriteWarn}
          />
          <Metric label="탁도" value={data.turbidity_ntu} unit="NTU" />
        </div>
      ) : (
        <p className="text-slate-500 text-sm">데이터 없음</p>
      )}

      {/* 24 h ammonia & nitrite trend chart */}
      <div className="mt-4">
        {history.length > 0 ? (
          <ResponsiveContainer width="100%" height={96}>
            <LineChart data={history} margin={{ top: 4, right: 4, left: -24, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
              <XAxis
                dataKey="bucket"
                tick={{ fill: '#94a3b8', fontSize: 10 }}
                tickLine={false}
                axisLine={false}
                interval="preserveStartEnd"
              />
              <YAxis
                tick={{ fill: '#94a3b8', fontSize: 10 }}
                tickLine={false}
                axisLine={false}
                domain={[0, 'auto']}
              />
              <Tooltip
                contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 6 }}
                labelStyle={{ color: '#cbd5e1', fontSize: 11 }}
                itemStyle={{ fontSize: 11 }}
              />
              {/* Warning threshold lines */}
              <ReferenceLine y={0.5} stroke="#eab308" strokeDasharray="4 2" strokeWidth={1} />
              <ReferenceLine y={0.1} stroke="#f97316" strokeDasharray="4 2" strokeWidth={1} />
              <Line
                type="monotone"
                dataKey="ammonia"
                stroke="#38bdf8"
                dot={false}
                strokeWidth={1.5}
                name="암모니아"
              />
              <Line
                type="monotone"
                dataKey="nitrite"
                stroke="#fb7185"
                dot={false}
                strokeWidth={1.5}
                name="아질산"
              />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="h-24 bg-slate-700/50 rounded-lg flex items-center justify-center">
            <span className="text-slate-500 text-xs">24h 시계열 데이터 로딩 중…</span>
          </div>
        )}
        <div className="flex gap-4 mt-1 justify-end">
          <span className="flex items-center gap-1 text-xs text-slate-500">
            <span className="w-3 h-0.5 bg-sky-400 inline-block" />암모니아
          </span>
          <span className="flex items-center gap-1 text-xs text-slate-500">
            <span className="w-3 h-0.5 bg-rose-400 inline-block" />아질산
          </span>
        </div>
      </div>
    </div>
  )
}
