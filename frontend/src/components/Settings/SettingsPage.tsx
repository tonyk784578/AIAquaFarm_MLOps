import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { CheckCircle, XCircle, Cpu, RefreshCw, Settings } from 'lucide-react'
import {
  getFeedingModelStatus, getFarmSettings,
  getGrowthModelStatus, getWaterQualityModelStatus, updateFarmSettings,
} from '@/services/api'
import type { FarmSettings, ModelStatus } from '@/types'
import { useAuth } from '@/context/AuthContext'

function ModelCard({ model }: { model: ModelStatus | undefined }) {
  if (!model) {
    return (
      <div
        className="rounded-2xl p-4 h-28 animate-pulse"
        style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--bg-border)' }}
      />
    )
  }
  return (
    <div
      className="rounded-2xl p-4 space-y-2"
      style={{
        backgroundColor: 'var(--bg-surface)',
        border: `1px solid ${model.is_loaded ? 'rgba(5,150,105,0.3)' : 'var(--bg-border)'}`,
        boxShadow: 'var(--shadow-sm)',
      }}
    >
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{model.model_name}</span>
        {model.is_loaded
          ? <CheckCircle size={15} style={{ color: 'var(--ok)' }} />
          : <XCircle    size={15} style={{ color: 'var(--danger)' }} />
        }
      </div>
      <div className="text-xs space-y-0.5">
        <p style={{ color: 'var(--text-muted)' }}>
          버전: <span style={{ color: 'var(--text-secondary)' }}>{model.model_version || '—'}</span>
        </p>
        <p style={{ color: 'var(--text-muted)' }}>
          디바이스: <span style={{ color: 'var(--text-secondary)' }}>{model.device}</span>
        </p>
        <p style={{ color: 'var(--text-muted)' }}>
          상태:{' '}
          <span style={{ color: model.is_loaded ? 'var(--ok)' : 'var(--danger)', fontWeight: 600 }}>
            {model.is_loaded ? '정상 로드' : '미로드 (degraded)'}
          </span>
        </p>
      </div>
    </div>
  )
}

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
      <label className="text-sm flex-1" style={{ color: 'var(--text-secondary)' }}>{label}</label>
      <div className="flex items-center gap-2">
        <input
          type="number"
          value={value}
          step={step}
          min={min}
          max={max}
          onChange={(e) => onChange(parseFloat(e.target.value))}
          className="input-base text-right"
          style={{ width: 96 }}
        />
        <span className="text-xs w-10 shrink-0" style={{ color: 'var(--text-muted)' }}>{unit}</span>
      </div>
    </div>
  )
}

export default function SettingsPage() {
  const { user } = useAuth()
  const qc = useQueryClient()

  const { data: wqStatus,     isLoading: wqLoading }      = useQuery({ queryKey: ['model-status', 'water-quality'], queryFn: getWaterQualityModelStatus, retry: false })
  const { data: growthStatus, isLoading: growthLoading }   = useQuery({ queryKey: ['model-status', 'growth'],        queryFn: getGrowthModelStatus,        retry: false })
  const { data: feedingStatus,isLoading: feedingLoading }  = useQuery({ queryKey: ['model-status', 'feeding'],       queryFn: getFeedingModelStatus,       retry: false })
  const { data: remoteSettings }                           = useQuery({ queryKey: ['farm-settings'],                 queryFn: getFarmSettings,             retry: false })

  const [draft, setDraft] = useState<Partial<FarmSettings>>({})
  const effective: FarmSettings = {
    ammonia_threshold_ppm:      0.5,
    nitrite_threshold_ppm:      0.1,
    dissolved_oxygen_min_mgl:   6.0,
    ph_min:                     6.5,
    ph_max:                     8.5,
    temperature_min_c:         18.0,
    temperature_max_c:         28.0,
    sensor_poll_interval:       5,
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
    <div className="max-w-3xl space-y-6">
      <h1 className="page-title flex items-center gap-2">
        <Settings size={18} style={{ color: 'var(--teal-500)' }} />
        시스템 설정
      </h1>

      {/* Account */}
      <section className="card space-y-2">
        <p className="section-title">계정 정보</p>
        <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
          사용자:{' '}
          <span className="font-semibold" style={{ color: 'var(--text-primary)' }}>{user?.username}</span>
          {user?.is_superuser && (
            <span className="ml-2 badge-warn">관리자</span>
          )}
        </p>
        <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
          이메일: <span style={{ color: 'var(--text-primary)' }}>{user?.email}</span>
        </p>
      </section>

      {/* AI Models */}
      <section>
        <div className="flex items-center gap-2 mb-3">
          <Cpu size={14} style={{ color: 'var(--teal-500)' }} />
          <p className="section-title mb-0">AI 모델 상태</p>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <ModelCard model={wqLoading      ? undefined : wqStatus}      />
          <ModelCard model={growthLoading  ? undefined : growthStatus}  />
          <ModelCard model={feedingLoading ? undefined : feedingStatus} />
        </div>
        <p className="text-xs mt-2" style={{ color: 'var(--text-muted)' }}>
          모델이 미로드 상태이면 규칙 기반 예측으로 대체됩니다.
        </p>
      </section>

      {/* Thresholds */}
      <section className="card space-y-4">
        <p className="section-title">경보 임계값</p>

        <div className="space-y-4">
          {/* Water quality */}
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: 'var(--info)' }}>수질</p>
            <div className="space-y-3">
              <ThresholdField label="암모니아 (NH₃) 경고" value={effective.ammonia_threshold_ppm}    unit="ppm"  step={0.05} min={0} onChange={(v) => setField('ammonia_threshold_ppm', v)} />
              <ThresholdField label="아질산 (NO₂) 경고"   value={effective.nitrite_threshold_ppm}    unit="ppm"  step={0.01} min={0} onChange={(v) => setField('nitrite_threshold_ppm', v)} />
              <ThresholdField label="용존산소 최소"         value={effective.dissolved_oxygen_min_mgl} unit="mg/L" step={0.1}  min={0} onChange={(v) => setField('dissolved_oxygen_min_mgl', v)} />
            </div>
          </div>

          <div className="h-px" style={{ backgroundColor: 'var(--bg-border)' }} />

          {/* pH */}
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: 'var(--warn)' }}>pH</p>
            <div className="space-y-3">
              <ThresholdField label="pH 최소" value={effective.ph_min} unit="" step={0.1} min={0} max={14} onChange={(v) => setField('ph_min', v)} />
              <ThresholdField label="pH 최대" value={effective.ph_max} unit="" step={0.1} min={0} max={14} onChange={(v) => setField('ph_max', v)} />
            </div>
          </div>

          <div className="h-px" style={{ backgroundColor: 'var(--bg-border)' }} />

          {/* Temperature */}
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: 'var(--danger)' }}>온도</p>
            <div className="space-y-3">
              <ThresholdField label="온도 최소" value={effective.temperature_min_c} unit="°C" step={0.5} onChange={(v) => setField('temperature_min_c', v)} />
              <ThresholdField label="온도 최대" value={effective.temperature_max_c} unit="°C" step={0.5} onChange={(v) => setField('temperature_max_c', v)} />
            </div>
          </div>
        </div>

        {hasDraft && (
          <div
            className="flex items-center justify-between pt-4"
            style={{ borderTop: '1px solid var(--bg-border)' }}
          >
            <span className="text-xs font-medium" style={{ color: 'var(--warn)' }}>저장되지 않은 변경사항이 있습니다.</span>
            <div className="flex gap-2">
              <button
                onClick={() => setDraft({})}
                className="text-xs px-3 py-1.5 rounded-lg transition-colors"
                style={{ color: 'var(--text-secondary)' }}
              >
                취소
              </button>
              <button
                onClick={() => saveSettings()}
                disabled={saving}
                className="btn-primary flex items-center gap-1.5 text-xs"
                style={{ padding: '6px 14px' }}
              >
                {saving && <RefreshCw size={12} className="animate-spin" />}
                저장
              </button>
            </div>
          </div>
        )}
      </section>

      {/* Sensor interval */}
      <section className="card space-y-3">
        <p className="section-title">센서 폴링 간격</p>
        <ThresholdField
          label="실시간 업데이트 주기"
          value={effective.sensor_poll_interval}
          unit="초"
          step={1}
          min={1}
          onChange={(v) => setField('sensor_poll_interval', Math.round(v))}
        />
        <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
          백엔드 가상 센서가 Redis로 데이터를 전송하는 주기입니다.
        </p>
      </section>
    </div>
  )
}
