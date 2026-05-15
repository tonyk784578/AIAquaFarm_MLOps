import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import {
  Brain, ChevronRight, CircuitBoard, Cpu, Database, Radio, Sliders,
} from 'lucide-react'
import {
  getAgentCycleStatus, getAgentHealth,
  getFeedingModelStatus, getGrowthModelStatus, getWaterQualityModelStatus,
  listAlerts, listTanks,
} from '@/services/api'
import type { AgentCycleStatus, AgentHealth, ModelStatus, Tank } from '@/types'

// ── Status types ──────────────────────────────────────────────────────────────

type StageStatus = 'ok' | 'warn' | 'down' | 'idle'

interface StageProps {
  Icon: React.ElementType
  title: string
  subtitle: string
  metric: string
  metricLabel: string
  status: StageStatus
  to: string
}

const STATUS_COLOR: Record<StageStatus, string> = {
  ok:   'var(--ok)',
  warn: 'var(--warn)',
  down: 'var(--danger)',
  idle: 'var(--text-muted)',
}

const STATUS_LABEL: Record<StageStatus, string> = {
  ok: '정상', warn: '주의', down: '중단', idle: '대기',
}

// ── Single stage card ─────────────────────────────────────────────────────────

function Stage({ Icon, title, subtitle, metric, metricLabel, status, to }: StageProps) {
  const color = STATUS_COLOR[status]
  return (
    <Link
      to={to}
      className="flex-1 min-w-0 rounded-xl p-3 transition-all group"
      style={{
        backgroundColor: 'var(--bg-elevated)',
        border: '1px solid var(--bg-border)',
      }}
      onMouseEnter={(e) => {
        ;(e.currentTarget as HTMLElement).style.borderColor = color
        ;(e.currentTarget as HTMLElement).style.transform = 'translateY(-1px)'
      }}
      onMouseLeave={(e) => {
        ;(e.currentTarget as HTMLElement).style.borderColor = 'var(--bg-border)'
        ;(e.currentTarget as HTMLElement).style.transform = ''
      }}
    >
      <div className="flex items-center gap-1.5 mb-1.5">
        <div
          className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0"
          style={{ backgroundColor: `color-mix(in srgb, ${color} 14%, transparent)` }}
        >
          <Icon size={14} style={{ color }} />
        </div>
        <span
          className="w-1.5 h-1.5 rounded-full"
          style={{
            backgroundColor: color,
            animation: status === 'ok' ? 'pulse 2s ease-in-out infinite' : undefined,
          }}
          title={STATUS_LABEL[status]}
        />
      </div>
      <p
        className="text-xs font-semibold leading-tight"
        style={{ color: 'var(--text-primary)' }}
      >
        {title}
      </p>
      <p
        className="text-[11px] mt-0.5 leading-tight line-clamp-1"
        style={{ color: 'var(--text-muted)' }}
      >
        {subtitle}
      </p>
      <div className="mt-2 flex items-baseline gap-1">
        <span className="text-base font-bold tabular-nums" style={{ color }}>
          {metric}
        </span>
        <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
          {metricLabel}
        </span>
      </div>
    </Link>
  )
}

// ── Arrow between stages ──────────────────────────────────────────────────────

function FlowArrow() {
  return (
    <div
      className="hidden lg:flex items-center justify-center shrink-0"
      style={{ color: 'var(--text-muted)' }}
    >
      <ChevronRight size={16} />
    </div>
  )
}

// ── Panel ─────────────────────────────────────────────────────────────────────

interface SystemFlowPanelProps {
  activeAlertCount: number
}

export default function SystemFlowPanel({ activeAlertCount }: SystemFlowPanelProps) {
  const { data: tanks = [] } = useQuery<Tank[]>({
    queryKey: ['tanks'],
    queryFn: listTanks,
  })

  // AI model statuses
  const wq = useQuery<ModelStatus>({
    queryKey: ['model-status', 'water'],
    queryFn: getWaterQualityModelStatus,
    refetchInterval: 60_000,
  })
  const growth = useQuery<ModelStatus>({
    queryKey: ['model-status', 'growth'],
    queryFn: getGrowthModelStatus,
    refetchInterval: 60_000,
  })
  const feeding = useQuery<ModelStatus>({
    queryKey: ['model-status', 'feeding'],
    queryFn: getFeedingModelStatus,
    refetchInterval: 60_000,
  })

  // Agent
  const { data: agentHealth } = useQuery<AgentHealth>({
    queryKey: ['agent-health'],
    queryFn: getAgentHealth,
    refetchInterval: 30_000,
    retry: false,
  })
  const { data: cycleStatus } = useQuery<AgentCycleStatus>({
    queryKey: ['agent-cycle-status'],
    queryFn: getAgentCycleStatus,
    refetchInterval: 30_000,
    retry: false,
  })

  // Recent commands count (last 24h) — best-effort, use cycle executed count as proxy
  const { data: activeAlerts = [] } = useQuery({
    queryKey: ['alerts-flow'],
    queryFn: () => listAlerts({ active_only: true, limit: 100 }),
    refetchInterval: 30_000,
  })

  // ── Derived statuses ────────────────────────────────────────────────────────

  const onlineTanks = tanks.filter((t) => t.status === 'online').length
  const sensorStatus: StageStatus =
    tanks.length === 0 ? 'idle' : onlineTanks === tanks.length ? 'ok' : 'warn'

  // Backend is reachable if we successfully fetched tanks (this query implies /v1/dashboard/tanks 200)
  const backendStatus: StageStatus = tanks.length > 0 ? 'ok' : 'warn'

  const modelsLoaded =
    Number(wq.data?.is_loaded ?? 0) +
    Number(growth.data?.is_loaded ?? 0) +
    Number(feeding.data?.is_loaded ?? 0)
  const aiStatus: StageStatus =
    modelsLoaded === 3 ? 'ok' : modelsLoaded > 0 ? 'warn' : 'down'

  const agentStatus: StageStatus = !agentHealth
    ? 'down'
    : !agentHealth.management_graph
    ? 'warn'
    : 'ok'

  const criticalCount = activeAlerts.filter((a) => a.severity === 'critical').length
  const controlStatus: StageStatus =
    criticalCount > 0 ? 'warn' : activeAlertCount > 0 ? 'warn' : 'ok'

  const executedCount = cycleStatus?.executed?.length ?? 0

  return (
    <div
      className="rounded-2xl px-4 py-3.5"
      style={{
        backgroundColor: 'var(--bg-surface)',
        border: '1px solid var(--bg-border)',
        boxShadow: 'var(--shadow-sm)',
      }}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <CircuitBoard size={14} style={{ color: 'var(--teal-500)' }} />
          <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
            시스템 데이터 흐름
          </h3>
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
            엣지 센서가 수집한 데이터가 AI를 거쳐 자동 제어로 이어지는 5단계 파이프라인입니다.
          </span>
        </div>
      </div>

      <div className="flex flex-col lg:flex-row items-stretch gap-2">
        <Stage
          Icon={Radio}
          title="① 엣지 센서·카메라"
          subtitle="수질·영상 수집"
          metric={tanks.length > 0 ? `${onlineTanks}/${tanks.length}` : '—'}
          metricLabel="수조 온라인"
          status={sensorStatus}
          to="/water-quality"
        />
        <FlowArrow />
        <Stage
          Icon={Database}
          title="② 백엔드 API"
          subtitle="FastAPI · Timescale · Redis"
          metric={tanks.length > 0 ? '실시간' : '—'}
          metricLabel="WS 스트리밍"
          status={backendStatus}
          to="/dashboard"
        />
        <FlowArrow />
        <Stage
          Icon={Cpu}
          title="③ AI 추론 모델"
          subtitle="수질·성장·급이"
          metric={`${modelsLoaded}/3`}
          metricLabel="모델 로드됨"
          status={aiStatus}
          to="/mlops"
        />
        <FlowArrow />
        <Stage
          Icon={Brain}
          title="④ AI 에이전트"
          subtitle="LangGraph · Claude"
          metric={!agentHealth ? '오프라인' : `${executedCount}`}
          metricLabel={!agentHealth ? '' : '직전 사이클 조치'}
          status={agentStatus}
          to="/mlops"
        />
        <FlowArrow />
        <Stage
          Icon={Sliders}
          title="⑤ 제어·알림"
          subtitle="펌프·사료·산소"
          metric={String(activeAlertCount)}
          metricLabel="활성 알림"
          status={controlStatus}
          to="/control"
        />
      </div>
    </div>
  )
}
