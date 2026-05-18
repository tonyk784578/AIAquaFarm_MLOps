import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import {
  Activity, AlertTriangle, Box, Brain, CheckCircle, Clock, Database,
  GitBranch, History, PlayCircle, RefreshCw, Rocket, Server, Settings2,
  TrendingUp, XCircle,
} from 'lucide-react'

import { useAuth } from '@/context/AuthContext'
import {
  getFeedingModelStatus,
  getGrowthModelStatus,
  getMLOpsAudit,
  getMLOpsDrift,
  getMLOpsRegistry,
  getWaterQualityModelStatus,
  triggerMLOpsDeploy,
  triggerMLOpsPromote,
  triggerMLOpsRetrain,
} from '@/services/api'
import type {
  AuditEntry,
  DriftReport,
  ModelStatus,
  RegisteredModel,
} from '@/types'
import { summariseAudit } from '@/utils/format'

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

const AUDIT_KIND_COLORS: Record<string, string> = {
  automl:     'var(--info)',
  drift:      'var(--warn)',
  promotion:  'var(--ok)',
  rollback:   'var(--warn)',
  deployment: 'var(--teal-500)',
  training:   'var(--info)',
  error:      'var(--danger)',
}

const DRIFT_STATUS_COLORS: Record<string, string> = {
  stable:  'var(--ok)',
  warning: 'var(--warn)',
  drift:   'var(--danger)',
}

// ── Production model status card (loaded/version/device) ─────────────────────

function ModelCard({ info }: { info: (typeof MODEL_INFO)[number] }) {
  const { data, isLoading, isError, refetch } = useQuery<ModelStatus>({
    queryKey: ['model-status', info.key],
    queryFn: info.fetchFn,
    refetchInterval: 60_000,
  })

  return (
    <div className="card" style={{ borderLeft: `3px solid ${info.accentColor}` }}>
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-2">
          <Box size={14} style={{ color: 'var(--text-muted)' }} />
          <div>
            <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{info.label}</p>
            <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>{info.desc}</p>
          </div>
        </div>
        <button onClick={() => refetch()} className="p-1 transition-colors" style={{ color: 'var(--text-muted)' }}>
          <RefreshCw size={13} />
        </button>
      </div>

      {isLoading && <p className="text-sm animate-pulse" style={{ color: 'var(--text-muted)' }}>불러오는 중…</p>}
      {isError && (
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

// ── Live MLflow registry rows + superuser actions ────────────────────────────

function RegistryRow({ model, isSuperuser }: { model: RegisteredModel; isSuperuser: boolean }) {
  const qc = useQueryClient()
  const [busy, setBusy] = useState<string | null>(null)
  const [feedback, setFeedback] = useState<{ ok: boolean; msg: string } | null>(null)

  const retrain = useMutation({
    mutationFn: () => triggerMLOpsRetrain(model.name, true),
    onMutate: () => setBusy('retrain'),
    onSettled: () => setBusy(null),
    onSuccess: (data) => {
      setFeedback({ ok: data.ok, msg: data.detail })
      qc.invalidateQueries({ queryKey: ['mlops', 'audit'] })
    },
    onError: (err: Error) => setFeedback({ ok: false, msg: err.message }),
  })

  const deploy = useMutation({
    mutationFn: () => triggerMLOpsDeploy(model.name),
    onMutate: () => setBusy('deploy'),
    onSettled: () => setBusy(null),
    onSuccess: (data) => {
      setFeedback({ ok: data.ok, msg: data.detail })
      qc.invalidateQueries({ queryKey: ['mlops', 'audit'] })
    },
    onError: (err: Error) => setFeedback({ ok: false, msg: err.message }),
  })

  const promote = useMutation({
    mutationFn: (runId: string) => triggerMLOpsPromote(model.name, runId, false),
    onMutate: () => setBusy('promote'),
    onSettled: () => setBusy(null),
    onSuccess: (data) => {
      setFeedback({ ok: data.ok, msg: data.detail })
      qc.invalidateQueries({ queryKey: ['mlops', 'registry'] })
      qc.invalidateQueries({ queryKey: ['mlops', 'audit'] })
    },
    onError: (err: Error) => setFeedback({ ok: false, msg: err.message }),
  })

  const handlePromote = () => {
    const runId = window.prompt(`${model.name}: 승격할 MLflow run_id를 입력하세요`)
    if (runId) promote.mutate(runId)
  }

  const handleRetrain = () => {
    if (window.confirm(`${model.name} 재훈련 사이클을 트리거합니다 (dry-run). 계속하시겠습니까?`)) {
      retrain.mutate()
    }
  }

  const handleDeploy = () => {
    if (window.confirm(`${model.name} 의 Production 버전을 엣지에 배포합니다. 계속하시겠습니까?`)) {
      deploy.mutate()
    }
  }

  return (
    <tr style={{ borderBottom: '1px solid var(--bg-border)' }}>
      <td className="px-4 py-3 font-mono text-xs" style={{ color: 'var(--text-primary)' }}>{model.name}</td>
      <td className="px-4 py-3 text-center">
        {model.production_version ? (
          <span className="px-2 py-0.5 rounded text-xs font-semibold" style={{ backgroundColor: 'rgba(5,150,105,0.12)', color: 'var(--ok)' }}>v{model.production_version}</span>
        ) : (
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>—</span>
        )}
      </td>
      <td className="px-4 py-3 text-center">
        {model.staging_version ? (
          <span className="px-2 py-0.5 rounded text-xs font-semibold" style={{ backgroundColor: 'rgba(37,99,235,0.12)', color: 'var(--info)' }}>v{model.staging_version}</span>
        ) : (
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>—</span>
        )}
      </td>
      <td className="px-4 py-3 text-right text-xs font-mono" style={{ color: 'var(--text-secondary)' }}>{model.versions.length}</td>
      {isSuperuser && (
        <td className="px-4 py-3">
          <div className="flex justify-end gap-1.5 flex-wrap">
            <button onClick={handleRetrain} disabled={busy !== null}
              className="px-2 py-1 rounded text-xs font-semibold flex items-center gap-1 disabled:opacity-40"
              style={{ backgroundColor: 'rgba(37,99,235,0.12)', color: 'var(--info)' }}
              title="dry-run 재훈련 사이클 트리거">
              <PlayCircle size={11} />{busy === 'retrain' ? '실행중…' : '재훈련'}
            </button>
            <button onClick={handlePromote} disabled={busy !== null}
              className="px-2 py-1 rounded text-xs font-semibold flex items-center gap-1 disabled:opacity-40"
              style={{ backgroundColor: 'rgba(5,150,105,0.12)', color: 'var(--ok)' }}
              title="특정 run을 Production으로 승격">
              <Rocket size={11} />{busy === 'promote' ? '실행중…' : '승격'}
            </button>
            <button onClick={handleDeploy} disabled={busy !== null}
              className="px-2 py-1 rounded text-xs font-semibold flex items-center gap-1 disabled:opacity-40"
              style={{ backgroundColor: 'rgba(20,184,166,0.12)', color: 'var(--teal-500)' }}
              title="Production 버전을 엣지 디바이스에 배포">
              <Server size={11} />{busy === 'deploy' ? '실행중…' : '배포'}
            </button>
          </div>
          {feedback && (
            <p className="text-xs mt-1 text-right" style={{ color: feedback.ok ? 'var(--ok)' : 'var(--danger)' }}>
              {feedback.msg}
            </p>
          )}
        </td>
      )}
    </tr>
  )
}

function RegistryPanel({ isSuperuser }: { isSuperuser: boolean }) {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['mlops', 'registry'],
    queryFn: getMLOpsRegistry,
    refetchInterval: 60_000,
  })

  return (
    <section>
      <div className="flex items-center justify-between mb-2">
        <p className="section-title flex items-center gap-1.5">
          <GitBranch size={13} style={{ color: 'var(--text-muted)' }} />
          MLflow 레지스트리
        </p>
        <button onClick={() => refetch()} className="p-1" style={{ color: 'var(--text-muted)' }}>
          <RefreshCw size={13} />
        </button>
      </div>

      <div className="card p-0 overflow-hidden">
        {isLoading && <p className="text-sm p-4 animate-pulse" style={{ color: 'var(--text-muted)' }}>레지스트리 조회중…</p>}
        {isError && (
          <div className="p-4 flex items-center gap-2 text-sm" style={{ color: 'var(--danger)' }}>
            <XCircle size={14} />MLOps 서비스에 연결할 수 없습니다 (mlops_api 다운).
          </div>
        )}
        {data && (
          <table className="w-full text-sm">
            <thead>
              <tr style={{ borderBottom: '1px solid var(--bg-border)' }}>
                <th className="px-4 py-2.5 text-left text-xs font-semibold" style={{ color: 'var(--text-muted)' }}>모델</th>
                <th className="px-4 py-2.5 text-center text-xs font-semibold" style={{ color: 'var(--text-muted)' }}>Production</th>
                <th className="px-4 py-2.5 text-center text-xs font-semibold" style={{ color: 'var(--text-muted)' }}>Staging</th>
                <th className="px-4 py-2.5 text-right text-xs font-semibold" style={{ color: 'var(--text-muted)' }}>버전수</th>
                {isSuperuser && <th className="px-4 py-2.5 text-right text-xs font-semibold" style={{ color: 'var(--text-muted)' }}>관리자 액션</th>}
              </tr>
            </thead>
            <tbody>
              {data.models.length === 0 && (
                <tr>
                  <td colSpan={isSuperuser ? 5 : 4} className="px-4 py-4 text-center text-xs" style={{ color: 'var(--text-muted)' }}>
                    등록된 모델이 없습니다
                  </td>
                </tr>
              )}
              {data.models.map((m) => <RegistryRow key={m.name} model={m} isSuperuser={isSuperuser} />)}
            </tbody>
          </table>
        )}
      </div>
    </section>
  )
}

// ── Drift dashboard ──────────────────────────────────────────────────────────

function DriftCard({ report }: { report: DriftReport }) {
  const accent = report.should_retrain ? 'var(--danger)' : report.max_psi >= 0.1 ? 'var(--warn)' : 'var(--ok)'
  return (
    <div className="card" style={{ borderLeft: `3px solid ${accent}` }}>
      <div className="flex items-center justify-between mb-3">
        <p className="text-sm font-semibold font-mono" style={{ color: 'var(--text-primary)' }}>{report.model_name}</p>
        {report.should_retrain && (
          <span className="text-xs px-2 py-0.5 rounded font-semibold flex items-center gap-1" style={{ backgroundColor: 'rgba(220,38,38,0.12)', color: 'var(--danger)' }}>
            <AlertTriangle size={10} />재훈련 권장
          </span>
        )}
      </div>
      <div className="grid grid-cols-3 gap-2 mb-3 text-xs">
        <div>
          <p style={{ color: 'var(--text-muted)' }}>max PSI</p>
          <p className="font-mono font-bold text-sm" style={{ color: accent }}>{report.max_psi.toFixed(3)}</p>
        </div>
        <div>
          <p style={{ color: 'var(--text-muted)' }}>mean PSI</p>
          <p className="font-mono font-bold text-sm" style={{ color: 'var(--text-primary)' }}>{report.mean_psi.toFixed(3)}</p>
        </div>
        <div>
          <p style={{ color: 'var(--text-muted)' }}>샘플</p>
          <p className="font-mono text-sm" style={{ color: 'var(--text-secondary)' }}>{report.n_current}</p>
        </div>
      </div>
      <div className="space-y-1">
        {report.features.slice(0, 5).map((f) => (
          <div key={f.feature} className="flex items-center justify-between text-xs">
            <span className="font-mono" style={{ color: 'var(--text-secondary)' }}>{f.feature}</span>
            <span className="font-mono px-1.5 py-0.5 rounded font-semibold"
              style={{
                backgroundColor: `${DRIFT_STATUS_COLORS[f.status] || 'var(--text-muted)'}15`,
                color: DRIFT_STATUS_COLORS[f.status] || 'var(--text-muted)',
              }}>
              {f.psi.toFixed(3)}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

function DriftPanel() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['mlops', 'drift'],
    queryFn: getMLOpsDrift,
    refetchInterval: 60_000,
  })

  return (
    <section>
      <p className="section-title flex items-center gap-1.5">
        <TrendingUp size={13} style={{ color: 'var(--text-muted)' }} />
        최신 드리프트 리포트 (스케줄러 15분 주기)
      </p>

      {isLoading && <p className="text-sm animate-pulse" style={{ color: 'var(--text-muted)' }}>드리프트 리포트 로딩중…</p>}
      {isError && (
        <div className="card flex items-center gap-2 text-sm" style={{ color: 'var(--danger)' }}>
          <XCircle size={14} />드리프트 데이터 조회 실패
        </div>
      )}
      {data && Object.keys(data.reports).length === 0 && (
        <div className="card text-xs" style={{ color: 'var(--text-muted)' }}>
          아직 기록된 드리프트 사이클이 없습니다. 스케줄러가 시작되면 곧 채워집니다.
        </div>
      )}
      {data && Object.keys(data.reports).length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {Object.values(data.reports).map((r) => <DriftCard key={r.model_name} report={r} />)}
        </div>
      )}
    </section>
  )
}

// ── Audit timeline ───────────────────────────────────────────────────────────

function AuditRow({ event }: { event: AuditEntry }) {
  const color = AUDIT_KIND_COLORS[event.kind] || 'var(--text-muted)'
  const summary = summariseAudit(event)
  const ts = new Date(event.ts).toLocaleString()

  return (
    <li className="flex gap-3 py-2.5" style={{ borderBottom: '1px solid var(--bg-border)' }}>
      <div className="flex-shrink-0 mt-1">
        <span className="w-2 h-2 rounded-full inline-block" style={{ backgroundColor: color }} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="px-1.5 py-0.5 rounded text-xs font-semibold uppercase"
            style={{ backgroundColor: `${color}15`, color }}>
            {event.kind}
          </span>
          {event.model && (
            <span className="text-xs font-mono" style={{ color: 'var(--text-primary)' }}>{event.model}</span>
          )}
          <span className="text-xs ml-auto" style={{ color: 'var(--text-muted)' }}>{ts}</span>
        </div>
        {summary && <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>{summary}</p>}
      </div>
    </li>
  )
}

function AuditPanel() {
  const [kindFilter, setKindFilter] = useState<string>('')
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['mlops', 'audit', kindFilter],
    queryFn: () => getMLOpsAudit({ n: 50, ...(kindFilter ? { kind: kindFilter } : {}) }),
    refetchInterval: 30_000,
  })

  return (
    <section>
      <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
        <p className="section-title flex items-center gap-1.5">
          <History size={13} style={{ color: 'var(--text-muted)' }} />
          MLOps 감사 로그
        </p>
        <div className="flex items-center gap-1.5">
          <select
            value={kindFilter}
            onChange={(e) => setKindFilter(e.target.value)}
            className="text-xs rounded px-2 py-1"
            style={{
              backgroundColor: 'var(--bg-elevated)',
              border: '1px solid var(--bg-border)',
              color: 'var(--text-secondary)',
            }}
          >
            <option value="">전체</option>
            <option value="automl">automl</option>
            <option value="drift">drift</option>
            <option value="promotion">promotion</option>
            <option value="deployment">deployment</option>
            <option value="training">training</option>
            <option value="error">error</option>
          </select>
          <button onClick={() => refetch()} className="p-1" style={{ color: 'var(--text-muted)' }}>
            <RefreshCw size={13} />
          </button>
        </div>
      </div>

      <div className="card">
        {isLoading && <p className="text-sm animate-pulse" style={{ color: 'var(--text-muted)' }}>감사 로그 로딩중…</p>}
        {isError && (
          <div className="flex items-center gap-2 text-sm" style={{ color: 'var(--danger)' }}>
            <XCircle size={14} />감사 로그 조회 실패
          </div>
        )}
        {data && data.events.length === 0 && (
          <p className="text-xs text-center py-4" style={{ color: 'var(--text-muted)' }}>
            아직 기록된 이벤트가 없습니다
          </p>
        )}
        {data && data.events.length > 0 && (
          <ul className="space-y-0 max-h-96 overflow-y-auto">
            {[...data.events].reverse().map((e, i) => <AuditRow key={`${e.ts}-${i}`} event={e} />)}
          </ul>
        )}
      </div>
    </section>
  )
}

// ── Static guides ────────────────────────────────────────────────────────────

function LifecycleStep({ label, active, done }: { label: string; active?: boolean; done?: boolean }) {
  let bg = 'var(--bg-elevated)'
  let border = 'var(--bg-border)'
  let color = 'var(--text-muted)'
  if (done) { bg = 'rgba(5,150,105,0.1)'; border = 'rgba(5,150,105,0.3)'; color = 'var(--ok)' }
  if (active) { bg = 'rgba(37,99,235,0.12)'; border = 'rgba(37,99,235,0.4)'; color = 'var(--info)' }

  return (
    <div className="flex-1 text-center py-2 px-1 rounded-lg text-xs font-semibold"
      style={{ backgroundColor: bg, border: `1px solid ${border}`, color }}>
      {done && <CheckCircle size={11} className="inline mr-1" />}
      {label}
    </div>
  )
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function MLOpsPage() {
  const { user } = useAuth()
  const isSuperuser = Boolean(user?.is_superuser)

  return (
    <div className="space-y-6">
      <h1 className="page-title flex items-center gap-2">
        <Activity size={18} style={{ color: 'var(--teal-500)' }} />
        MLOps 모델 관리
        {isSuperuser && (
          <span className="text-xs px-2 py-0.5 rounded font-semibold ml-2" style={{ backgroundColor: 'rgba(220,38,38,0.12)', color: 'var(--danger)' }}>
            <Settings2 size={10} className="inline mr-1" />Superuser
          </span>
        )}
      </h1>

      <section>
        <p className="section-title flex items-center gap-1.5">
          <Box size={13} style={{ color: 'var(--text-muted)' }} />
          Production 모델 상태 (백엔드 AI 엔진)
        </p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {MODEL_INFO.map((info) => <ModelCard key={info.key} info={info} />)}
        </div>
      </section>

      <section>
        <Link to="/agents" className="card flex items-center gap-3 transition-colors group" style={{ borderLeft: '3px solid #8B5CF6' }}>
          <Brain size={18} style={{ color: '#8B5CF6' }} className="shrink-0" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>AI 에이전트 (LangGraph) 페이지로 이동</p>
            <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>실시간 사이클 상태, 그래프 토폴로지, 의사결정 트레이스는 별도 페이지에서 확인합니다.</p>
          </div>
          <RefreshCw size={14} style={{ color: 'var(--text-muted)' }} className="shrink-0 group-hover:rotate-90 transition-transform" />
        </Link>
      </section>

      <RegistryPanel isSuperuser={isSuperuser} />

      <DriftPanel />

      <AuditPanel />

      <section>
        <p className="section-title flex items-center gap-1.5">
          <Clock size={13} style={{ color: 'var(--text-muted)' }} />
          모델 생명주기
        </p>
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
            훈련 → QualityGate 통과 → Staging(Canary) A/B 테스트 → canary_wins 시 Production 승격.
            PSI ≥ 0.20 시 AutoML이 긴급 재훈련을 트리거합니다.
          </p>
        </div>
      </section>

      <section>
        <p className="section-title">PSI 드리프트 기준</p>
        <div className="card space-y-4">
          <div className="grid grid-cols-3 gap-3">
            {PSI_THRESHOLDS.map(({ label, range, colorVar }) => (
              <div key={label} className="rounded-xl p-3" style={{ backgroundColor: `${colorVar}12`, border: `1px solid ${colorVar}30` }}>
                <p className="text-sm font-bold mb-0.5" style={{ color: colorVar }}>{label}</p>
                <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>{range}</p>
              </div>
            ))}
          </div>
          <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
            스케줄러가 주기마다 모든 모델의 입력 특성 분포를 검사하며, PSI ≥ 0.20이면 샘플 임계값과 무관하게 즉시 재훈련이 트리거됩니다.
          </p>
        </div>
      </section>

      <section>
        <p className="section-title flex items-center gap-1.5">
          <Database size={13} style={{ color: 'var(--text-muted)' }} />
          AutoML 재훈련 임계값
        </p>
        <div className="card p-0 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr style={{ borderBottom: '1px solid var(--bg-border)' }}>
                {['모델','샘플 임계값','PSI 임계값','데이터 소스'].map((h, i) => (
                  <th key={h} className={`px-5 py-3 text-xs font-semibold ${i === 0 || i === 3 ? 'text-left' : 'text-right'}`} style={{ color: 'var(--text-muted)' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[
                { model: 'WaterQualityPredictor',     samples: '1,000 행',   psi: '≥ 0.20', source: 'raw/sensor/' },
                { model: 'FeedingActivityClassifier', samples: '300 이미지', psi: '≥ 0.20', source: 'raw/labelled/feeding/' },
                { model: 'FishDetection',             samples: '500 이미지', psi: '≥ 0.20', source: 'raw/labelled/growth/' },
              ].map((row) => (
                <tr key={row.model} style={{ borderBottom: '1px solid var(--bg-border)' }}>
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
