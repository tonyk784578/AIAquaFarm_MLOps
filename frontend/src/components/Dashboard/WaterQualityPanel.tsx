import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CheckCircle2, Droplets, Wifi, WifiOff, XCircle } from 'lucide-react'
import {
  CartesianGrid, Line, LineChart, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { getWaterQualityHistory } from '@/services/api'
import { useWebSocket } from '@/hooks/useWebSocket'
import { useThemeStore } from '@/stores/themeStore'
import type { WaterQualityReading } from '@/types'

interface Props {
  data: WaterQualityReading | null
  tankId?: string
}

// Safe ranges for recirculating aquaculture
function getMetricStatus(
  metric: 'temperature' | 'ph' | 'do' | 'ammonia' | 'nitrite' | 'turbidity',
  value: number | null,
): 'ok' | 'warn' | 'danger' | undefined {
  if (value == null) return undefined
  switch (metric) {
    case 'temperature':
      return value < 17 || value > 31 ? 'danger' : value < 20 || value > 28 ? 'warn' : 'ok'
    case 'ph':
      return value < 6.5 || value > 9.0 ? 'danger' : value < 7.0 || value > 8.5 ? 'warn' : 'ok'
    case 'do':
      return value < 4 ? 'danger' : value < 6 ? 'warn' : 'ok'
    case 'ammonia':
      return value >= 1.0 ? 'danger' : value >= 0.5 ? 'warn' : 'ok'
    case 'nitrite':
      return value >= 0.5 ? 'danger' : value >= 0.1 ? 'warn' : 'ok'
    case 'turbidity':
      return value > 20 ? 'danger' : value > 10 ? 'warn' : 'ok'
  }
}

interface MetricProps {
  label: string
  value: number | null
  unit: string
  digits?: number
  status?: 'ok' | 'warn' | 'danger' | undefined
}

function MetricItem({ label, value, unit, digits = 2, status }: MetricProps) {
  const valueColor =
    status === 'danger' ? 'var(--danger)'
    : status === 'warn'   ? 'var(--warn)'
    : 'var(--text-primary)'

  const borderColor =
    status === 'danger' ? 'var(--danger)'
    : status === 'warn'   ? 'var(--warn)'
    : status === 'ok'     ? 'var(--ok)'
    : 'var(--bg-border)'

  const StatusIcon =
    status === 'danger' ? XCircle
    : status === 'warn'   ? XCircle
    : status === 'ok'     ? CheckCircle2
    : null

  const iconColor =
    status === 'danger' ? 'var(--danger)'
    : status === 'warn'   ? 'var(--warn)'
    : 'var(--ok)'

  return (
    <div
      className="metric-card"
      style={{ borderLeft: `3px solid ${borderColor}` }}
    >
      <div className="flex items-center justify-between mb-1">
        <p className="text-xs font-medium" style={{ color: 'var(--text-muted)' }}>{label}</p>
        {StatusIcon && (
          <StatusIcon size={11} style={{ color: iconColor }} />
        )}
      </div>
      <p className="text-xl font-bold tabular-nums" style={{ color: valueColor }}>
        {value != null ? value.toFixed(digits) : '—'}
        {value != null && unit && (
          <span className="text-xs font-normal ml-1" style={{ color: 'var(--text-muted)' }}>{unit}</span>
        )}
      </p>
    </div>
  )
}

function formatBucket(isoString: string): string {
  const d = new Date(isoString)
  return `${d.getHours().toString().padStart(2, '0')}:00`
}

type ChartTab = 'chemical' | 'physical'

export default function WaterQualityPanel({ data: initialData, tankId }: Props) {
  const isDark = useThemeStore((s) => s.isDark)
  const [activeTab, setActiveTab] = useState<ChartTab>('chemical')
  const { status: wsStatus, lastMessage } = useWebSocket(tankId ?? 'ALL', { enabled: !!tankId })

  const liveReading: WaterQualityReading | null =
    lastMessage?.type === 'water_quality' ? (lastMessage.data as WaterQualityReading) : null
  const data = liveReading ?? initialData

  const { data: history = [] } = useQuery({
    queryKey: ['wq-history', tankId],
    queryFn: () =>
      tankId ? getWaterQualityHistory(tankId, { limit: 24 }) : Promise.resolve([]),
    enabled: !!tankId,
    refetchInterval: 60_000,
    select: (rows) =>
      [...rows].reverse().map((r: Record<string, unknown>) => ({
        bucket:      formatBucket(r.bucket as string),
        ammonia:     r.ammonia_ppm             != null ? +(r.ammonia_ppm             as number).toFixed(3) : null,
        nitrite:     r.nitrite_ppm             != null ? +(r.nitrite_ppm             as number).toFixed(3) : null,
        temperature: r.temperature_c           != null ? +(r.temperature_c           as number).toFixed(1) : null,
        do:          r.dissolved_oxygen_mgl    != null ? +(r.dissolved_oxygen_mgl    as number).toFixed(2) : null,
        ph:          r.ph                      != null ? +(r.ph                      as number).toFixed(2) : null,
      })),
  })

  const grid      = isDark ? '#243044' : '#E2E8F0'
  const axisFill  = isDark ? '#4B6280' : '#94A3B8'
  const tooltipBg = isDark ? '#0C1528' : '#FFFFFF'
  const tooltipBorder = isDark ? '#243044' : '#DDE3EE'

  const tooltipStyle = {
    backgroundColor: tooltipBg,
    border: `1px solid ${tooltipBorder}`,
    borderRadius: 8,
    fontSize: 12,
    color: isDark ? '#EEF4FF' : '#0F172A',
  }

  const tempStatus    = getMetricStatus('temperature', data?.temperature_c ?? null)
  const phStatus      = getMetricStatus('ph',          data?.ph ?? null)
  const doStatus      = getMetricStatus('do',          data?.dissolved_oxygen_mgl ?? null)
  const ammoniaStatus = getMetricStatus('ammonia',     data?.ammonia_ppm ?? null)
  const nitriteStatus = getMetricStatus('nitrite',     data?.nitrite_ppm ?? null)
  const turbStatus    = getMetricStatus('turbidity',   data?.turbidity_ntu ?? null)

  const hasHistory = history.length > 0

  return (
    <div className="card h-full">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Droplets size={15} style={{ color: 'var(--info)' }} />
          <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
            수질 모니터링
          </h2>
          {tankId && (
            wsStatus === 'connected'
              ? <Wifi size={12} style={{ color: 'var(--ok)' }} />
              : <WifiOff size={12} style={{ color: 'var(--text-muted)' }} />
          )}
        </div>
        <div className="flex items-center gap-2">
          {data && (
            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
              {new Date(data.measured_at).toLocaleTimeString('ko-KR')}
            </span>
          )}
          {data?.source === 'virtual_sensor' && (
            <span className="badge-info">가상센서</span>
          )}
        </div>
      </div>

      {/* Metric grid */}
      {data ? (
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
          <MetricItem label="수온"    value={data.temperature_c}           unit="°C"    digits={1} status={tempStatus} />
          <MetricItem label="pH"      value={data.ph}                      unit=""      digits={2} status={phStatus} />
          <MetricItem label="용존산소" value={data.dissolved_oxygen_mgl}   unit="mg/L"  digits={2} status={doStatus} />
          <MetricItem label="암모니아" value={data.ammonia_ppm}            unit="ppm"   digits={3} status={ammoniaStatus} />
          <MetricItem label="아질산"   value={data.nitrite_ppm}            unit="ppm"   digits={3} status={nitriteStatus} />
          <MetricItem label="탁도"     value={data.turbidity_ntu}          unit="NTU"   digits={1} status={turbStatus} />
        </div>
      ) : (
        <p className="text-sm" style={{ color: 'var(--text-muted)' }}>데이터 없음</p>
      )}

      {/* Chart section */}
      <div className="mt-4">
        {/* Tab buttons */}
        <div className="flex items-center justify-between mb-2">
          <div className="flex gap-1">
            {(['chemical', 'physical'] as ChartTab[]).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className="text-xs px-2.5 py-1 rounded-lg font-medium transition-all"
                style={
                  activeTab === tab
                    ? {
                        background: isDark
                          ? 'rgba(20,184,166,0.15)'
                          : 'rgba(13,148,136,0.1)',
                        color: 'var(--teal-500)',
                      }
                    : { color: 'var(--text-muted)' }
                }
              >
                {tab === 'chemical' ? '화학 지표' : '환경 지표'}
              </button>
            ))}
          </div>
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>24시간</span>
        </div>

        {hasHistory ? (
          <>
            {/* Chemical tab: Ammonia + Nitrite */}
            {activeTab === 'chemical' && (
              <ResponsiveContainer width="100%" height={140}>
                <LineChart data={history} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={grid} vertical={false} />
                  <XAxis
                    dataKey="bucket"
                    tick={{ fill: axisFill, fontSize: 10 }}
                    tickLine={false}
                    axisLine={false}
                    interval="preserveStartEnd"
                  />
                  <YAxis
                    tick={{ fill: axisFill, fontSize: 10 }}
                    tickLine={false}
                    axisLine={false}
                    domain={[0, 'auto']}
                  />
                  <Tooltip contentStyle={tooltipStyle} labelStyle={{ color: axisFill }} itemStyle={{ fontSize: 11 }} />
                  <ReferenceLine y={0.5} stroke="var(--warn)"   strokeDasharray="4 2" strokeWidth={1} label={{ value: '경고', fill: axisFill, fontSize: 9, position: 'right' }} />
                  <ReferenceLine y={1.0} stroke="var(--danger)" strokeDasharray="4 2" strokeWidth={1} label={{ value: '위험', fill: axisFill, fontSize: 9, position: 'right' }} />
                  <ReferenceLine y={0.1} stroke="var(--warn)"   strokeDasharray="4 2" strokeWidth={1} />
                  <Line type="monotone" dataKey="ammonia" stroke="var(--info)"   dot={false} strokeWidth={2} name="암모니아(ppm)" connectNulls />
                  <Line type="monotone" dataKey="nitrite"  stroke="var(--danger)" dot={false} strokeWidth={2} name="아질산(ppm)"  connectNulls />
                </LineChart>
              </ResponsiveContainer>
            )}

            {/* Physical tab: Temperature + DO */}
            {activeTab === 'physical' && (
              <ResponsiveContainer width="100%" height={140}>
                <LineChart data={history} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={grid} vertical={false} />
                  <XAxis
                    dataKey="bucket"
                    tick={{ fill: axisFill, fontSize: 10 }}
                    tickLine={false}
                    axisLine={false}
                    interval="preserveStartEnd"
                  />
                  <YAxis
                    tick={{ fill: axisFill, fontSize: 10 }}
                    tickLine={false}
                    axisLine={false}
                    domain={[0, 35]}
                  />
                  <Tooltip contentStyle={tooltipStyle} labelStyle={{ color: axisFill }} itemStyle={{ fontSize: 11 }} />
                  <ReferenceLine y={6}  stroke="var(--info)"   strokeDasharray="4 2" strokeWidth={1} label={{ value: 'DO 최소', fill: axisFill, fontSize: 9, position: 'right' }} />
                  <ReferenceLine y={28} stroke="var(--warn)"   strokeDasharray="4 2" strokeWidth={1} label={{ value: '온도 상한', fill: axisFill, fontSize: 9, position: 'right' }} />
                  <Line type="monotone" dataKey="temperature" stroke="var(--warn)" dot={false} strokeWidth={2} name="수온(°C)"         connectNulls />
                  <Line type="monotone" dataKey="do"          stroke="var(--info)" dot={false} strokeWidth={2} name="용존산소(mg/L)"   connectNulls />
                  <Line type="monotone" dataKey="ph"          stroke="var(--ok)"   dot={false} strokeWidth={1.5} name="pH" strokeDasharray="5 3" connectNulls />
                </LineChart>
              </ResponsiveContainer>
            )}

            {/* Legend */}
            <div className="flex gap-4 mt-1.5 justify-end flex-wrap">
              {activeTab === 'chemical' ? (
                <>
                  <LegendDot color="var(--info)"   label="암모니아" />
                  <LegendDot color="var(--danger)" label="아질산" />
                </>
              ) : (
                <>
                  <LegendDot color="var(--warn)"   label="수온(°C)" />
                  <LegendDot color="var(--info)"   label="DO(mg/L)" />
                  <LegendDot color="var(--ok)"     label="pH" dashed />
                </>
              )}
            </div>
          </>
        ) : (
          <div
            className="h-36 rounded-xl flex items-center justify-center"
            style={{ backgroundColor: 'var(--bg-elevated)' }}
          >
            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
              24h 시계열 데이터 로딩 중…
            </span>
          </div>
        )}
      </div>
    </div>
  )
}

function LegendDot({
  color,
  label,
  dashed = false,
}: {
  color: string
  label: string
  dashed?: boolean
}) {
  return (
    <span className="flex items-center gap-1 text-xs" style={{ color: 'var(--text-muted)' }}>
      {dashed ? (
        <span className="flex gap-0.5">
          <span className="w-2 h-0.5 rounded inline-block" style={{ backgroundColor: color }} />
          <span className="w-1 h-0.5 rounded inline-block" style={{ backgroundColor: color }} />
        </span>
      ) : (
        <span className="w-3 h-0.5 inline-block rounded" style={{ backgroundColor: color }} />
      )}
      {label}
    </span>
  )
}
