// Settings page — shows AI model load status and editable alert thresholds.

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { CheckCircle, XCircle, Cpu, RefreshCw } from 'lucide-react'
import {
  getFeedingModelStatus,
  getFarmSettings,
  getGrowthModelStatus,
  getWaterQualityModelStatus,
  updateFarmSettings,
} from '@/services/api'
import type { FarmSettings, ModelStatus } from '@/types'
import { useAuth } from '@/context/AuthContext'

// ── Model status card ──────────────────────────────────────────────────────────

function ModelCard({ model }: { model: ModelStatus | undefined }) {
  if (!model) {
    return (
      <div className="bg-slate-800 rounded-xl p-4 ring-1 ring-slate-700 animate-pulse h-28" />
    )
  }
  return (
    <div className="bg-slate-800 rounded-xl p-4 ring-1 ring-slate-700 space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-slate-200">{model.model_name}</span>
        {model.is_loaded ? (
          <CheckCircle className="w-4 h-4 text-emerald-400" />
        ) : (
          <XCircle className="w-4 h-4 text-red-400" />
        )}
      </div>
      <div className="text-xs text-slate-400 space-y-0.5">
        <p>버전: <span className="text-slate-300">{model.model_version || '—'}</span></p>
        <p>디바이스: <span className="text-slate-300">{model.device}</span></p>
        <p>
          상태:{' '}
          <span className={model.is_loaded ? 'text-emerald-400' : 'text-red-400'}>
            {model.is_loaded ? '정상 로드' : '미로드 (degraded)'}
          </span>
        </p>
      </div>
    </div>
  )
}

// ── Threshold field ────────────────────────────────────────────────────────────

interface ThresholdFieldProps {
  label: string
  value: number
  unit: string
  step?: number
  min?: number
  max?: number
  onChange: (v: number) => void
}

function ThresholdField({ label, value, unit, step = 0.1, min, max, onChange }: ThresholdFieldProps) {
  return (
    <div className="flex items-center justify-between gap-4">
      <label className="text-sm text-slate-300 flex-1">{label}</label>
      <div className="flex items-center gap-1.5">
        <input
          type="number"
          value={value}
          step={step}
          min={min}
          max={max}
          onChange={(e) => onChange(parseFloat(e.target.value))}
          className="w-24 bg-slate-900 border border-slate-700 rounded-lg px-2 py-1
                     text-slate-100 text-sm text-right
                     focus:outline-none focus:ring-1 focus:ring-sky-500/50"
        />
        <span className="text-xs text-slate-500 w-12">{unit}</span>
      </div>
    </div>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function SettingsPage() {
  const { user } = useAuth()
  const qc = useQueryClient()

  const { data: wqStatus, isLoading: wqLoading } = useQuery({
    queryKey: ['model-status', 'water-quality'],
    queryFn: getWaterQualityModelStatus,
    retry: false,
  })
  const { data: growthStatus, isLoading: growthLoading } = useQuery({
    queryKey: ['model-status', 'growth'],
    queryFn: getGrowthModelStatus,
    retry: false,
  })
  const { data: feedingStatus, isLoading: feedingLoading } = useQuery({
    queryKey: ['model-status', 'feeding'],
    queryFn: getFeedingModelStatus,
    retry: false,
  })

  const { data: remoteSettings } = useQuery({
    queryKey: ['farm-settings'],
    queryFn: getFarmSettings,
    retry: false,
  })

  const [draft, setDraft] = useState<Partial<FarmSettings>>({})
  const effective: FarmSettings = {
    ammonia_threshold_ppm: 0.5,
    nitrite_threshold_ppm: 0.1,
    dissolved_oxygen_min_mgl: 6.0,
    ph_min: 6.5,
    ph_max: 8.5,
    temperature_min_c: 18.0,
    temperature_max_c: 28.0,
    sensor_poll_interval: 5,
    ...remoteSettings,
    ...draft,
  }

  function setField<K extends keyof FarmSettings>(key: K, value: FarmSettings[K]) {
    setDraft((d) => ({ ...d, [key]: value }))
  }

  const { mutate: saveSettings, isPending: saving } = useMutation({
    mutationFn: () => updateFarmSettings(draft),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['farm-settings'] })
      setDraft({})
    },
  })

  const hasDraft = Object.keys(draft).length > 0

  return (
    <div className="max-w-3xl space-y-8">
      <h1 className="text-xl font-semibold text-slate-100">시스템 설정</h1>

      {/* User info */}
      <section className="bg-slate-800 rounded-2xl p-5 ring-1 ring-slate-700 space-y-1">
        <h2 className="text-sm font-medium text-slate-300 mb-3">계정 정보</h2>
        <p className="text-sm text-slate-400">
          사용자: <span className="text-slate-200 font-medium">{user?.username}</span>
          {user?.is_superuser && (
            <span className="ml-2 text-xs bg-amber-500/20 text-amber-400 px-1.5 py-0.5 rounded">
              관리자
            </span>
          )}
        </p>
        <p className="text-sm text-slate-400">
          이메일: <span className="text-slate-200">{user?.email}</span>
        </p>
      </section>

      {/* AI model status */}
      <section className="space-y-3">
        <div className="flex items-center gap-2">
          <Cpu className="w-4 h-4 text-sky-400" />
          <h2 className="text-sm font-medium text-slate-300">AI 모델 상태</h2>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <ModelCard model={wqLoading ? undefined : wqStatus} />
          <ModelCard model={growthLoading ? undefined : growthStatus} />
          <ModelCard model={feedingLoading ? undefined : feedingStatus} />
        </div>
        <p className="text-xs text-slate-500">
          모델이 미로드 상태이면 규칙 기반 예측으로 대체됩니다.
        </p>
      </section>

      {/* Alert thresholds */}
      <section className="bg-slate-800 rounded-2xl p-5 ring-1 ring-slate-700 space-y-4">
        <h2 className="text-sm font-medium text-slate-300">경보 임계값</h2>

        <div className="space-y-3 divide-y divide-slate-700/50">
          <div className="space-y-3 pb-3">
            <p className="text-xs text-slate-500 uppercase tracking-wider">수질</p>
            <ThresholdField
              label="암모니아 (NH₃) 경고"
              value={effective.ammonia_threshold_ppm}
              unit="ppm"
              step={0.05}
              min={0}
              onChange={(v) => setField('ammonia_threshold_ppm', v)}
            />
            <ThresholdField
              label="아질산 (NO₂) 경고"
              value={effective.nitrite_threshold_ppm}
              unit="ppm"
              step={0.01}
              min={0}
              onChange={(v) => setField('nitrite_threshold_ppm', v)}
            />
            <ThresholdField
              label="용존산소 최소"
              value={effective.dissolved_oxygen_min_mgl}
              unit="mg/L"
              step={0.1}
              min={0}
              onChange={(v) => setField('dissolved_oxygen_min_mgl', v)}
            />
          </div>

          <div className="space-y-3 py-3">
            <p className="text-xs text-slate-500 uppercase tracking-wider">pH</p>
            <ThresholdField
              label="pH 최소"
              value={effective.ph_min}
              unit=""
              step={0.1}
              min={0}
              max={14}
              onChange={(v) => setField('ph_min', v)}
            />
            <ThresholdField
              label="pH 최대"
              value={effective.ph_max}
              unit=""
              step={0.1}
              min={0}
              max={14}
              onChange={(v) => setField('ph_max', v)}
            />
          </div>

          <div className="space-y-3 pt-3">
            <p className="text-xs text-slate-500 uppercase tracking-wider">온도</p>
            <ThresholdField
              label="온도 최소"
              value={effective.temperature_min_c}
              unit="°C"
              step={0.5}
              onChange={(v) => setField('temperature_min_c', v)}
            />
            <ThresholdField
              label="온도 최대"
              value={effective.temperature_max_c}
              unit="°C"
              step={0.5}
              onChange={(v) => setField('temperature_max_c', v)}
            />
          </div>
        </div>

        {hasDraft && (
          <div className="flex items-center justify-between pt-2 border-t border-slate-700">
            <span className="text-xs text-amber-400">저장되지 않은 변경사항이 있습니다.</span>
            <div className="flex gap-2">
              <button
                onClick={() => setDraft({})}
                className="text-xs px-3 py-1.5 rounded-lg text-slate-400 hover:text-slate-200 transition-colors"
              >
                취소
              </button>
              <button
                onClick={() => saveSettings()}
                disabled={saving}
                className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg
                           bg-sky-600 hover:bg-sky-500 disabled:bg-slate-700
                           text-white transition-colors"
              >
                {saving && <RefreshCw className="w-3 h-3 animate-spin" />}
                저장
              </button>
            </div>
          </div>
        )}
      </section>

      {/* Sensor poll interval */}
      <section className="bg-slate-800 rounded-2xl p-5 ring-1 ring-slate-700 space-y-3">
        <h2 className="text-sm font-medium text-slate-300">센서 폴링 간격</h2>
        <ThresholdField
          label="실시간 업데이트 주기"
          value={effective.sensor_poll_interval}
          unit="초"
          step={1}
          min={1}
          onChange={(v) => setField('sensor_poll_interval', Math.round(v))}
        />
        <p className="text-xs text-slate-500">
          백엔드 가상 센서가 Redis로 데이터를 전송하는 주기입니다.
        </p>
      </section>
    </div>
  )
}
