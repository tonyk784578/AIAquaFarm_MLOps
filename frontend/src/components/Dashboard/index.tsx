import { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Activity, AlertTriangle, Droplets, Fish, X } from 'lucide-react'
import { getDashboardSummary, listTanks } from '@/services/api'
import { useWebSocket } from '@/hooks/useWebSocket'
import type { Alert, DashboardSummary, Tank, WSMessage } from '@/types'
import AlertPanel from './AlertPanel'
import FeedingPanel from './FeedingPanel'
import FishGrowthPanel from './FishGrowthPanel'
import SystemFlowPanel from './SystemFlowPanel'
import WaterQualityPanel from './WaterQualityPanel'

// ── Alert Toast ───────────────────────────────────────────────────────────────

interface AlertToastProps {
  alert: Alert
  onDismiss: () => void
}

function AlertToast({ alert, onDismiss }: AlertToastProps) {
  const isCritical = alert.severity === 'critical'
  useEffect(() => {
    const t = setTimeout(onDismiss, 8_000)
    return () => clearTimeout(t)
  }, [onDismiss])

  return (
    <div
      className="fixed bottom-6 right-6 z-50 flex items-start gap-3 max-w-sm w-full rounded-2xl px-4 py-3 animate-slide-in"
      style={{
        backgroundColor: 'var(--bg-surface)',
        border: `1px solid ${isCritical ? 'rgba(220,38,38,0.4)' : 'rgba(217,119,6,0.4)'}`,
        boxShadow: 'var(--shadow-lg)',
      }}
    >
      <AlertTriangle
        size={15}
        className="mt-0.5 shrink-0"
        style={{ color: isCritical ? 'var(--danger)' : 'var(--warn)' }}
      />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold truncate" style={{ color: 'var(--text-primary)' }}>
          {alert.title}
        </p>
        <p className="text-xs mt-0.5 line-clamp-2" style={{ color: 'var(--text-secondary)' }}>
          {alert.message}
        </p>
        <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>{alert.tank_id}</p>
      </div>
      <button
        onClick={onDismiss}
        className="shrink-0 p-0.5 rounded transition-opacity opacity-60 hover:opacity-100"
        style={{ color: 'var(--text-muted)' }}
      >
        <X size={14} />
      </button>
    </div>
  )
}

// ── KPI Summary Row ───────────────────────────────────────────────────────────

interface KpiCardProps {
  label: string
  value: string
  subtext: string
  valueColor: string
  Icon: React.ElementType
}

function KpiCard({ label, value, subtext, valueColor, Icon }: KpiCardProps) {
  return (
    <div
      className="rounded-2xl px-4 py-3 flex items-center gap-3"
      style={{
        backgroundColor: 'var(--bg-surface)',
        border: '1px solid var(--bg-border)',
        boxShadow: 'var(--shadow-sm)',
      }}
    >
      <div
        className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
        style={{ backgroundColor: `color-mix(in srgb, ${valueColor} 12%, transparent)` }}
      >
        <Icon size={18} style={{ color: valueColor }} />
      </div>
      <div className="min-w-0">
        <p className="text-xs font-medium" style={{ color: 'var(--text-muted)' }}>{label}</p>
        <p className="text-xl font-bold leading-tight tabular-nums" style={{ color: valueColor }}>
          {value}
        </p>
        <p className="text-xs mt-0.5" style={{ color: 'var(--text-secondary)' }}>{subtext}</p>
      </div>
    </div>
  )
}

function SummaryKpiRow({
  summary,
  tanks,
}: {
  summary: DashboardSummary | undefined
  tanks: Tank[]
}) {
  const onlineTanks = tanks.filter((t) => t.status === 'online').length
  const alertCount = summary?.active_alert_count ?? 0
  const biomass = summary?.fish_growth?.biomass_kg
  const fishCount = summary?.fish_growth?.fish_count
  const temp = summary?.water_quality?.temperature_c
  const doVal = summary?.water_quality?.dissolved_oxygen_mgl

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      <KpiCard
        label="수조 현황"
        value={tanks.length > 0 ? `${onlineTanks} / ${tanks.length}` : '—'}
        subtext="운영 중"
        valueColor="var(--teal-500)"
        Icon={Activity}
      />
      <KpiCard
        label="활성 알림"
        value={String(alertCount)}
        subtext={alertCount > 0 ? `${alertCount}건 주의 필요` : '이상 없음'}
        valueColor={alertCount > 0 ? 'var(--danger)' : 'var(--ok)'}
        Icon={AlertTriangle}
      />
      <KpiCard
        label="총 바이오매스"
        value={biomass != null ? `${biomass.toFixed(1)} kg` : '—'}
        subtext={fishCount != null ? `${fishCount.toLocaleString()}마리` : '데이터 없음'}
        valueColor="var(--info)"
        Icon={Fish}
      />
      <KpiCard
        label="현재 수온 / DO"
        value={temp != null ? `${temp.toFixed(1)}°C` : '—'}
        subtext={doVal != null ? `DO ${doVal.toFixed(1)} mg/L` : '데이터 없음'}
        valueColor="var(--warn)"
        Icon={Droplets}
      />
    </div>
  )
}

// ── Dashboard ─────────────────────────────────────────────────────────────────

export default function Dashboard() {
  const qc = useQueryClient()
  const [selectedTankId, setSelectedTankId] = useState<string | undefined>(undefined)
  const [toast, setToast] = useState<Alert | null>(null)
  const dismissRef = useRef<() => void>(() => setToast(null))
  dismissRef.current = () => setToast(null)

  const { data: summary, isLoading } = useQuery({
    queryKey: ['dashboard-summary'],
    queryFn: getDashboardSummary,
    refetchInterval: 10_000,
  })

  const { data: tanks = [] } = useQuery({
    queryKey: ['tanks'],
    queryFn: listTanks,
  })

  useEffect(() => {
    if (tanks.length > 0 && !selectedTankId) {
      setSelectedTankId(tanks[0].tank_id)
    }
  }, [tanks, selectedTankId])

  useWebSocket(selectedTankId ?? 'ALL', {
    enabled: !!selectedTankId,
    onMessage: (msg: WSMessage) => {
      if (msg.type !== 'alert') return
      const alertData = msg.data as Alert
      setToast(alertData)
      qc.invalidateQueries({ queryKey: ['dashboard-summary'] })
      qc.invalidateQueries({ queryKey: ['alerts'] })
      qc.invalidateQueries({ queryKey: ['alerts-header'] })
    },
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-sm animate-pulse" style={{ color: 'var(--text-muted)' }}>
          데이터 로딩 중…
        </div>
      </div>
    )
  }

  return (
    <>
      <div className="space-y-5">
        {/* Page header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="page-title">운영 대시보드</h1>
            <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
              실시간 양식장 모니터링
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>수조:</span>
            {tanks.map((tank) => (
              <button
                key={tank.tank_id}
                onClick={() => setSelectedTankId(tank.tank_id)}
                className="text-xs px-2.5 py-1 rounded-lg font-medium transition-all flex items-center gap-1.5"
                style={
                  selectedTankId === tank.tank_id
                    ? {
                        background: 'linear-gradient(135deg, var(--teal-500), var(--blue-500))',
                        color: '#fff',
                      }
                    : {
                        backgroundColor: 'var(--bg-surface)',
                        border: '1px solid var(--bg-border)',
                        color: 'var(--text-secondary)',
                      }
                }
              >
                <span
                  className="w-1.5 h-1.5 rounded-full shrink-0"
                  style={{
                    backgroundColor:
                      tank.status === 'online'
                        ? 'var(--ok)'
                        : tank.status === 'warning'
                        ? 'var(--warn)'
                        : 'var(--text-muted)',
                  }}
                />
                {tank.name}
              </button>
            ))}
          </div>
        </div>

        {/* System data-flow pipeline */}
        <SystemFlowPanel activeAlertCount={summary?.active_alert_count ?? 0} />

        {/* KPI summary row */}
        <SummaryKpiRow summary={summary} tanks={tanks} />

        {/* Alert banner */}
        {(summary?.active_alert_count ?? 0) > 0 && (
          <Link
            to="/alerts"
            className="flex items-center gap-2.5 rounded-xl px-4 py-2.5 transition-colors"
            style={{
              backgroundColor: 'rgba(220,38,38,0.07)',
              border: '1px solid rgba(220,38,38,0.2)',
            }}
            onMouseEnter={(e) => {
              ;(e.currentTarget as HTMLElement).style.backgroundColor = 'rgba(220,38,38,0.11)'
            }}
            onMouseLeave={(e) => {
              ;(e.currentTarget as HTMLElement).style.backgroundColor = 'rgba(220,38,38,0.07)'
            }}
          >
            <AlertTriangle size={14} style={{ color: 'var(--danger)' }} />
            <span className="text-sm font-semibold" style={{ color: 'var(--danger)' }}>
              활성 알림 {summary?.active_alert_count}건 — 클릭하여 확인
            </span>
          </Link>
        )}

        {/* Top row: WaterQuality (2/3) + Alerts (1/3) */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
          <div className="lg:col-span-2">
            <WaterQualityPanel data={summary?.water_quality ?? null} tankId={selectedTankId} />
          </div>
          <AlertPanel alerts={summary?.recent_alerts ?? []} />
        </div>

        {/* Bottom row: FishGrowth + Feeding */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <FishGrowthPanel data={summary?.fish_growth ?? null} tankId={selectedTankId} />
          <FeedingPanel tankId={selectedTankId} />
        </div>
      </div>

      {toast && <AlertToast alert={toast} onDismiss={dismissRef.current} />}
    </>
  )
}
