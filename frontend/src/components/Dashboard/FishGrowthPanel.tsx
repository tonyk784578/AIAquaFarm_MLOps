// Fish growth monitoring panel — displays vision AI outputs.
// TODO (Phase 2): Add growth trend chart (weight/length over time).
// TODO (Phase 2): Add camera feed thumbnail from edge device.

import { Fish } from 'lucide-react'
import type { FishGrowthRecord } from '@/types'

interface Props {
  data: FishGrowthRecord | null
}

export default function FishGrowthPanel({ data }: Props) {
  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Fish className="w-4 h-4 text-emerald-400" />
          <h2 className="font-medium text-slate-200">성장 관리</h2>
        </div>
        {data?.model_version && (
          <span className="text-xs text-slate-500">v{data.model_version}</span>
        )}
      </div>

      {data ? (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          <div>
            <span className="metric-label">어류 수</span>
            <span className="metric-value">{data.fish_count ?? '—'}</span>
          </div>
          <div>
            <span className="metric-label">평균 체장</span>
            <span className="metric-value">
              {data.avg_length_cm?.toFixed(1) ?? '—'}
              <span className="text-sm font-normal text-slate-400 ml-1">cm</span>
            </span>
          </div>
          <div>
            <span className="metric-label">평균 체중</span>
            <span className="metric-value">
              {data.avg_weight_g?.toFixed(0) ?? '—'}
              <span className="text-sm font-normal text-slate-400 ml-1">g</span>
            </span>
          </div>
          <div>
            <span className="metric-label">총 바이오매스</span>
            <span className="metric-value">
              {data.biomass_kg?.toFixed(1) ?? '—'}
              <span className="text-sm font-normal text-slate-400 ml-1">kg</span>
            </span>
          </div>
          <div>
            <span className="metric-label">일일 성장률</span>
            <span className={`metric-value ${(data.daily_growth_rate_pct ?? 0) > 0 ? 'text-emerald-400' : 'text-slate-100'}`}>
              {data.daily_growth_rate_pct != null
                ? `+${data.daily_growth_rate_pct.toFixed(2)}%`
                : '—'}
            </span>
          </div>
          <div>
            <span className="metric-label">FCR</span>
            <span className="metric-value">
              {data.feed_conversion_ratio?.toFixed(2) ?? '—'}
            </span>
          </div>
        </div>
      ) : (
        <p className="text-slate-500 text-sm">데이터 없음</p>
      )}

      {/* TODO (Phase 2): Camera thumbnail */}
      <div className="mt-4 h-24 bg-slate-700/50 rounded-lg flex items-center justify-center">
        <span className="text-slate-500 text-xs">카메라 피드 — Phase 2 구현 예정</span>
      </div>
    </div>
  )
}
