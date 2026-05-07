// Equipment control panel — manual override for feeding and pump control.
// TODO (Phase 3): Add confirmation dialog before sending commands.
// TODO (Phase 3): Add real-time command status tracking via WebSocket.

import { useMutation, useQuery } from '@tanstack/react-query'
import { Pause, Play, Sliders } from 'lucide-react'
import { useState } from 'react'
import { listTanks, stopFeeding, triggerFeeding } from '@/services/api'

export default function ControlPanel() {
  const [selectedTank, setSelectedTank] = useState<string>('')
  const [feedAmount, setFeedAmount] = useState<number>(1.0)
  const [lastJobId, setLastJobId] = useState<string | null>(null)

  const { data: tanks = [] } = useQuery({
    queryKey: ['tanks'],
    queryFn: listTanks,
  })

  const feedMutation = useMutation({
    mutationFn: () => triggerFeeding(selectedTank, feedAmount),
    onSuccess: (data) => setLastJobId(data.job_id),
  })

  const stopMutation = useMutation({
    mutationFn: () => stopFeeding(selectedTank),
    onSuccess: (data) => setLastJobId(data.job_id),
  })

  return (
    <div className="max-w-2xl space-y-6">
      <div className="flex items-center gap-2 mb-2">
        <Sliders className="w-5 h-5 text-sky-400" />
        <h1 className="text-xl font-semibold">장비 제어</h1>
      </div>

      <div className="card space-y-4">
        <h2 className="font-medium text-slate-200">급이 제어</h2>

        {/* Tank selector */}
        <div>
          <label className="block text-xs text-slate-400 mb-1">수조 선택</label>
          <select
            value={selectedTank}
            onChange={(e) => setSelectedTank(e.target.value)}
            className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-sky-500"
          >
            <option value="">수조를 선택하세요</option>
            {tanks.map((tank) => (
              <option key={tank.tank_id} value={tank.tank_id}>
                {tank.name} ({tank.tank_id})
              </option>
            ))}
          </select>
        </div>

        {/* Feed amount */}
        <div>
          <label className="block text-xs text-slate-400 mb-1">
            급이량: {feedAmount.toFixed(1)} kg
          </label>
          <input
            type="range"
            min={0.1}
            max={20}
            step={0.1}
            value={feedAmount}
            onChange={(e) => setFeedAmount(Number(e.target.value))}
            className="w-full accent-sky-500"
          />
          <div className="flex justify-between text-xs text-slate-500 mt-0.5">
            <span>0.1 kg</span>
            <span>20 kg</span>
          </div>
        </div>

        {/* Action buttons */}
        <div className="flex gap-3">
          <button
            onClick={() => feedMutation.mutate()}
            disabled={!selectedTank || feedMutation.isPending}
            className="flex items-center gap-2 px-4 py-2 bg-sky-600 hover:bg-sky-500 disabled:opacity-40 disabled:cursor-not-allowed rounded-lg text-sm font-medium transition-colors"
          >
            <Play className="w-4 h-4" />
            급이 시작
          </button>
          <button
            onClick={() => stopMutation.mutate()}
            disabled={!selectedTank || stopMutation.isPending}
            className="flex items-center gap-2 px-4 py-2 bg-red-700 hover:bg-red-600 disabled:opacity-40 disabled:cursor-not-allowed rounded-lg text-sm font-medium transition-colors"
          >
            <Pause className="w-4 h-4" />
            긴급 정지
          </button>
        </div>

        {lastJobId && (
          <p className="text-xs text-slate-400">
            마지막 명령 ID: <span className="font-mono text-sky-400">{lastJobId}</span>
          </p>
        )}
      </div>

      {/* TODO (Phase 3): Add pump control section */}
      <div className="card opacity-50">
        <h2 className="font-medium text-slate-400">순환펌프 제어 — Phase 3 구현 예정</h2>
      </div>
    </div>
  )
}
