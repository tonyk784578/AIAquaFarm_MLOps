import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { AlertTriangle, Pause, Play, Sliders, Wind, Waves, Droplets } from 'lucide-react'
import {
  controlPump,
  increaseAeration,
  listTanks,
  stopFeeding,
  triggerFeeding,
  triggerWaterExchange,
} from '@/services/api'

// ── Confirmation dialog ──────────────────────────────────────────────────────

interface ConfirmDialog {
  title: string
  description: string
  onConfirm: () => void
}

function ConfirmModal({ dialog, onClose }: { dialog: ConfirmDialog; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-slate-800 border border-slate-700 rounded-xl p-6 w-full max-w-sm shadow-xl">
        <div className="flex items-center gap-2 mb-3">
          <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0" />
          <h3 className="text-sm font-semibold text-slate-100">{dialog.title}</h3>
        </div>
        <p className="text-sm text-slate-400 mb-5">{dialog.description}</p>
        <div className="flex gap-3 justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-slate-400 hover:text-slate-200 transition-colors"
          >
            취소
          </button>
          <button
            onClick={() => { dialog.onConfirm(); onClose() }}
            className="px-4 py-2 text-sm bg-sky-600 hover:bg-sky-500 text-white rounded-lg transition-colors font-medium"
          >
            확인
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Shared command status badge ───────────────────────────────────────────────

function StatusBadge({ jobId, error }: { jobId?: string | null; error?: boolean }) {
  if (error) return <p className="text-xs text-red-400 mt-2">명령 전송 실패</p>
  if (jobId)
    return (
      <p className="text-xs text-emerald-400 mt-2">
        명령 전송 완료 · ID:{' '}
        <span className="font-mono text-sky-400">{jobId}</span>
      </p>
    )
  return null
}

export default function ControlPanel() {
  const [selectedTank, setSelectedTank] = useState('')
  const [feedAmount, setFeedAmount] = useState(1.0)
  const [aerationBoost, setAerationBoost] = useState(30)
  const [exchangePct, setExchangePct] = useState(10)
  const [confirm, setConfirm] = useState<ConfirmDialog | null>(null)

  const { data: tanks = [] } = useQuery({ queryKey: ['tanks'], queryFn: listTanks })

  const ask = (dialog: ConfirmDialog) => setConfirm(dialog)

  // ── Mutations ─────────────────────────────────────────────────────────────

  const feedMut = useMutation({
    mutationFn: () => triggerFeeding(selectedTank, feedAmount),
  })
  const stopMut = useMutation({
    mutationFn: () => stopFeeding(selectedTank),
  })
  const pumpStartMut = useMutation({
    mutationFn: () => controlPump(selectedTank, 'start'),
  })
  const pumpStopMut = useMutation({
    mutationFn: () => controlPump(selectedTank, 'stop'),
  })
  const aerationMut = useMutation({
    mutationFn: () => increaseAeration(selectedTank, aerationBoost),
  })
  const exchangeMut = useMutation({
    mutationFn: () => triggerWaterExchange(selectedTank, exchangePct),
  })

  const noTank = !selectedTank

  return (
    <div className="max-w-3xl space-y-6">
      {confirm && (
        <ConfirmModal dialog={confirm} onClose={() => setConfirm(null)} />
      )}

      <div className="flex items-center gap-2">
        <Sliders className="w-5 h-5 text-sky-400" />
        <h1 className="text-lg font-semibold text-slate-100">장비 제어</h1>
      </div>

      {/* Tank selector */}
      <div className="bg-slate-800 rounded-xl border border-slate-700 p-4">
        <label className="text-xs text-slate-400 font-medium block mb-2">수조 선택</label>
        <select
          value={selectedTank}
          onChange={(e) => setSelectedTank(e.target.value)}
          className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-sky-500"
        >
          <option value="">수조를 선택하세요</option>
          {tanks.map((t) => (
            <option key={t.tank_id} value={t.tank_id}>
              {t.name} ({t.tank_id})
            </option>
          ))}
        </select>
        {noTank && (
          <p className="text-xs text-slate-500 mt-1.5">수조를 선택해야 제어 명령을 전송할 수 있습니다.</p>
        )}
      </div>

      {/* ── 급이 제어 ─────────────────────────────────────────────── */}
      <section className="bg-slate-800 rounded-xl border border-slate-700 p-5 space-y-4">
        <div className="flex items-center gap-2">
          <Play className="w-4 h-4 text-amber-400" />
          <h2 className="text-sm font-semibold text-slate-200">급이 제어</h2>
        </div>

        <div>
          <label className="text-xs text-slate-400">급이량: {feedAmount.toFixed(1)} kg</label>
          <input
            type="range" min={0.1} max={20} step={0.1}
            value={feedAmount}
            onChange={(e) => setFeedAmount(Number(e.target.value))}
            className="w-full mt-1 accent-amber-400"
          />
          <div className="flex justify-between text-xs text-slate-500 mt-0.5">
            <span>0.1 kg</span><span>20 kg</span>
          </div>
        </div>

        <div className="flex gap-3">
          <button
            disabled={noTank || feedMut.isPending}
            onClick={() =>
              ask({
                title: '급이 시작',
                description: `${selectedTank}에 ${feedAmount.toFixed(1)} kg 급이를 시작하시겠습니까?`,
                onConfirm: () => feedMut.mutate(),
              })
            }
            className="flex items-center gap-2 px-4 py-2 bg-amber-500 hover:bg-amber-400 disabled:opacity-40 text-slate-900 font-medium text-sm rounded-lg transition-colors"
          >
            <Play className="w-3.5 h-3.5" />
            급이 시작
          </button>
          <button
            disabled={noTank || stopMut.isPending}
            onClick={() =>
              ask({
                title: '긴급 정지',
                description: `${selectedTank} 급이기를 즉시 정지합니다. 계속하시겠습니까?`,
                onConfirm: () => stopMut.mutate(),
              })
            }
            className="flex items-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-500 disabled:opacity-40 text-white font-medium text-sm rounded-lg transition-colors"
          >
            <Pause className="w-3.5 h-3.5" />
            긴급 정지
          </button>
        </div>
        <StatusBadge
          jobId={(feedMut.data ?? stopMut.data)?.job_id}
          error={feedMut.isError || stopMut.isError}
        />
      </section>

      {/* ── 순환펌프 제어 ─────────────────────────────────────────── */}
      <section className="bg-slate-800 rounded-xl border border-slate-700 p-5 space-y-4">
        <div className="flex items-center gap-2">
          <Waves className="w-4 h-4 text-sky-400" />
          <h2 className="text-sm font-semibold text-slate-200">순환펌프 제어</h2>
        </div>
        <div className="flex gap-3">
          <button
            disabled={noTank || pumpStartMut.isPending}
            onClick={() =>
              ask({
                title: '펌프 시작',
                description: `${selectedTank} 순환펌프를 가동합니다.`,
                onConfirm: () => pumpStartMut.mutate(),
              })
            }
            className="flex items-center gap-2 px-4 py-2 bg-sky-600 hover:bg-sky-500 disabled:opacity-40 text-white font-medium text-sm rounded-lg transition-colors"
          >
            <Play className="w-3.5 h-3.5" />
            펌프 시작
          </button>
          <button
            disabled={noTank || pumpStopMut.isPending}
            onClick={() =>
              ask({
                title: '펌프 정지',
                description: `${selectedTank} 순환펌프를 정지합니다.`,
                onConfirm: () => pumpStopMut.mutate(),
              })
            }
            className="flex items-center gap-2 px-4 py-2 bg-slate-600 hover:bg-slate-500 disabled:opacity-40 text-white font-medium text-sm rounded-lg transition-colors"
          >
            <Pause className="w-3.5 h-3.5" />
            펌프 정지
          </button>
        </div>
        <StatusBadge
          jobId={(pumpStartMut.data ?? pumpStopMut.data)?.job_id}
          error={pumpStartMut.isError || pumpStopMut.isError}
        />
      </section>

      {/* ── 폭기 제어 ─────────────────────────────────────────────── */}
      <section className="bg-slate-800 rounded-xl border border-slate-700 p-5 space-y-4">
        <div className="flex items-center gap-2">
          <Wind className="w-4 h-4 text-emerald-400" />
          <h2 className="text-sm font-semibold text-slate-200">폭기 (Aeration) 제어</h2>
        </div>
        <div>
          <label className="text-xs text-slate-400">부스트: {aerationBoost}%</label>
          <input
            type="range" min={10} max={200} step={10}
            value={aerationBoost}
            onChange={(e) => setAerationBoost(Number(e.target.value))}
            className="w-full mt-1 accent-emerald-400"
          />
          <div className="flex justify-between text-xs text-slate-500 mt-0.5">
            <span>10%</span><span>200%</span>
          </div>
        </div>
        <button
          disabled={noTank || aerationMut.isPending}
          onClick={() =>
            ask({
              title: '폭기 강화',
              description: `${selectedTank} 폭기를 ${aerationBoost}% 증가시킵니다.`,
              onConfirm: () => aerationMut.mutate(),
            })
          }
          className="flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white font-medium text-sm rounded-lg transition-colors"
        >
          <Wind className="w-3.5 h-3.5" />
          폭기 강화
        </button>
        <StatusBadge jobId={aerationMut.data?.job_id} error={aerationMut.isError} />
      </section>

      {/* ── 환수 제어 ─────────────────────────────────────────────── */}
      <section className="bg-slate-800 rounded-xl border border-slate-700 p-5 space-y-4">
        <div className="flex items-center gap-2">
          <Droplets className="w-4 h-4 text-blue-400" />
          <h2 className="text-sm font-semibold text-slate-200">부분 환수</h2>
        </div>
        <div>
          <label className="text-xs text-slate-400">환수 비율: {exchangePct}%</label>
          <input
            type="range" min={5} max={50} step={5}
            value={exchangePct}
            onChange={(e) => setExchangePct(Number(e.target.value))}
            className="w-full mt-1 accent-blue-400"
          />
          <div className="flex justify-between text-xs text-slate-500 mt-0.5">
            <span>5%</span><span>50%</span>
          </div>
        </div>
        <button
          disabled={noTank || exchangeMut.isPending}
          onClick={() =>
            ask({
              title: '부분 환수',
              description: `${selectedTank} 수조 용량의 ${exchangePct}%를 환수합니다. 계속하시겠습니까?`,
              onConfirm: () => exchangeMut.mutate(),
            })
          }
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white font-medium text-sm rounded-lg transition-colors"
        >
          <Droplets className="w-3.5 h-3.5" />
          환수 실행
        </button>
        <StatusBadge jobId={exchangeMut.data?.job_id} error={exchangeMut.isError} />
      </section>
    </div>
  )
}
