// Feeding status panel — shows last feeding event and AI recommendation.
// TODO (Phase 2): Add feeding activity score bar chart.
// TODO (Phase 3): Wire up one-click feeding trigger button.

import { useQuery } from '@tanstack/react-query'
import { Utensils } from 'lucide-react'
import { getLatestWaterQuality } from '@/services/api'

export default function FeedingPanel() {
  // TODO (Phase 2): Add /monitoring/feeding/latest endpoint and query it here
  const isLoading = false

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Utensils className="w-4 h-4 text-amber-400" />
          <h2 className="font-medium text-slate-200">먹이 관리</h2>
        </div>
      </div>

      {/* Feeding activity score */}
      <div className="space-y-3">
        <div>
          <div className="flex items-center justify-between mb-1">
            <span className="metric-label">먹이활성도</span>
            <span className="text-xs text-slate-400">— %</span>
          </div>
          <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-amber-400 rounded-full transition-all duration-500"
              style={{ width: '0%' }}
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <span className="metric-label">최근 급이량</span>
            <span className="metric-value">—<span className="text-sm font-normal text-slate-400 ml-1">kg</span></span>
          </div>
          <div>
            <span className="metric-label">AI 권장 급이량</span>
            <span className="metric-value text-amber-400">—<span className="text-sm font-normal text-slate-400 ml-1">kg</span></span>
          </div>
        </div>
      </div>

      {/* TODO (Phase 2): Real feeding history chart */}
      <div className="mt-4 h-24 bg-slate-700/50 rounded-lg flex items-center justify-center">
        <span className="text-slate-500 text-xs">먹이효율 차트 — Phase 2 구현 예정</span>
      </div>
    </div>
  )
}
