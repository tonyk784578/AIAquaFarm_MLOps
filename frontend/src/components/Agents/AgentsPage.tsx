// AI Agents page — runtime orchestration view (LangGraph workflows).
//
// Scope split from /mlops:
//   /mlops   — model assets: registry, lifecycle, drift, A/B, AutoML
//   /agents  — runtime: live cycle status, LangGraph topology, recent trace
//
// Reads from the agent service (FastAPI on :8001 via /agents proxy).

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Brain, RefreshCw, Zap } from 'lucide-react'
import { getAgentCycleStatus, getAgentHealth, triggerAgentCycle } from '@/services/api'
import type { AgentCycleStatus } from '@/types'
import AgentGraphVisualization from './AgentGraphVisualization'

// ── Live status / manual-run panel ──────────────────────────────────────────

function AgentLiveStatus() {
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

  const agentOnline    = !!health
  const graphAvailable = health?.management_graph ?? false
  const lastRanAt      = status?.ran_at ? new Date(status.ran_at).toLocaleString('ko-KR') : '—'
  const decisionCount  = status?.decisions?.length ?? 0
  const executedCount  = status?.executed?.length  ?? 0
  const nonTrivial     = status?.decisions?.filter((d) => d.action_type !== 'no_action') ?? []

  return (
    <div className="card space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Brain size={15} style={{ color: '#8B5CF6' }} />
          <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
            관리 에이전트 상태
          </h3>
          <span
            className="text-xs px-2 py-0.5 rounded-full font-semibold"
            style={
              agentOnline
                ? { backgroundColor: 'rgba(5,150,105,0.1)', color: 'var(--ok)' }
                : { backgroundColor: 'var(--bg-elevated)',   color: 'var(--text-muted)' }
            }
          >
            {agentOnline ? '온라인' : '오프라인'}
          </span>
          {agentOnline && !graphAvailable && (
            <span className="text-xs" style={{ color: 'var(--warn)' }}>(LangGraph 미설치)</span>
          )}
        </div>
        <button
          onClick={() => runCycle()}
          disabled={running || !agentOnline}
          className="btn-primary flex items-center gap-1.5 text-xs"
          style={{ padding: '6px 12px' }}
        >
          {running ? <RefreshCw size={12} className="animate-spin" /> : <Zap size={12} />}
          {running ? '실행 중…' : '수동 실행'}
        </button>
      </div>

      {statusLoading ? (
        <p className="text-xs animate-pulse" style={{ color: 'var(--text-muted)' }}>상태 로딩 중…</p>
      ) : status && !('status' in status && status.status === 'no_cycle_run_yet') ? (
        <div className="space-y-3">
          <div className="grid grid-cols-3 gap-3 text-center">
            {[
              { label: '최종 실행',   value: lastRanAt,   big: false },
              { label: '결정 / 실행', value: `${decisionCount} / ${executedCount}`, big: true },
              { label: '조치 건수',   value: String(nonTrivial.length), big: true, highlight: nonTrivial.length > 0 },
            ].map(({ label, value, big, highlight }) => (
              <div key={label} className="rounded-xl p-3" style={{ backgroundColor: 'var(--bg-elevated)' }}>
                <p className="text-xs mb-0.5" style={{ color: 'var(--text-muted)' }}>{label}</p>
                <p
                  className={`${big ? 'text-sm font-bold' : 'text-xs font-medium'} mt-0.5`}
                  style={{ color: highlight ? 'var(--warn)' : big ? 'var(--text-primary)' : 'var(--text-secondary)' }}
                >
                  {value}
                </p>
              </div>
            ))}
          </div>

          {status.final_report && (
            <div className="rounded-xl p-3" style={{ backgroundColor: 'var(--bg-elevated)' }}>
              <p className="text-xs mb-1" style={{ color: 'var(--text-muted)' }}>최종 보고서</p>
              <p className="text-xs leading-relaxed" style={{ color: 'var(--text-secondary)' }}>{status.final_report}</p>
            </div>
          )}

          {nonTrivial.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-xs" style={{ color: 'var(--text-muted)' }}>실행된 조치</p>
              {nonTrivial.map((d, i) => (
                <div
                  key={i}
                  className="flex items-start gap-2 rounded-xl px-3 py-2"
                  style={{ backgroundColor: 'var(--bg-elevated)' }}
                >
                  <span className="text-xs font-mono font-semibold shrink-0" style={{ color: '#8B5CF6' }}>{d.action_type}</span>
                  <span className="text-xs line-clamp-1" style={{ color: 'var(--text-secondary)' }}>{d.reasoning}</span>
                  <span className="text-xs shrink-0 ml-auto" style={{ color: 'var(--text-muted)' }}>
                    {(d.confidence * 100).toFixed(0)}%
                  </span>
                </div>
              ))}
            </div>
          )}

          {status.error && (
            <p className="text-xs rounded-xl px-3 py-2" style={{ color: 'var(--danger)', backgroundColor: 'rgba(220,38,38,0.08)' }}>
              오류: {status.error}
            </p>
          )}
        </div>
      ) : (
        <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
          아직 실행된 사이클이 없습니다. 수동 실행 버튼을 눌러 시작하세요.
        </p>
      )}
    </div>
  )
}

// ── Page ────────────────────────────────────────────────────────────────────

export default function AgentsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="page-title flex items-center gap-2">
          <Brain size={18} style={{ color: '#8B5CF6' }} />
          AI 에이전트 (LangGraph)
        </h1>
        <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
          센서·카메라 데이터 → 의사결정 → 액추에이터까지 농장 1회 사이클을 LangGraph 그래프로 오케스트레이션합니다.
        </p>
      </div>

      <section>
        <p className="section-title">실시간 상태</p>
        <AgentLiveStatus />
      </section>

      <section>
        <p className="section-title">그래프 토폴로지 · 운영 파이프라인</p>
        <AgentGraphVisualization />
      </section>
    </div>
  )
}
