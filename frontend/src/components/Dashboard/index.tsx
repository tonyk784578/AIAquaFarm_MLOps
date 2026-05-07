// Main dashboard page — grid layout of all monitoring panels.
// Tank selector filters panels; WebSocket delivers real-time WQ updates.

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getDashboardSummary, listTanks } from '@/services/api'
import AlertPanel from './AlertPanel'
import FeedingPanel from './FeedingPanel'
import FishGrowthPanel from './FishGrowthPanel'
import WaterQualityPanel from './WaterQualityPanel'

export default function Dashboard() {
  const [selectedTankId, setSelectedTankId] = useState<string | undefined>(undefined)

  const { data: summary, isLoading } = useQuery({
    queryKey: ['dashboard-summary'],
    queryFn: getDashboardSummary,
    refetchInterval: 10_000,
  })

  const { data: tanks = [] } = useQuery({
    queryKey: ['tanks'],
    queryFn: listTanks,
    onSuccess: (data) => {
      // Auto-select first tank
      if (data.length > 0 && !selectedTankId) {
        setSelectedTankId(data[0].tank_id)
      }
    },
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-slate-400 animate-pulse">데이터 로딩 중...</div>
      </div>
    )
  }

  return (
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
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-2 flex items-center gap-2">
          <span className="text-red-400 text-sm font-medium">
            ⚠ 활성 알림 {summary?.active_alert_count}건
          </span>
        </div>
      )}

      {/* 2-column grid for main panels */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <WaterQualityPanel
          data={summary?.water_quality ?? null}
          tankId={selectedTankId}
        />
        <FishGrowthPanel data={summary?.fish_growth ?? null} />
        <FeedingPanel />
        <AlertPanel alerts={summary?.recent_alerts ?? []} />
      </div>
    </div>
  )
}
