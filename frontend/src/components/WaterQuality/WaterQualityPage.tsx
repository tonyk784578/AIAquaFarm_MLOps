import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CheckCircle2, Droplets, Wifi, WifiOff, XCircle } from 'lucide-react'
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { getLatestWaterQuality, getWaterQualityHistory, listTanks } from '@/services/api'
import { useWebSocket } from '@/hooks/useWebSocket'
import { useThemeStore } from '@/stores/themeStore'
import type { WaterQualityReading } from '@/types'

// ── Safe range helpers ────────────────────────────────────────────────────────

type MetricKey = 'temperature' | 'ph' | 'do' | 'ammonia' | 'nitrite' | 'turbidity'

interface SafeRange { ok: [number, number]; warn: [number, number] }

const SAFE_RANGES: Record<MetricKey, SafeRange> = {
  temperature: { ok: [20, 28],  warn: [17, 31] },
  ph:          { ok: [7.0, 8.5], warn: [6.5, 9.0] },
  do:          { ok: [6, 99],   warn: [4, 99] },
  ammonia:     { ok: [0, 0.5],  warn: [0, 1.0] },
  nitrite:     { ok: [0, 0.1],  warn: [0, 0.5] },
  turbidity:   { ok: [0, 10],   warn: [0, 20] },
}

function getStatus(metric: MetricKey, value: number | null): 'ok' | 'warn' | 'danger' | undefined {
  if (value == null) return undefined
  const r = SAFE_RANGES[metric]
  if (value >= r.ok[0] && value <= r.ok[1]) return 'ok'
  if (value >= r.warn[0] && value <= r.warn[1]) return 'warn'
  return 'danger'
}

// ── Big metric card ───────────────────────────────────────────────────────────

interface BigMetricProps {
  label: string
  value: number | null
  unit: string
  digits: number
  metric: MetricKey
  safeRange: string
}

function BigMetric({ label, value, unit, digits, metric, safeRange }: BigMetricProps) {
  const status = getStatus(metric, value)

  const valueColor =
    status === 'danger' ? 'var(--danger)'
    : status === 'warn'   ? 'var(--warn)'
    : 'var(--text-primary)'

  const borderColor =
    status === 'danger' ? 'var(--danger)'
    : status === 'warn'   ? 'var(--warn)'
    : status === 'ok'     ? 'var(--ok)'
    : 'var(--bg-border)'

  const StatusIcon = status === 'ok' ? CheckCircle2 : status ? XCircle : null
  const iconColor  = status === 'ok' ? 'var(--ok)' : status === 'warn' ? 'var(--warn)' : 'var(--danger)'

  return (
    <div
      className="metric-card"
      style={{ borderLeft: `3px solid ${borderColor}` }}
    >
      <div className="flex items-center justify-between mb-1">
        <p className="text-xs font-semibold" style={{ color: 'var(--text-muted)' }}>{label}</p>
        {StatusIcon && <StatusIcon size={13} style={{ color: iconColor }} />}
      </div>
      <p className="text-3xl font-bold tabular-nums" style={{ color: valueColor }}>
        {value != null ? value.toFixed(digits) : '—'}
        <span className="text-sm font-normal ml-1" style={{ color: 'var(--text-muted)' }}>{unit}</span>
      </p>
      <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>적정: {safeRange}</p>
    </div>
  )
}

// ── History chart ─────────────────────────────────────────────────────────────

const BUCKET_OPTIONS = [
  { label: '1시간',  minutes: 5,   limit: 12 },
  { label: '6시간',  minutes: 30,  limit: 12 },
  { label: '24시간', minutes: 60,  limit: 24 },
  { label: '7일',    minutes: 720, limit: 14 },
]

function formatBucket(iso: string, bucketMins: number): string {
  const d = new Date(iso)
  if (bucketMins >= 720) return `${(d.getMonth() + 1)}/${d.getDate()}`
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
}

interface HistoryChartProps {
  tankId: string
  isDark: boolean
}

function ChemicalHistoryChart({ tankId, isDark }: HistoryChartProps) {
  const [bucketIdx, setBucketIdx] = useState(2) // default 24h
  const bucket = BUCKET_OPTIONS[bucketIdx]

  const { data: history = [], isLoading } = useQuery({
    queryKey: ['wq-history-chemical', tankId, bucketIdx],
    queryFn: () =>
      getWaterQualityHistory(tankId, { bucket_minutes: bucket.minutes, limit: bucket.limit }),
    enabled: !!tankId,
    refetchInterval: 60_000,
    select: (rows) =>
      [...rows].reverse().map((r: Record<string, unknown>) => ({
        bucket:   formatBucket(r.bucket as string, bucket.minutes),
        ammonia:  r.ammonia_ppm  != null ? +(r.ammonia_ppm  as number).toFixed(3) : null,
        nitrite:  r.nitrite_ppm  != null ? +(r.nitrite_ppm  as number).toFixed(3) : null,
      })),
  })

  const grid     = isDark ? '#243044' : '#E2E8F0'
  const axisClr  = isDark ? '#4B6280' : '#94A3B8'
  const tipStyle = {
    backgroundColor: isDark ? '#0C1528' : '#FFFFFF',
    border: `1px solid ${isDark ? '#243044' : '#DDE3EE'}`,
    borderRadius: 8, fontSize: 12,
    color: isDark ? '#EEF4FF' : '#0F172A',
  }

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
          암모니아 · 아질산 추이
        </h3>
        <div className="flex gap-1">
          {BUCKET_OPTIONS.map((opt, i) => (
            <button
              key={i}
              onClick={() => setBucketIdx(i)}
              className="text-xs px-2 py-0.5 rounded-md font-medium transition-all"
              style={
                bucketIdx === i
                  ? { background: 'linear-gradient(135deg,var(--teal-500),var(--blue-500))', color: '#fff' }
                  : { color: 'var(--text-muted)' }
              }
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <div className="h-48 flex items-center justify-center">
          <span className="text-xs animate-pulse" style={{ color: 'var(--text-muted)' }}>로딩 중…</span>
        </div>
      ) : history.length > 0 ? (
        <>
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={history} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={grid} vertical={false} />
              <XAxis dataKey="bucket" tick={{ fill: axisClr, fontSize: 10 }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
              <YAxis tick={{ fill: axisClr, fontSize: 10 }} tickLine={false} axisLine={false} domain={[0, 'auto']} />
              <Tooltip contentStyle={tipStyle} labelStyle={{ color: axisClr }} itemStyle={{ fontSize: 11 }} />
              <ReferenceLine y={0.5} stroke="var(--warn)"   strokeDasharray="4 2" strokeWidth={1} label={{ value: '암모니아 경고(0.5)', fill: axisClr, fontSize: 9, position: 'insideTopRight' }} />
              <ReferenceLine y={1.0} stroke="var(--danger)" strokeDasharray="4 2" strokeWidth={1} label={{ value: '암모니아 위험(1.0)', fill: axisClr, fontSize: 9, position: 'insideTopRight' }} />
              <ReferenceLine y={0.1} stroke="var(--warn)"   strokeDasharray="4 2" strokeWidth={1} label={{ value: '아질산 경고(0.1)', fill: axisClr, fontSize: 9, position: 'insideBottomRight' }} />
              <Line type="monotone" dataKey="ammonia" stroke="var(--info)"   strokeWidth={2} dot={false} name="암모니아(ppm)" connectNulls />
              <Line type="monotone" dataKey="nitrite"  stroke="var(--danger)" strokeWidth={2} dot={false} name="아질산(ppm)"  connectNulls />
            </LineChart>
          </ResponsiveContainer>
          <div className="flex gap-4 mt-1.5 justify-end">
            <LegendDot color="var(--info)"   label="암모니아" />
            <LegendDot color="var(--danger)" label="아질산" />
          </div>
        </>
      ) : (
        <EmptyChart />
      )}
    </div>
  )
}

function PhysicalHistoryChart({ tankId, isDark }: HistoryChartProps) {
  const [bucketIdx, setBucketIdx] = useState(2)
  const bucket = BUCKET_OPTIONS[bucketIdx]

  const { data: history = [], isLoading } = useQuery({
    queryKey: ['wq-history-physical', tankId, bucketIdx],
    queryFn: () =>
      getWaterQualityHistory(tankId, { bucket_minutes: bucket.minutes, limit: bucket.limit }),
    enabled: !!tankId,
    refetchInterval: 60_000,
    select: (rows) =>
      [...rows].reverse().map((r: Record<string, unknown>) => ({
        bucket:      formatBucket(r.bucket as string, bucket.minutes),
        temperature: r.temperature_c        != null ? +(r.temperature_c        as number).toFixed(1) : null,
        do:          r.dissolved_oxygen_mgl != null ? +(r.dissolved_oxygen_mgl as number).toFixed(2) : null,
        ph:          r.ph                   != null ? +(r.ph                   as number).toFixed(2) : null,
        turbidity:   r.turbidity_ntu        != null ? +(r.turbidity_ntu        as number).toFixed(1) : null,
      })),
  })

  const grid     = isDark ? '#243044' : '#E2E8F0'
  const axisClr  = isDark ? '#4B6280' : '#94A3B8'
  const tipStyle = {
    backgroundColor: isDark ? '#0C1528' : '#FFFFFF',
    border: `1px solid ${isDark ? '#243044' : '#DDE3EE'}`,
    borderRadius: 8, fontSize: 12,
    color: isDark ? '#EEF4FF' : '#0F172A',
  }

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
          수온 · 용존산소 추이
        </h3>
        <div className="flex gap-1">
          {BUCKET_OPTIONS.map((opt, i) => (
            <button
              key={i}
              onClick={() => setBucketIdx(i)}
              className="text-xs px-2 py-0.5 rounded-md font-medium transition-all"
              style={
                bucketIdx === i
                  ? { background: 'linear-gradient(135deg,var(--teal-500),var(--blue-500))', color: '#fff' }
                  : { color: 'var(--text-muted)' }
              }
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <div className="h-48 flex items-center justify-center">
          <span className="text-xs animate-pulse" style={{ color: 'var(--text-muted)' }}>로딩 중…</span>
        </div>
      ) : history.length > 0 ? (
        <>
          <ResponsiveContainer width="100%" height={180}>
            <AreaChart data={history} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
              <defs>
                <linearGradient id="tempGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="var(--warn)" stopOpacity={0.2} />
                  <stop offset="95%" stopColor="var(--warn)" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="doGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="var(--info)" stopOpacity={0.15} />
                  <stop offset="95%" stopColor="var(--info)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke={grid} vertical={false} />
              <XAxis dataKey="bucket" tick={{ fill: axisClr, fontSize: 10 }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
              <YAxis tick={{ fill: axisClr, fontSize: 10 }} tickLine={false} axisLine={false} domain={[0, 35]} />
              <Tooltip contentStyle={tipStyle} labelStyle={{ color: axisClr }} itemStyle={{ fontSize: 11 }} />
              <ReferenceLine y={20} stroke="var(--warn)"  strokeDasharray="4 2" strokeWidth={1} label={{ value: '수온 하한(20°C)', fill: axisClr, fontSize: 9, position: 'insideTopRight' }} />
              <ReferenceLine y={28} stroke="var(--warn)"  strokeDasharray="4 2" strokeWidth={1} label={{ value: '수온 상한(28°C)', fill: axisClr, fontSize: 9, position: 'insideTopRight' }} />
              <ReferenceLine y={6}  stroke="var(--info)"  strokeDasharray="4 2" strokeWidth={1} label={{ value: 'DO 최소(6mg/L)', fill: axisClr, fontSize: 9, position: 'insideBottomRight' }} />
              <Area type="monotone" dataKey="temperature" stroke="var(--warn)" fill="url(#tempGrad)" strokeWidth={2} dot={false} name="수온(°C)"       connectNulls />
              <Area type="monotone" dataKey="do"          stroke="var(--info)" fill="url(#doGrad)"  strokeWidth={2} dot={false} name="DO(mg/L)"       connectNulls />
              <Line type="monotone" dataKey="ph"          stroke="var(--ok)"   strokeWidth={1.5}    dot={false} strokeDasharray="5 3" name="pH" connectNulls />
            </AreaChart>
          </ResponsiveContainer>
          <div className="flex gap-4 mt-1.5 justify-end">
            <LegendDot color="var(--warn)" label="수온(°C)" />
            <LegendDot color="var(--info)" label="DO(mg/L)" />
            <LegendDot color="var(--ok)"   label="pH" dashed />
          </div>
        </>
      ) : (
        <EmptyChart />
      )}
    </div>
  )
}

// ── Recent readings table ─────────────────────────────────────────────────────

function RecentReadingsTable({ readings, isDark }: { readings: WaterQualityReading[]; isDark: boolean }) {
  if (readings.length === 0) return null

  const borderClr  = isDark ? '#243044' : '#DDE3EE'
  const mutedClr   = isDark ? '#4B6280' : '#94A3B8'

  return (
    <div className="card">
      <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
        최근 측정값
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr style={{ borderBottom: `1px solid ${borderClr}` }}>
              {['시각', '수온(°C)', 'pH', 'DO(mg/L)', '암모니아(ppm)', '아질산(ppm)', '탁도(NTU)', '소스'].map(
                (h) => (
                  <th
                    key={h}
                    className="pb-2 text-left font-semibold pr-4"
                    style={{ color: mutedClr }}
                  >
                    {h}
                  </th>
                ),
              )}
            </tr>
          </thead>
          <tbody>
            {readings.map((r) => {
              const ammoniaS = getStatus('ammonia', r.ammonia_ppm)
              const nitriteS = getStatus('nitrite', r.nitrite_ppm)
              const doS      = getStatus('do', r.dissolved_oxygen_mgl)
              const tempS    = getStatus('temperature', r.temperature_c)

              return (
                <tr
                  key={r.id}
                  style={{ borderBottom: `1px solid ${borderClr}` }}
                >
                  <td className="py-2 pr-4 tabular-nums" style={{ color: mutedClr }}>
                    {new Date(r.measured_at).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                  </td>
                  <StatusCell value={r.temperature_c}        digits={1} status={tempS} />
                  <StatusCell value={r.ph}                   digits={2} />
                  <StatusCell value={r.dissolved_oxygen_mgl} digits={2} status={doS} />
                  <StatusCell value={r.ammonia_ppm}          digits={3} status={ammoniaS} />
                  <StatusCell value={r.nitrite_ppm}          digits={3} status={nitriteS} />
                  <StatusCell value={r.turbidity_ntu}        digits={1} />
                  <td className="py-2 pr-4" style={{ color: mutedClr }}>
                    {r.source === 'virtual_sensor' ? '가상' : r.source === 'manual' ? '수동' : '센서'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function StatusCell({
  value,
  digits,
  status,
}: {
  value: number | null
  digits: number
  status?: 'ok' | 'warn' | 'danger'
}) {
  const color =
    status === 'danger' ? 'var(--danger)'
    : status === 'warn'   ? 'var(--warn)'
    : 'var(--text-primary)'

  return (
    <td className="py-2 pr-4 tabular-nums font-medium" style={{ color }}>
      {value != null ? value.toFixed(digits) : '—'}
    </td>
  )
}

// ── Shared helpers ────────────────────────────────────────────────────────────

function LegendDot({ color, label, dashed = false }: { color: string; label: string; dashed?: boolean }) {
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

function EmptyChart() {
  return (
    <div className="h-48 rounded-xl flex items-center justify-center" style={{ backgroundColor: 'var(--bg-elevated)' }}>
      <span className="text-xs" style={{ color: 'var(--text-muted)' }}>데이터 없음</span>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function WaterQualityPage() {
  const isDark = useThemeStore((s) => s.isDark)
  const [selectedTankId, setSelectedTankId] = useState<string | undefined>(undefined)

  const { data: tanks = [] } = useQuery({
    queryKey: ['tanks'],
    queryFn: listTanks,
  })

  useEffect(() => {
    if (tanks.length > 0 && !selectedTankId) {
      setSelectedTankId(tanks[0].tank_id)
    }
  }, [tanks, selectedTankId])

  const { status: wsStatus, lastMessage } = useWebSocket(selectedTankId ?? 'ALL', {
    enabled: !!selectedTankId,
  })

  const { data: latestReadings = [] } = useQuery({
    queryKey: ['wq-latest-all', selectedTankId],
    queryFn: () => getLatestWaterQuality(selectedTankId, 20),
    enabled: !!selectedTankId,
    refetchInterval: 15_000,
  })

  // Live reading from WS overrides the first item
  const liveReading: WaterQualityReading | null =
    lastMessage?.type === 'water_quality' ? (lastMessage.data as WaterQualityReading) : null
  const current = liveReading ?? latestReadings[0] ?? null

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="page-title">수질 모니터링</h1>
          <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
            실시간 수질 지표 및 이력 분석
          </p>
        </div>
        <div className="flex items-center gap-2">
          {selectedTankId && (
            wsStatus === 'connected'
              ? <span className="flex items-center gap-1 text-xs" style={{ color: 'var(--ok)' }}><Wifi size={12} />실시간</span>
              : <span className="flex items-center gap-1 text-xs" style={{ color: 'var(--text-muted)' }}><WifiOff size={12} />연결 끊김</span>
          )}
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>수조:</span>
          {tanks.map((tank) => (
            <button
              key={tank.tank_id}
              onClick={() => setSelectedTankId(tank.tank_id)}
              className="text-xs px-2.5 py-1 rounded-lg font-medium transition-all flex items-center gap-1.5"
              style={
                selectedTankId === tank.tank_id
                  ? { background: 'linear-gradient(135deg, var(--teal-500), var(--blue-500))', color: '#fff' }
                  : { backgroundColor: 'var(--bg-surface)', border: '1px solid var(--bg-border)', color: 'var(--text-secondary)' }
              }
            >
              <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: tank.status === 'online' ? 'var(--ok)' : 'var(--text-muted)' }} />
              {tank.name}
            </button>
          ))}
        </div>
      </div>

      {!selectedTankId ? (
        <div className="card flex items-center justify-center h-40">
          <span className="text-sm" style={{ color: 'var(--text-muted)' }}>수조를 선택하세요</span>
        </div>
      ) : (
        <>
          {/* Current readings — 6 big metric cards */}
          <div className="flex items-center gap-2 mb-1">
            <Droplets size={14} style={{ color: 'var(--info)' }} />
            <span className="section-title" style={{ marginBottom: 0 }}>현재 측정값</span>
            {current && (
              <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                {new Date(current.measured_at).toLocaleString('ko-KR')}
              </span>
            )}
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-6 gap-3">
            <BigMetric label="수온"    value={current?.temperature_c}        unit="°C"   digits={1} metric="temperature" safeRange="20~28°C" />
            <BigMetric label="pH"      value={current?.ph}                   unit=""     digits={2} metric="ph"          safeRange="7.0~8.5" />
            <BigMetric label="용존산소" value={current?.dissolved_oxygen_mgl} unit="mg/L" digits={2} metric="do"          safeRange="≥ 6" />
            <BigMetric label="암모니아" value={current?.ammonia_ppm}          unit="ppm"  digits={3} metric="ammonia"     safeRange="< 0.5" />
            <BigMetric label="아질산"   value={current?.nitrite_ppm}          unit="ppm"  digits={3} metric="nitrite"     safeRange="< 0.1" />
            <BigMetric label="탁도"     value={current?.turbidity_ntu}        unit="NTU"  digits={1} metric="turbidity"   safeRange="< 10" />
          </div>

          {/* Charts */}
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
            <ChemicalHistoryChart tankId={selectedTankId} isDark={isDark} />
            <PhysicalHistoryChart tankId={selectedTankId} isDark={isDark} />
          </div>

          {/* Recent readings table */}
          <RecentReadingsTable readings={latestReadings} isDark={isDark} />
        </>
      )}
    </div>
  )
}
