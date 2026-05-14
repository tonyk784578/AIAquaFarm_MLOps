import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { AlertTriangle, Droplets, Pause, Play, Sliders, Wind, Waves } from 'lucide-react'
import {
  controlPump, increaseAeration, listTanks,
  stopFeeding, triggerFeeding, triggerWaterExchange,
} from '@/services/api'

interface ConfirmDialog {
  title: string
  description: string
  onConfirm: () => void
}

function ConfirmModal({ dialog, onClose }: { dialog: ConfirmDialog; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ backgroundColor: 'rgba(0,0,0,0.5)' }}>
      <div
        className="w-full max-w-sm rounded-2xl p-6 animate-fade-in"
        style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--bg-border)', boxShadow: 'var(--shadow-lg)' }}
      >
        <div className="flex items-center gap-2 mb-3">
          <AlertTriangle size={16} style={{ color: 'var(--warn)' }} className="shrink-0" />
          <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{dialog.title}</h3>
        </div>
        <p className="text-sm mb-5" style={{ color: 'var(--text-secondary)' }}>{dialog.description}</p>
        <div className="flex gap-3 justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm rounded-lg transition-colors"
            style={{ color: 'var(--text-secondary)' }}
          >
            취소
          </button>
          <button
            onClick={() => { dialog.onConfirm(); onClose() }}
            className="btn-primary"
          >
            확인
          </button>
        </div>
      </div>
    </div>
  )
}

function StatusBadge({ jobId, error }: { jobId?: string | null; error?: boolean }) {
  if (error) return (
    <p className="text-xs mt-2" style={{ color: 'var(--danger)' }}>명령 전송 실패</p>
  )
  if (jobId) return (
    <p className="text-xs mt-2" style={{ color: 'var(--ok)' }}>
      명령 전송 완료 · ID: <span className="font-mono" style={{ color: 'var(--info)' }}>{jobId}</span>
    </p>
  )
  return null
}

function SectionCard({ icon, title, children }: {
  icon: React.ReactNode
  title: string
  children: React.ReactNode
}) {
  return (
    <section className="card space-y-4">
      <div className="flex items-center gap-2">
        {icon}
        <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{title}</h2>
      </div>
      {children}
    </section>
  )
}

export default function ControlPanel() {
  const [selectedTank, setSelectedTank] = useState('')
  const [feedAmount, setFeedAmount] = useState(1.0)
  const [aerationBoost, setAerationBoost] = useState(30)
  const [exchangePct, setExchangePct] = useState(10)
  const [confirm, setConfirm] = useState<ConfirmDialog | null>(null)

  const { data: tanks = [] } = useQuery({ queryKey: ['tanks'], queryFn: listTanks })
  const ask = (dialog: ConfirmDialog) => setConfirm(dialog)

  const feedMut      = useMutation({ mutationFn: () => triggerFeeding(selectedTank, feedAmount) })
  const stopMut      = useMutation({ mutationFn: () => stopFeeding(selectedTank) })
  const pumpStartMut = useMutation({ mutationFn: () => controlPump(selectedTank, 'start') })
  const pumpStopMut  = useMutation({ mutationFn: () => controlPump(selectedTank, 'stop') })
  const aerationMut  = useMutation({ mutationFn: () => increaseAeration(selectedTank, aerationBoost) })
  const exchangeMut  = useMutation({ mutationFn: () => triggerWaterExchange(selectedTank, exchangePct) })

  const noTank = !selectedTank

  const rangeStyle = {
    accentColor: 'var(--teal-500)',
  }

  return (
    <div className="max-w-3xl space-y-5">
      {confirm && <ConfirmModal dialog={confirm} onClose={() => setConfirm(null)} />}

      <div className="flex items-center gap-2">
        <Sliders size={18} style={{ color: 'var(--teal-500)' }} />
        <h1 className="page-title">장비 제어</h1>
      </div>

      {/* Tank selector */}
      <div className="card">
        <label className="section-title block mb-2">수조 선택</label>
        <select
          value={selectedTank}
          onChange={(e) => setSelectedTank(e.target.value)}
          className="input-base"
        >
          <option value="">수조를 선택하세요</option>
          {tanks.map((t) => (
            <option key={t.tank_id} value={t.tank_id}>
              {t.name} ({t.tank_id})
            </option>
          ))}
        </select>
        {noTank && (
          <p className="text-xs mt-2" style={{ color: 'var(--text-muted)' }}>
            수조를 선택해야 제어 명령을 전송할 수 있습니다.
          </p>
        )}
      </div>

      {/* 급이 제어 */}
      <SectionCard
        icon={<Play size={15} style={{ color: 'var(--warn)' }} />}
        title="급이 제어"
      >
        <div>
          <label className="text-xs" style={{ color: 'var(--text-secondary)' }}>
            급이량: <strong>{feedAmount.toFixed(1)} kg</strong>
          </label>
          <input
            type="range" min={0.1} max={20} step={0.1}
            value={feedAmount}
            onChange={(e) => setFeedAmount(Number(e.target.value))}
            className="w-full mt-1.5"
            style={rangeStyle}
          />
          <div className="flex justify-between text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
            <span>0.1 kg</span><span>20 kg</span>
          </div>
        </div>
        <div className="flex gap-3">
          <button
            disabled={noTank || feedMut.isPending}
            onClick={() => ask({
              title: '급이 시작',
              description: `${selectedTank}에 ${feedAmount.toFixed(1)} kg 급이를 시작하시겠습니까?`,
              onConfirm: () => feedMut.mutate(),
            })}
            className="btn-primary flex items-center gap-1.5"
          >
            <Play size={13} />급이 시작
          </button>
          <button
            disabled={noTank || stopMut.isPending}
            onClick={() => ask({
              title: '긴급 정지',
              description: `${selectedTank} 급이기를 즉시 정지합니다. 계속하시겠습니까?`,
              onConfirm: () => stopMut.mutate(),
            })}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold text-white disabled:opacity-40 transition-colors"
            style={{ backgroundColor: 'var(--danger)' }}
          >
            <Pause size={13} />긴급 정지
          </button>
        </div>
        <StatusBadge jobId={(feedMut.data ?? stopMut.data)?.job_id} error={feedMut.isError || stopMut.isError} />
      </SectionCard>

      {/* 순환펌프 */}
      <SectionCard
        icon={<Waves size={15} style={{ color: 'var(--info)' }} />}
        title="순환펌프 제어"
      >
        <div className="flex gap-3">
          <button
            disabled={noTank || pumpStartMut.isPending}
            onClick={() => ask({
              title: '펌프 시작',
              description: `${selectedTank} 순환펌프를 가동합니다.`,
              onConfirm: () => pumpStartMut.mutate(),
            })}
            className="btn-primary flex items-center gap-1.5"
          >
            <Play size={13} />펌프 시작
          </button>
          <button
            disabled={noTank || pumpStopMut.isPending}
            onClick={() => ask({
              title: '펌프 정지',
              description: `${selectedTank} 순환펌프를 정지합니다.`,
              onConfirm: () => pumpStopMut.mutate(),
            })}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold disabled:opacity-40 transition-colors"
            style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--bg-border)', color: 'var(--text-secondary)' }}
          >
            <Pause size={13} />펌프 정지
          </button>
        </div>
        <StatusBadge jobId={(pumpStartMut.data ?? pumpStopMut.data)?.job_id} error={pumpStartMut.isError || pumpStopMut.isError} />
      </SectionCard>

      {/* 폭기 */}
      <SectionCard
        icon={<Wind size={15} style={{ color: 'var(--ok)' }} />}
        title="폭기 (Aeration) 제어"
      >
        <div>
          <label className="text-xs" style={{ color: 'var(--text-secondary)' }}>
            부스트: <strong>{aerationBoost}%</strong>
          </label>
          <input
            type="range" min={10} max={200} step={10}
            value={aerationBoost}
            onChange={(e) => setAerationBoost(Number(e.target.value))}
            className="w-full mt-1.5"
            style={{ accentColor: 'var(--ok)' }}
          />
          <div className="flex justify-between text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
            <span>10%</span><span>200%</span>
          </div>
        </div>
        <button
          disabled={noTank || aerationMut.isPending}
          onClick={() => ask({
            title: '폭기 강화',
            description: `${selectedTank} 폭기를 ${aerationBoost}% 증가시킵니다.`,
            onConfirm: () => aerationMut.mutate(),
          })}
          className="btn-primary flex items-center gap-1.5"
        >
          <Wind size={13} />폭기 강화
        </button>
        <StatusBadge jobId={aerationMut.data?.job_id} error={aerationMut.isError} />
      </SectionCard>

      {/* 환수 */}
      <SectionCard
        icon={<Droplets size={15} style={{ color: 'var(--blue-500)' }} />}
        title="부분 환수"
      >
        <div>
          <label className="text-xs" style={{ color: 'var(--text-secondary)' }}>
            환수 비율: <strong>{exchangePct}%</strong>
          </label>
          <input
            type="range" min={5} max={50} step={5}
            value={exchangePct}
            onChange={(e) => setExchangePct(Number(e.target.value))}
            className="w-full mt-1.5"
            style={{ accentColor: 'var(--blue-500)' }}
          />
          <div className="flex justify-between text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
            <span>5%</span><span>50%</span>
          </div>
        </div>
        <button
          disabled={noTank || exchangeMut.isPending}
          onClick={() => ask({
            title: '부분 환수',
            description: `${selectedTank} 수조 용량의 ${exchangePct}%를 환수합니다. 계속하시겠습니까?`,
            onConfirm: () => exchangeMut.mutate(),
          })}
          className="btn-primary flex items-center gap-1.5"
        >
          <Droplets size={13} />환수 실행
        </button>
        <StatusBadge jobId={exchangeMut.data?.job_id} error={exchangeMut.isError} />
      </SectionCard>
    </div>
  )
}
