// Main dashboard page — grid layout of all monitoring panels.
// Tank selector filters panels; WebSocket delivers real-time WQ + alert updates.

import { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { AlertTriangle, X } from 'lucide-react'
import { getDashboardSummary, listTanks } from '@/services/api'
import { useWebSocket } from '@/hooks/useWebSocket'
import type { Alert, WSMessage } from '@/types'
import AlertPanel from './AlertPanel'
import FeedingPanel from './FeedingPanel'
import FishGrowthPanel from './FishGrowthPanel'
import WaterQualityPanel from './WaterQualityPanel'

// ── Real-time alert toast ──────────────────────────────────────────────────────

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
      className={`fixed bottom-6 right-6 z-50 flex items-start gap-3 max-w-sm w-full
        rounded-xl px-4 py-3 shadow-lg ring-1 animate-slide-in
        ${isCritical
          ? 'bg-red-950 ring-red-500/50 text-red-200'
          : 'bg-yellow-950 ring-yellow-500/50 text-yellow-200'}`}
    >
      <AlertTriangle className={`w-4 h-4 mt-0.5 shrink-0 ${isCritical ? 'text-red-400' : 'text-yellow-400'}`} />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">{alert.title}</p>
        <p className="text-xs opacity-75 mt-0.5 line-clamp-2">{alert.message}</p>
        <p className="text-xs opacity-50 mt-1">{alert.tank_id}</p>
      </div>
      <button onClick={onDismiss} className="shrink-0 opacity-60 hover:opacity-100 transition-opacity">
        <X className="w-4 h-4" />
      </button>
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
    select: (data) => {
      if (data.length > 0 && !selectedTankId) {
        setTimeout(() => setSelectedTankId(data[0].tank_id), 0)
      }
      return data
    },
  })

  // Subscribe to the tank's WebSocket channel to receive real-time alert pushes.
  // WaterQualityPanel has its own WS connection for sensor data; this one is
  // dedicated to alert-type messages so the Dashboard can react immediately.
  useWebSocket(selectedTankId ?? 'ALL', {
    enabled: !!selectedTankId,
    onMessage: (msg: WSMessage) => {
      if (msg.type !== 'alert') return
      const alertData = msg.data as Alert
      setToast(alertData)
      // Invalidate so AlertPanel and header badge refresh without waiting for the poll
      qc.invalidateQueries({ queryKey: ['dashboard-summary'] })
      qc.invalidateQueries({ queryKey: ['alerts'] })
      qc.invalidateQueries({ queryKey: ['alerts-header'] })
    },
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-slate-400 animate-pulse">데이터 로딩 중…</div>
      </div>
    )
  }

  return (
    <>
      <div className="space-y-6">
        {/* Page header with tank selector */}
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-semibold text-slate-100">운영 대시보드</h1>
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-400">수조:</span>
            {tanks.map((tank) => (
              <button
                key={tank.tank_id}
                onClick={() => setSelectedTankId(tank.tank_id)}
                className={`text-xs px-2 py-0.5 rounded transition-colors ${
                  selectedTankId === tank.tank_id
                    ? 'bg-sky-500/30 text-sky-300 ring-1 ring-sky-500/50'
                    : tank.status === 'online'
                    ? 'bg-green-500/20 text-green-400 hover:bg-green-500/30'
                    : 'bg-slate-700 text-slate-400 hover:bg-slate-600'
                }`}
              >
                {tank.name}
              </button>
            ))}
          </div>
        </div>

        {/* Alert summary bar */}
        {(summary?.active_alert_count ?? 0) > 0 && (
          <Link
            to="/alerts"
            className="flex items-center gap-2 bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-2 hover:bg-red-500/15 transition-colors"
          >
            <AlertTriangle className="w-4 h-4 text-red-400" />
            <span className="text-red-400 text-sm font-medium">
              활성 알림 {summary?.active_alert_count}건 — 클릭하여 확인
            </span>
          </Link>
        )}

        {/* 2-column grid for main panels */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <WaterQualityPanel
            data={summary?.water_quality ?? null}
            tankId={selectedTankId}
          />
          <FishGrowthPanel
            data={summary?.fish_growth ?? null}
            tankId={selectedTankId}
          />
          <FeedingPanel tankId={selectedTankId} />
          <AlertPanel alerts={summary?.recent_alerts ?? []} />
        </div>
      </div>

      {/* Real-time alert toast — rendered outside the scroll container */}
      {toast && <AlertToast alert={toast} onDismiss={dismissRef.current} />}
    </>
  )
}
