// AI Agents page — runtime orchestration view (LangGraph workflows).
//
// Scope split from /mlops:
//   /mlops   — model assets: registry, lifecycle, drift, A/B, AutoML
//   /agents  — runtime: live cycle status, LangGraph topology, recent trace
//
// Reads from the agent service (FastAPI on :8001 via /agents proxy).

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertCircle, Brain, CheckCircle, Clock, Radio, RefreshCw, Zap,
} from 'lucide-react'

import { useEventSource } from '@/hooks/useEventSource'
import {
  agentEventStreamUrl,
  getAgentCycleStatus,
  getAgentHealth,
  getAgentHistory,
  triggerAgentCycle,
} from '@/services/api'
import type { AgentCycleStatus } from '@/types'
import { eventSummary } from '@/utils/format'
import AgentGraphVisualization from './AgentGraphVisualization'

const EVENT_KIND_COLORS: Record<string, string> = {
  cycle_started:          'var(--info)',
  cycle_completed:        'var(--ok)',
  node_started:           'var(--text-muted)',
  node_completed:         'var(--ok)',
  decision_made:          'var(--info)',
  command_executed:       'var(--ok)',
  command_failed:         'var(--danger)',
  optimization_started:   'var(--info)',
  optimization_completed: 'var(--ok)',
  error:                  'var(--danger)',
}

// ── Live SSE event stream ───────────────────────────────────────────────────

function AgentEventStream() {
  const { status, events, reconnectAttempts } = useEventSource(agentEventStreamUrl(), {
    bufferSize: 50,
    reconnectBaseDelay: 1_000,
  })

  const statusBadge = (() => {
    if (status === 'open') return { label: '실시간 연결', color: 'var(--ok)', bg: 'rgba(5,150,105,0.12)' }
    if (status === 'connecting') return { label: '연결 중…', color: 'var(--info)', bg: 'rgba(37,99,235,0.12)' }
    if (status === 'error')
      return {
        label: `재연결 (${reconnectAttempts})`,
        color: 'var(--warn)',
        bg: 'rgba(217,119,6,0.12)',
      }
    return { label: '연결 종료', color: 'var(--text-muted)', bg: 'var(--bg-elevated)' }
  })()

  return (
    <div className="card space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Radio
            size={14}
            style={{ color: statusBadge.color }}
            className={status === 'open' ? 'animate-pulse' : ''}
          />
          <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
            라이브 이벤트 (SSE)
          </h3>
          <span
            className="text-xs px-2 py-0.5 rounded-full font-semibold"
            style={{ backgroundColor: statusBadge.bg, color: statusBadge.color }}
          >
            {statusBadge.label}
          </span>
        </div>
        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
          {events.length} / 50
        </span>
      </div>

      <ul className="space-y-0 max-h-64 overflow-y-auto">
        {events.length === 0 && (
          <li className="text-xs py-3 text-center" style={{ color: 'var(--text-muted)' }}>
            {status === 'open' ? '이벤트 대기 중…' : '에이전트 서비스 연결을 확인하세요.'}
          </li>
        )}
        {[...events].reverse().map((ev, i) => {
          const color = EVENT_KIND_COLORS[ev.kind] || 'var(--text-muted)'
          const ts = new Date(ev.ts).toLocaleTimeString()
          const summary = eventSummary(ev)
          return (
            <li
              key={`${ev.ts}-${i}`}
              className="flex items-center gap-2 py-1.5 text-xs"
              style={{ borderBottom: '1px solid var(--bg-border)' }}
            >
              <span
                className="w-1.5 h-1.5 rounded-full shrink-0"
                style={{ backgroundColor: color }}
              />
              <span className="font-mono shrink-0" style={{ color }}>
                {ev.kind}
              </span>
              {ev.tank_id && (
                <span
                  className="font-mono text-xs px-1.5 py-0 rounded"
                  style={{ backgroundColor: 'var(--bg-elevated)', color: 'var(--text-secondary)' }}
                >
                  {ev.tank_id}
                </span>
              )}
              {summary && (
                <span className="line-clamp-1 flex-1" style={{ color: 'var(--text-secondary)' }}>
                  {summary}
                </span>
              )}
              <span className="ml-auto shrink-0" style={{ color: 'var(--text-muted)' }}>
                {ts}
              </span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

// ── Cycle history timeline ──────────────────────────────────────────────────

function AgentHistoryTimeline() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['agent-history'],
    queryFn: () => getAgentHistory(20),
    refetchInterval: 30_000,
    retry: false,
  })

  return (
    <div className="card space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Clock size={14} style={{ color: 'var(--text-muted)' }} />
          <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
            최근 사이클 이력
          </h3>
        </div>
        <button
          onClick={() => refetch()}
          className="p-1"
          style={{ color: 'var(--text-muted)' }}
        >
          <RefreshCw size={13} />
        </button>
      </div>

      {isLoading && (
        <p className="text-xs animate-pulse" style={{ color: 'var(--text-muted)' }}>
          이력 로딩중…
        </p>
      )}
      {isError && (
        <p className="text-xs flex items-center gap-1.5" style={{ color: 'var(--danger)' }}>
          <AlertCircle size={12} />이력 조회 실패 (Redis 미연결 가능성)
        </p>
      )}
      {data && data.items.length === 0 && (
        <p className="text-xs text-center py-3" style={{ color: 'var(--text-muted)' }}>
          아직 실행된 사이클이 없습니다
        </p>
      )}

      {data && data.items.length > 0 && (
        <ul className="space-y-2 max-h-80 overflow-y-auto">
          {data.items.map((item, idx) => {
            const decisionCount = Array.isArray(item.decisions) ? item.decisions.length : 0
            const execCount = Array.isArray(item.executed) ? item.executed.length : 0
            const nonTrivial = Array.isArray(item.decisions)
              ? item.decisions.filter((d) => d.action_type !== 'no_action').length
              : 0
            const ts = item.ran_at ? new Date(item.ran_at).toLocaleString() : '—'
            const hasError = Boolean(item.error)
            return (
              <li
                key={`${item.ran_at}-${idx}`}
                className="rounded-xl px-3 py-2.5 flex gap-3 items-start"
                style={{
                  backgroundColor: 'var(--bg-elevated)',
                  borderLeft: `3px solid ${hasError ? 'var(--danger)' : nonTrivial > 0 ? 'var(--warn)' : 'var(--ok)'}`,
                }}
              >
                <div className="flex-shrink-0 mt-0.5">
                  {hasError ? (
                    <AlertCircle size={14} style={{ color: 'var(--danger)' }} />
                  ) : (
                    <CheckCircle size={14} style={{ color: 'var(--ok)' }} />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs font-mono" style={{ color: 'var(--text-secondary)' }}>
                      결정 {decisionCount} · 실행 {execCount}
                    </span>
                    {nonTrivial > 0 && (
                      <span
                        className="text-xs px-1.5 py-0.5 rounded font-semibold"
                        style={{ backgroundColor: 'rgba(217,119,6,0.12)', color: 'var(--warn)' }}
                      >
                        조치 {nonTrivial}
                      </span>
                    )}
                    <span className="ml-auto text-xs" style={{ color: 'var(--text-muted)' }}>
                      {ts}
                    </span>
                  </div>
                  {item.final_report && (
                    <p
                      className="text-xs mt-1 line-clamp-2"
                      style={{ color: 'var(--text-secondary)' }}
                    >
                      {item.final_report}
                    </p>
                  )}
                  {hasError && (
                    <p className="text-xs mt-1" style={{ color: 'var(--danger)' }}>
                      {item.error}
                    </p>
                  )}
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

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
        <p className="section-title">라이브 이벤트 + 사이클 이력</p>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <AgentEventStream />
          <AgentHistoryTimeline />
        </div>
      </section>

      <section>
        <p className="section-title">그래프 토폴로지 · 운영 파이프라인</p>
        <AgentGraphVisualization />
      </section>
    </div>
  )
}
