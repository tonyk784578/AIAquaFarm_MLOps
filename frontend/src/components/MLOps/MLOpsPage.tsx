import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Activity, Box, Brain, CheckCircle, RefreshCw, XCircle } from 'lucide-react'
import {
  getFeedingModelStatus, getGrowthModelStatus, getWaterQualityModelStatus,
} from '@/services/api'
import type { ModelStatus } from '@/types'

const MODEL_INFO = [
  { key: 'growth',  label: 'FishDetection',              desc: 'YOLOv8 어류 탐지 모델',       accentColor: 'var(--ok)',   fetchFn: getGrowthModelStatus  },
  { key: 'feeding', label: 'FeedingActivityClassifier',   desc: 'ResNet18 급이 활성도 분류기',  accentColor: 'var(--warn)', fetchFn: getFeedingModelStatus },
  { key: 'water',   label: 'WaterQualityPredictor',       desc: 'LSTM 수질 예측 모델',          accentColor: 'var(--info)', fetchFn: getWaterQualityModelStatus },
] as const

const PSI_THRESHOLDS = [
  { label: '안정',   range: '< 0.10',     colorVar: 'var(--ok)'     },
  { label: '경고',   range: '0.10 – 0.19', colorVar: 'var(--warn)'  },
  { label: '재훈련', range: '≥ 0.20',     colorVar: 'var(--danger)' },
]

function ModelCard({ info }: { info: (typeof MODEL_INFO)[number] }) {
  const { data, isLoading, isError, refetch } = useQuery<ModelStatus>({
    queryKey: ['model-status', info.key],
    queryFn: info.fetchFn,
    refetchInterval: 60_000,
  })

  return (
    <div
      className="card"
      style={{ borderLeft: `3px solid ${info.accentColor}` }}
    >
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-2">
          <Box size={14} style={{ color: 'var(--text-muted)' }} />
          <div>
            <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{info.label}</p>
            <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>{info.desc}</p>
          </div>
        </div>
        <button
          onClick={() => refetch()}
          className="p-1 transition-colors"
          style={{ color: 'var(--text-muted)' }}
        >
          <RefreshCw size={13} />
        </button>
      </div>

      {isLoading && <p className="text-sm animate-pulse" style={{ color: 'var(--text-muted)' }}>불러오는 중…</p>}
      {isError  && (
        <div className="flex items-center gap-1.5 text-sm" style={{ color: 'var(--danger)' }}>
          <XCircle size={14} />상태 조회 실패
        </div>
      )}

      {data && (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            {data.is_loaded ? (
              <>
                <span className="w-2 h-2 rounded-full animate-pulse" style={{ backgroundColor: info.accentColor }} />
                <span className="text-xs font-semibold" style={{ color: 'var(--ok)' }}>로드됨</span>
              </>
            ) : (
              <>
                <span className="w-2 h-2 rounded-full" style={{ backgroundColor: 'var(--text-muted)' }} />
                <span className="text-xs" style={{ color: 'var(--text-muted)' }}>미로드</span>
              </>
            )}
          </div>
          <div className="grid grid-cols-2 gap-3 text-xs">
            <div>
              <p className="mb-0.5" style={{ color: 'var(--text-muted)' }}>버전</p>
              <p className="font-mono font-medium" style={{ color: 'var(--text-primary)' }}>{data.model_version || '—'}</p>
            </div>
            <div>
              <p className="mb-0.5" style={{ color: 'var(--text-muted)' }}>디바이스</p>
              <p className="font-mono font-medium" style={{ color: 'var(--text-primary)' }}>{data.device || '—'}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function LifecycleStep({ label, active, done }: { label: string; active?: boolean; done?: boolean }) {
  let bg = 'var(--bg-elevated)'
  let border = 'var(--bg-border)'
  let color = 'var(--text-muted)'

  if (done)   { bg = 'rgba(5,150,105,0.1)';  border = 'rgba(5,150,105,0.3)';  color = 'var(--ok)'   }
  if (active) { bg = 'rgba(37,99,235,0.12)'; border = 'rgba(37,99,235,0.4)';  color = 'var(--info)' }

  return (
    <div
      className="flex-1 text-center py-2 px-1 rounded-lg text-xs font-semibold"
      style={{ backgroundColor: bg, border: `1px solid ${border}`, color }}
    >
      {done && <CheckCircle size={11} className="inline mr-1" />}
      {label}
    </div>
  )
}

export default function MLOpsPage() {
  return (
    <div className="space-y-6">
      <h1 className="page-title flex items-center gap-2">
        <Activity size={18} style={{ color: 'var(--teal-500)' }} />
        MLOps 모델 관리
      </h1>

      {/* Model status */}
      <section>
        <p className="section-title">Production 모델 상태</p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {MODEL_INFO.map((info) => <ModelCard key={info.key} info={info} />)}
        </div>
      </section>

      {/* Cross-link to the dedicated Agents page */}
      <section>
        <Link
          to="/agents"
          className="card flex items-center gap-3 transition-colors group"
          style={{ borderLeft: '3px solid #8B5CF6' }}
        >
          <Brain size={18} style={{ color: '#8B5CF6' }} className="shrink-0" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
              AI 에이전트 (LangGraph) 페이지로 이동
            </p>
            <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
              실시간 사이클 상태, 그래프 토폴로지, 의사결정 트레이스는 별도 페이지에서 확인합니다.
            </p>
          </div>
          <RefreshCw size={14} style={{ color: 'var(--text-muted)' }} className="shrink-0 group-hover:rotate-90 transition-transform" />
        </Link>
      </section>

      {/* Lifecycle */}
      <section>
        <p className="section-title">모델 생명주기</p>
        <div className="card">
          <div className="flex items-center gap-2 text-xs">
            <LifecycleStep label="None" done />
            <span style={{ color: 'var(--text-muted)' }} className="text-lg font-bold">→</span>
            <LifecycleStep label="Staging (Canary)" done />
            <span style={{ color: 'var(--text-muted)' }} className="text-lg font-bold">→</span>
            <LifecycleStep label="Production" active />
            <span style={{ color: 'var(--text-muted)' }} className="text-lg font-bold">→</span>
            <LifecycleStep label="Archived" />
          </div>
          <p className="text-xs mt-3" style={{ color: 'var(--text-muted)' }}>
            훈련 → QualityGate 통과 → Staging(Canary) A/B 테스트 →
            canary_wins 시 Production 승격. PSI ≥ 0.20 시 AutoML이 긴급 재훈련 트리거.
          </p>
        </div>
      </section>

      {/* PSI guide */}
      <section>
        <p className="section-title">PSI 드리프트 기준</p>
        <div className="card space-y-4">
          <div className="grid grid-cols-3 gap-3">
            {PSI_THRESHOLDS.map(({ label, range, colorVar }) => (
              <div
                key={label}
                className="rounded-xl p-3"
                style={{ backgroundColor: `${colorVar}12`, border: `1px solid ${colorVar}30` }}
              >
                <p className="text-sm font-bold mb-0.5" style={{ color: colorVar }}>{label}</p>
                <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>{range}</p>
              </div>
            ))}
          </div>
          <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
            PSI(Population Stability Index)는 참조(훈련) 분포와 현재(추론) 분포 간 이동을 측정합니다.
            AutoML 파이프라인이 6시간마다 모든 모델의 입력 특성 분포를 검사하며,
            PSI ≥ 0.20이면 샘플 임계값과 무관하게 즉시 재훈련이 트리거됩니다.
          </p>
        </div>
      </section>

      {/* A/B testing */}
      <section>
        <p className="section-title">A/B 테스트 (Canary 배포)</p>
        <div className="card space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
            <div className="space-y-2">
              <p className="font-semibold" style={{ color: 'var(--text-primary)' }}>라우팅 방식</p>
              <p style={{ color: 'var(--text-secondary)' }}>
                요청 해시 기반 결정적 라우팅 — 동일 요청은 항상 동일 모델로 라우팅됩니다.
                기본 canary 비율: 10%.
              </p>
            </div>
            <div className="space-y-2">
              <p className="font-semibold" style={{ color: 'var(--text-primary)' }}>API 사용 방법</p>
              <div className="rounded-xl p-3 font-mono text-xs space-y-1" style={{ backgroundColor: 'var(--bg-elevated)' }}>
                <p><span style={{ color: 'var(--info)' }}>POST</span> <span style={{ color: 'var(--text-secondary)' }}>/v1/admin/models/promote-canary</span></p>
                <p><span style={{ color: 'var(--ok)' }}>POST</span> <span style={{ color: 'var(--text-secondary)' }}>/v1/admin/models/graduate</span></p>
                <p><span style={{ color: 'var(--danger)' }}>POST</span> <span style={{ color: 'var(--text-secondary)' }}>/v1/admin/models/rollback</span></p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* AutoML table */}
      <section>
        <p className="section-title">AutoML 재훈련 임계값</p>
        <div className="card p-0 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr style={{ borderBottom: '1px solid var(--bg-border)' }}>
                {['모델','샘플 임계값','PSI 임계값','데이터 소스'].map((h, i) => (
                  <th
                    key={h}
                    className={`px-5 py-3 text-xs font-semibold ${i === 0 || i === 3 ? 'text-left' : 'text-right'}`}
                    style={{ color: 'var(--text-muted)' }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[
                { model: 'WaterQualityPredictor',        samples: '1,000 행',      psi: '≥ 0.20', source: 'raw/sensor/' },
                { model: 'FeedingActivityClassifier',    samples: '300 이미지',    psi: '≥ 0.20', source: 'raw/labelled/feeding/' },
                { model: 'FishDetection',                samples: '500 이미지',    psi: '≥ 0.20', source: 'raw/labelled/growth/' },
              ].map((row) => (
                <tr
                  key={row.model}
                  style={{ borderBottom: '1px solid var(--bg-border)' }}
                  onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = 'var(--bg-elevated)' }}
                  onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = '' }}
                >
                  <td className="px-5 py-3 font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>{row.model}</td>
                  <td className="px-5 py-3 text-right text-sm" style={{ color: 'var(--text-primary)' }}>{row.samples}</td>
                  <td className="px-5 py-3 text-right text-sm font-semibold" style={{ color: 'var(--danger)' }}>{row.psi}</td>
                  <td className="px-5 py-3 font-mono text-xs" style={{ color: 'var(--text-muted)' }}>{row.source}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
