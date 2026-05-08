import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Activity, Box, Brain, CheckCircle, RefreshCw, XCircle, Zap } from 'lucide-react'
import {
  getFeedingModelStatus,
  getGrowthModelStatus,
  getWaterQualityModelStatus,
  getAgentCycleStatus,
  getAgentHealth,
  triggerAgentCycle,
} from '@/services/api'
import type { AgentCycleStatus, ModelStatus } from '@/types'

const MODEL_INFO = [
  {
    key: 'growth',
    label: 'FishDetection',
    desc: 'YOLOv8 어류 탐지 모델',
    color: 'emerald',
    fetchFn: getGrowthModelStatus,
  },
  {
    key: 'feeding',
    label: 'FeedingActivityClassifier',
    desc: 'ResNet18 급이 활성도 분류기',
    color: 'amber',
    fetchFn: getFeedingModelStatus,
  },
  {
    key: 'water',
    label: 'WaterQualityPredictor',
    desc: 'LSTM 수질 예측 모델',
    color: 'sky',
    fetchFn: getWaterQualityModelStatus,
  },
] as const

const PSI_THRESHOLDS = [
  { label: '안정', range: '< 0.10', color: 'text-emerald-400', bg: 'bg-emerald-400/10' },
  { label: '경고', range: '0.10 – 0.19', color: 'text-yellow-400', bg: 'bg-yellow-400/10' },
  { label: '재훈련', range: '≥ 0.20', color: 'text-red-400', bg: 'bg-red-400/10' },
]

function ModelCard({ info }: { info: (typeof MODEL_INFO)[number] }) {
  const { data, isLoading, isError, refetch } = useQuery<ModelStatus>({
    queryKey: ['model-status', info.key],
    queryFn: info.fetchFn,
    refetchInterval: 60_000,
  })

  const colorMap: Record<string, string> = {
    emerald: 'border-emerald-500/30 bg-emerald-500/5',
    amber: 'border-amber-500/30 bg-amber-500/5',
    sky: 'border-sky-500/30 bg-sky-500/5',
  }
  const dotMap: Record<string, string> = {
    emerald: 'bg-emerald-400',
    amber: 'bg-amber-400',
    sky: 'bg-sky-400',
  }

  return (
    <div className={`rounded-xl border p-5 ${colorMap[info.color]}`}>
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-2">
          <Box className="w-4 h-4 text-slate-400" />
          <div>
            <p className="text-sm font-semibold text-slate-100">{info.label}</p>
            <p className="text-xs text-slate-500">{info.desc}</p>
          </div>
        </div>
        <button onClick={() => refetch()} className="text-slate-500 hover:text-slate-300 transition-colors">
          <RefreshCw className="w-3.5 h-3.5" />
        </button>
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 text-slate-500 text-sm">
          <RefreshCw className="w-3.5 h-3.5 animate-spin" />
          불러오는 중…
        </div>
      )}

      {isError && (
        <div className="flex items-center gap-2 text-red-400 text-sm">
          <XCircle className="w-4 h-4" />
          상태 조회 실패
        </div>
      )}

      {data && (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            {data.is_loaded ? (
              <>
                <span className={`w-2 h-2 rounded-full ${dotMap[info.color]} animate-pulse`} />
                <span className="text-xs text-emerald-400 font-medium">로드됨</span>
              </>
            ) : (
              <>
                <span className="w-2 h-2 rounded-full bg-slate-500" />
                <span className="text-xs text-slate-400">미로드</span>
              </>
            )}
          </div>
          <div className="grid grid-cols-2 gap-3 text-xs">
            <div>
              <p className="text-slate-500 mb-0.5">버전</p>
              <p className="text-slate-200 font-mono">{data.model_version || '—'}</p>
            </div>
            <div>
              <p className="text-slate-500 mb-0.5">디바이스</p>
              <p className="text-slate-200 font-mono">{data.device || '—'}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function LifecycleStep({ label, active, done }: { label: string; active?: boolean; done?: boolean }) {
  return (
    <div className={`flex-1 text-center py-2 px-1 rounded-lg text-xs font-medium border transition-colors ${
      done
        ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
        : active
        ? 'bg-sky-500/20 border-sky-500/40 text-sky-400'
        : 'bg-slate-700/50 border-slate-700 text-slate-500'
    }`}>
      {done && <CheckCircle className="w-3 h-3 inline mr-1" />}
      {label}
    </div>
  )
}

// ── Agent cycle panel ──────────────────────────────────────────────────────────

function AgentPanel() {
  const qc = useQueryClient()

  const { data: health } = useQuery({
    queryKey: ['agent-health'],
    queryFn: getAgentHealth,
    refetchInterval: 30_000,
    retry: false,
  })

  const { data: status, isLoading: statusLoading } = useQuery<AgentCycleStatus>({
    queryKey: ['agent-cycle-status'],
    queryFn: getAgentCycleStatus,
    refetchInterval: 15_000,
    retry: false,
  })

  const { mutate: runCycle, isPending: running } = useMutation({
    mutationFn: triggerAgentCycle,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['agent-cycle-status'] })
      qc.invalidateQueries({ queryKey: ['dashboard-summary'] })
    },
  })

  const graphAvailable = health?.management_graph ?? false
  const agentOnline = !!health

  const lastRanAt = status?.ran_at
    ? new Date(status.ran_at).toLocaleString('ko-KR')
    : '—'

  const decisionCount = status?.decisions?.length ?? 0
  const executedCount = status?.executed?.length ?? 0
  const nonTrivialDecisions = status?.decisions?.filter(
    (d) => d.action_type !== 'no_action'
  ) ?? []

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-5 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Brain className="w-4 h-4 text-violet-400" />
          <h3 className="text-sm font-medium text-slate-200">관리 에이전트</h3>
          <span
            className={`text-xs px-1.5 py-0.5 rounded-full font-medium ${
              agentOnline
                ? 'bg-emerald-500/20 text-emerald-400'
                : 'bg-slate-700 text-slate-500'
            }`}
          >
            {agentOnline ? '온라인' : '오프라인'}
          </span>
          {agentOnline && !graphAvailable && (
            <span className="text-xs text-amber-400">(LangGraph 미설치)</span>
          )}
        </div>
        <button
          onClick={() => runCycle()}
          disabled={running || !agentOnline}
          className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg
                     bg-violet-600 hover:bg-violet-500 disabled:bg-slate-700
                     text-white disabled:text-slate-500 transition-colors"
        >
          {running ? (
            <RefreshCw className="w-3 h-3 animate-spin" />
          ) : (
            <Zap className="w-3 h-3" />
          )}
          {running ? '실행 중…' : '수동 실행'}
        </button>
      </div>

      {/* Last cycle summary */}
      {statusLoading ? (
        <div className="text-xs text-slate-500 animate-pulse">상태 로딩 중…</div>
      ) : status && !('status' in status && status.status === 'no_cycle_run_yet') ? (
        <div className="space-y-3">
          {/* Stats row */}
          <div className="grid grid-cols-3 gap-3 text-center">
            <div className="bg-slate-900/60 rounded-lg p-2">
              <p className="text-xs text-slate-500">최종 실행</p>
              <p className="text-xs text-slate-300 font-medium mt-0.5">{lastRanAt}</p>
            </div>
            <div className="bg-slate-900/60 rounded-lg p-2">
              <p className="text-xs text-slate-500">결정 / 실행</p>
              <p className="text-sm font-bold text-slate-100 mt-0.5">
                {decisionCount} / {executedCount}
              </p>
            </div>
            <div className="bg-slate-900/60 rounded-lg p-2">
              <p className="text-xs text-slate-500">조치 건수</p>
              <p className={`text-sm font-bold mt-0.5 ${nonTrivialDecisions.length > 0 ? 'text-amber-400' : 'text-emerald-400'}`}>
                {nonTrivialDecisions.length}
              </p>
            </div>
          </div>

          {/* Report */}
          {status.final_report && (
            <div className="bg-slate-900/60 rounded-lg p-3">
              <p className="text-xs text-slate-400 mb-1">최종 보고서</p>
              <p className="text-xs text-slate-300 leading-relaxed">{status.final_report}</p>
            </div>
          )}

          {/* Non-trivial decisions */}
          {nonTrivialDecisions.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-xs text-slate-500">실행된 조치</p>
              {nonTrivialDecisions.map((d, i) => (
                <div key={i} className="flex items-start gap-2 bg-slate-900/60 rounded-lg px-3 py-2">
                  <span className="text-xs font-mono text-violet-400 shrink-0">{d.action_type}</span>
                  <span className="text-xs text-slate-400 line-clamp-1">{d.reasoning}</span>
                  <span className="text-xs text-slate-500 shrink-0 ml-auto">
                    {(d.confidence * 100).toFixed(0)}%
                  </span>
                </div>
              ))}
            </div>
          )}

          {/* Error */}
          {status.error && (
            <p className="text-xs text-red-400 bg-red-400/10 rounded-lg px-3 py-2">
              오류: {status.error}
            </p>
          )}
        </div>
      ) : (
        <p className="text-xs text-slate-500">아직 실행된 사이클이 없습니다. 수동 실행 버튼을 눌러 시작하세요.</p>
      )}
    </div>
  )
}

export default function MLOpsPage() {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-2">
        <Activity className="w-5 h-5 text-sky-400" />
        <h1 className="text-lg font-semibold text-slate-100">MLOps 모델 관리</h1>
      </div>

      {/* Model status cards */}
      <section>
        <h2 className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-3">
          Production 모델 상태
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {MODEL_INFO.map((info) => (
            <ModelCard key={info.key} info={info} />
          ))}
        </div>
      </section>

      {/* AI Agent panel */}
      <section>
        <h2 className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-3">
          AI 에이전트 (LangGraph)
        </h2>
        <AgentPanel />
      </section>

      {/* MLflow lifecycle */}
      <section>
        <h2 className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-3">
          모델 생명주기
        </h2>
        <div className="bg-slate-800 rounded-xl border border-slate-700 p-5">
          <div className="flex items-center gap-2 text-xs">
            <LifecycleStep label="None" done />
            <span className="text-slate-600 text-lg font-bold">→</span>
            <LifecycleStep label="Staging (Canary)" done />
            <span className="text-slate-600 text-lg font-bold">→</span>
            <LifecycleStep label="Production" active />
            <span className="text-slate-600 text-lg font-bold">→</span>
            <LifecycleStep label="Archived" />
          </div>
          <p className="text-xs text-slate-500 mt-3">
            훈련 → QualityGate 통과 → Staging(Canary) A/B 테스트 →
            canary_wins 시 Production 승격. PSI ≥ 0.20 시 AutoML이 긴급 재훈련 트리거.
          </p>
        </div>
      </section>

      {/* Drift PSI guide */}
      <section>
        <h2 className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-3">
          PSI 드리프트 기준
        </h2>
        <div className="bg-slate-800 rounded-xl border border-slate-700 p-5">
          <div className="grid grid-cols-3 gap-3 mb-4">
            {PSI_THRESHOLDS.map(({ label, range, color, bg }) => (
              <div key={label} className={`rounded-lg p-3 ${bg}`}>
                <p className={`text-sm font-semibold ${color}`}>{label}</p>
                <p className="text-xs text-slate-400 mt-0.5">{range}</p>
              </div>
            ))}
          </div>
          <p className="text-xs text-slate-500">
            PSI(Population Stability Index)는 참조(훈련) 분포와 현재(추론) 분포 간 이동을 측정합니다.
            AutoML 파이프라인이 6시간마다 모든 모델의 입력 특성 분포를 검사하며,
            PSI ≥ 0.20이면 샘플 임계값과 무관하게 즉시 재훈련이 트리거됩니다.
          </p>
        </div>
      </section>

      {/* A/B testing info */}
      <section>
        <h2 className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-3">
          A/B 테스트 (Canary 배포)
        </h2>
        <div className="bg-slate-800 rounded-xl border border-slate-700 p-5 space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
            <div className="space-y-2">
              <p className="text-slate-300 font-medium">라우팅 방식</p>
              <p className="text-slate-400">
                요청 해시 기반 결정적 라우팅 — 동일 요청은 항상 동일 모델로 라우팅됩니다.
                기본 canary 비율: 10%.
              </p>
            </div>
            <div className="space-y-2">
              <p className="text-slate-300 font-medium">API 사용 방법</p>
              <div className="bg-slate-900 rounded-lg p-3 font-mono text-slate-300 space-y-1">
                <p><span className="text-sky-400">POST</span> /v1/admin/models/promote-canary</p>
                <p><span className="text-emerald-400">POST</span> /v1/admin/models/graduate</p>
                <p><span className="text-red-400">POST</span> /v1/admin/models/rollback</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* AutoML schedule */}
      <section>
        <h2 className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-3">
          AutoML 재훈련 임계값
        </h2>
        <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-slate-400 border-b border-slate-700">
                <th className="text-left px-5 py-3 font-medium">모델</th>
                <th className="text-right px-5 py-3 font-medium">샘플 임계값</th>
                <th className="text-right px-5 py-3 font-medium">PSI 임계값</th>
                <th className="text-left px-5 py-3 font-medium">데이터 소스</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700/50">
              {[
                { model: 'WaterQualityPredictor', samples: '1,000 행', psi: '≥ 0.20', source: 'raw/sensor/' },
                { model: 'FeedingActivityClassifier', samples: '300 이미지', psi: '≥ 0.20', source: 'raw/labelled/feeding/' },
                { model: 'FishDetection', samples: '500 이미지', psi: '≥ 0.20', source: 'raw/labelled/growth/' },
              ].map((row) => (
                <tr key={row.model} className="hover:bg-slate-700/30 transition-colors">
                  <td className="px-5 py-3 font-mono text-xs text-slate-300">{row.model}</td>
                  <td className="px-5 py-3 text-right text-slate-200">{row.samples}</td>
                  <td className="px-5 py-3 text-right text-red-400">{row.psi}</td>
                  <td className="px-5 py-3 text-slate-400 font-mono text-xs">{row.source}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
