// Industry-grade LangGraph visualization for smart aquaculture operations.
//
// Three-lane SCADA-style diagram:
//   [데이터 소스] ──▶ [LangGraph 에이전트] ──▶ [물리 액추에이터 / 통보]
//
// The center column renders the actual compiled graph defined in
//   agents/management_agent/graph.py
//   agents/optimization_agent/graph.py
// Live water-quality / growth / feeding readings flow into collect_data,
// threshold rules sit beside analyse_situation, and the actions taken on
// the last cycle light up the corresponding actuator nodes on the right.

import { useQuery } from '@tanstack/react-query'
import {
  AlertTriangle, Camera, ChevronRight, Database, Droplet,
  Fish, GitBranch, Network, Sliders, UtensilsCrossed, Waves, Wind,
} from 'lucide-react'
import {
  getAgentCycleStatus, getDashboardSummary, getFeedingHistory,
} from '@/services/api'
import type {
  AgentCycleStatus, DashboardSummary, FeedingRecord,
} from '@/types'

// ── Geometry / palette ───────────────────────────────────────────────────────

const COLORS = {
  edge:         'var(--bg-border)',
  edgeActive:   '#8B5CF6',
  edgeDimmed:   'var(--bg-border)',
  nodeFill:     'var(--bg-surface)',
  nodeBorder:   'var(--bg-border)',
  visitedFill:  'rgba(139, 92, 246, 0.10)',
  visitedBorder:'#8B5CF6',
  errorBorder:  'var(--danger)',
  ok:           'var(--ok)',
  warn:         'var(--warn)',
  danger:       'var(--danger)',
  info:         'var(--info)',
  text:         'var(--text-primary)',
  textMuted:    'var(--text-muted)',
  textSec:      'var(--text-secondary)',
  llmAccent:    '#8B5CF6',
  bgElev:       'var(--bg-elevated)',
  // Per-stream accent colours
  streamWQ:     '#0EA5E9', // sky
  streamGrowth: '#10B981', // emerald
  streamFeed:   '#F59E0B', // amber
}

const NODE_W = 168
const NODE_H = 48
const SRC_W = 232
const SRC_H = 96
const ACT_W = 196
const ACT_H = 56

// ── Domain thresholds (kept in sync with backend/app/config.py defaults) ─────

const THRESHOLDS = {
  ammoniaWarn: 0.5,  ammoniaCrit: 1.0,
  nitriteWarn: 0.1,  nitriteCrit: 0.2,
  doWarn: 6.0,       doCrit: 5.0,
  phMin: 6.5,        phMax: 8.5,
}

type MetricLevel = 'ok' | 'warn' | 'crit' | 'idle'

function levelForAmmonia(v: number | null | undefined): MetricLevel {
  if (v == null) return 'idle'
  if (v >= THRESHOLDS.ammoniaCrit) return 'crit'
  if (v >= THRESHOLDS.ammoniaWarn) return 'warn'
  return 'ok'
}
function levelForNitrite(v: number | null | undefined): MetricLevel {
  if (v == null) return 'idle'
  if (v >= THRESHOLDS.nitriteCrit) return 'crit'
  if (v >= THRESHOLDS.nitriteWarn) return 'warn'
  return 'ok'
}
function levelForDO(v: number | null | undefined): MetricLevel {
  if (v == null) return 'idle'
  if (v <= THRESHOLDS.doCrit) return 'crit'
  if (v <= THRESHOLDS.doWarn) return 'warn'
  return 'ok'
}
function levelForPh(v: number | null | undefined): MetricLevel {
  if (v == null) return 'idle'
  if (v < THRESHOLDS.phMin || v > THRESHOLDS.phMax) return 'warn'
  return 'ok'
}

const LEVEL_COLOR: Record<MetricLevel, string> = {
  ok: COLORS.ok, warn: COLORS.warn, crit: COLORS.danger, idle: COLORS.textMuted,
}

function fmt(v: number | null | undefined, digits = 2, suffix = ''): string {
  if (v == null || Number.isNaN(v)) return '—'
  return `${v.toFixed(digits)}${suffix}`
}

// ── Arrow marker defs ────────────────────────────────────────────────────────

function ArrowDefs() {
  return (
    <defs>
      <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
        <path d="M0,0 L10,5 L0,10 z" fill={COLORS.edge} />
      </marker>
      <marker id="arrow-active" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
        <path d="M0,0 L10,5 L0,10 z" fill={COLORS.edgeActive} />
      </marker>
      <marker id="arrow-dim" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
        <path d="M0,0 L10,5 L0,10 z" fill={COLORS.edgeDimmed} opacity={0.5} />
      </marker>
      <marker id="arrow-wq" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
        <path d="M0,0 L10,5 L0,10 z" fill={COLORS.streamWQ} />
      </marker>
      <marker id="arrow-growth" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
        <path d="M0,0 L10,5 L0,10 z" fill={COLORS.streamGrowth} />
      </marker>
      <marker id="arrow-feed" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
        <path d="M0,0 L10,5 L0,10 z" fill={COLORS.streamFeed} />
      </marker>
    </defs>
  )
}

// ── Generic node renderers ──────────────────────────────────────────────────

interface AgentNodeProps {
  cx: number
  cy: number
  label: string
  sub: string
  visited: boolean
  errored?: boolean
  isLlm?: boolean
}

function AgentNode({ cx, cy, label, sub, visited, errored, isLlm }: AgentNodeProps) {
  const border = errored
    ? COLORS.errorBorder
    : visited
    ? COLORS.visitedBorder
    : COLORS.nodeBorder
  const fill = visited ? COLORS.visitedFill : COLORS.nodeFill
  return (
    <g>
      <rect
        x={cx - NODE_W / 2} y={cy - NODE_H / 2}
        width={NODE_W} height={NODE_H} rx={10} ry={10}
        fill={fill} stroke={border} strokeWidth={visited ? 1.5 : 1}
      />
      {isLlm && (
        <g>
          <circle cx={cx + NODE_W / 2 - 9} cy={cy - NODE_H / 2 + 9} r={3.5} fill={COLORS.llmAccent} />
          <text
            x={cx + NODE_W / 2 - 16} y={cy - NODE_H / 2 + 12}
            textAnchor="end" fontSize={8.5} fontWeight={700} fill={COLORS.llmAccent}
          >
            LLM
          </text>
        </g>
      )}
      <text
        x={cx} y={cy - 6} textAnchor="middle" dominantBaseline="middle"
        fontSize={12} fontWeight={700}
        fontFamily="ui-monospace, SFMono-Regular, monospace"
        fill={COLORS.text}
      >
        {label}
      </text>
      <text
        x={cx} y={cy + 9} textAnchor="middle" dominantBaseline="middle"
        fontSize={10} fill={COLORS.textMuted}
      >
        {sub}
      </text>
    </g>
  )
}

function Terminal({ cx, cy, label, kind, visited }: {
  cx: number; cy: number; label: string;
  kind: 'start' | 'end'; visited: boolean
}) {
  const stroke = visited
    ? (kind === 'start' ? COLORS.ok : COLORS.visitedBorder)
    : COLORS.textMuted
  const fill = visited
    ? (kind === 'start' ? 'rgba(5,150,105,0.15)' : 'rgba(139,92,246,0.10)')
    : 'rgba(148,163,184,0.10)'
  return (
    <g>
      <ellipse cx={cx} cy={cy} rx={26} ry={15} fill={fill} stroke={stroke} strokeWidth={1.5} />
      <text x={cx} y={cy + 1} textAnchor="middle" dominantBaseline="middle"
        fontSize={10} fontWeight={700} fill={stroke}>
        {label}
      </text>
    </g>
  )
}

// ── Path drawing ─────────────────────────────────────────────────────────────

interface EdgeOpts {
  marker?: 'default' | 'active' | 'dim' | 'wq' | 'growth' | 'feed'
  dashed?: boolean
  width?: number
  opacity?: number
}

function polylinePath(points: [number, number][], opts: EdgeOpts = {}, key?: string | number) {
  const markerId = (
    opts.marker === 'active' ? 'arrow-active' :
    opts.marker === 'dim'    ? 'arrow-dim' :
    opts.marker === 'wq'     ? 'arrow-wq' :
    opts.marker === 'growth' ? 'arrow-growth' :
    opts.marker === 'feed'   ? 'arrow-feed' :
    'arrow'
  )
  const stroke = (
    opts.marker === 'active' ? COLORS.edgeActive :
    opts.marker === 'dim'    ? COLORS.edgeDimmed :
    opts.marker === 'wq'     ? COLORS.streamWQ :
    opts.marker === 'growth' ? COLORS.streamGrowth :
    opts.marker === 'feed'   ? COLORS.streamFeed :
    COLORS.edge
  )
  const pts = points.map(([x, y]) => `${x},${y}`).join(' ')
  return (
    <polyline
      key={key}
      points={pts}
      fill="none"
      stroke={stroke}
      strokeWidth={opts.width ?? 1.6}
      strokeDasharray={opts.dashed ? '3 3' : undefined}
      opacity={opts.opacity ?? (opts.marker === 'dim' ? 0.5 : 1)}
      markerEnd={`url(#${markerId})`}
    />
  )
}

// ── Source-card renderer ────────────────────────────────────────────────────

interface SourceCardProps {
  x: number; y: number
  Icon: React.ElementType
  title: string
  subtitle: string
  accent: string
  rows: { label: string; value: string; level?: MetricLevel }[]
}

function SourceCard({ x, y, Icon, title, subtitle, accent, rows }: SourceCardProps) {
  // SVG <foreignObject> hosts a small HTML card. We render text inside SVG
  // instead, to keep print/PDF export friendly.
  return (
    <g>
      <rect
        x={x} y={y} width={SRC_W} height={SRC_H} rx={10} ry={10}
        fill={COLORS.bgElev} stroke={COLORS.nodeBorder} strokeWidth={1}
      />
      <rect x={x} y={y} width={3} height={SRC_H} rx={1.5} fill={accent} />
      <foreignObject x={x + 11} y={y + 9} width={SRC_W - 14} height={26}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <Icon size={14} color={accent} />
          <span style={{
            fontSize: 12, fontWeight: 700, color: COLORS.text,
          }}>{title}</span>
          <span style={{ fontSize: 10, color: COLORS.textMuted, marginLeft: 'auto' }}>
            {subtitle}
          </span>
        </div>
      </foreignObject>
      {rows.map((r, i) => {
        const yRow = y + 39 + i * 17
        const dotColor = LEVEL_COLOR[r.level ?? 'idle']
        return (
          <g key={i}>
            <circle cx={x + 14} cy={yRow + 5} r={3} fill={dotColor} />
            <text
              x={x + 24} y={yRow + 8}
              fontSize={10.5} fill={COLORS.textSec}
            >
              {r.label}
            </text>
            <text
              x={x + SRC_W - 12} y={yRow + 8}
              textAnchor="end"
              fontSize={11} fontWeight={600}
              fontFamily="ui-monospace, SFMono-Regular, monospace"
              fill={r.level === 'crit' ? COLORS.danger : r.level === 'warn' ? COLORS.warn : COLORS.text}
            >
              {r.value}
            </text>
          </g>
        )
      })}
    </g>
  )
}

// ── Actuator-card renderer ──────────────────────────────────────────────────

interface ActuatorCardProps {
  x: number; y: number
  Icon: React.ElementType
  title: string
  channel: string
  triggered: boolean
  detail?: string
}

function ActuatorCard({ x, y, Icon, title, channel, triggered, detail }: ActuatorCardProps) {
  const accent = triggered ? COLORS.warn : COLORS.textMuted
  const border = triggered ? COLORS.warn : COLORS.nodeBorder
  const fill = triggered ? 'rgba(217,119,6,0.10)' : COLORS.nodeFill
  return (
    <g>
      <rect
        x={x} y={y} width={ACT_W} height={ACT_H} rx={10} ry={10}
        fill={fill} stroke={border} strokeWidth={triggered ? 1.5 : 1}
      />
      <foreignObject x={x + 10} y={y + 7} width={ACT_W - 14} height={20}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <Icon size={13} color={accent} />
          <span style={{ fontSize: 11.5, fontWeight: 700, color: COLORS.text }}>{title}</span>
          {triggered && (
            <span style={{
              fontSize: 9, fontWeight: 700, color: COLORS.warn,
              marginLeft: 'auto', textTransform: 'uppercase',
            }}>● 활성</span>
          )}
        </div>
      </foreignObject>
      <text
        x={x + 30} y={y + 36}
        fontSize={9.5}
        fontFamily="ui-monospace, SFMono-Regular, monospace"
        fill={COLORS.textMuted}
      >
        {channel}
      </text>
      {detail && (
        <text
          x={x + 30} y={y + 49}
          fontSize={9.5} fill={COLORS.warn}
        >
          {detail}
        </text>
      )}
    </g>
  )
}

// ── Rule pill (decision threshold beside analyse_situation) ─────────────────

function RulePill({ x, y, w, level, label }: {
  x: number; y: number; w: number; level: MetricLevel; label: string
}) {
  const color = LEVEL_COLOR[level]
  return (
    <g>
      <rect x={x} y={y} width={w} height={18} rx={4} fill={`color-mix(in srgb, ${color} 12%, transparent)`} stroke={color} strokeWidth={0.8} />
      <text x={x + 7} y={y + 12} fontSize={10}
        fontFamily="ui-monospace, SFMono-Regular, monospace"
        fill={color} fontWeight={600}>
        {label}
      </text>
    </g>
  )
}

// ── Optimization subgraph ────────────────────────────────────────────────────

function OptimizationSubgraph({ visited }: { visited: boolean }) {
  // Wider viewBox so the 4 task nodes (168px each) keep a clear ~22px gap.
  //   START(35) ── gather(160) ── generate(350) ── simulate(540) ── select(730) ── END(920)
  // Node rectangle spans cx ± 84; arrows draw from one edge to ~2px before next so
  // the markerEnd arrowhead lands cleanly inside the gap.
  const yNode = 80
  const HALF = NODE_W / 2 // 84
  const nodes = [
    { x: 35,  label: 'START',                kind: 'start' as const },
    { x: 160, label: 'gather_outputs',       sub: 'AI 결과 수집' },
    { x: 350, label: 'generate_candidates',  sub: 'Claude 후보 제안', isLlm: true },
    { x: 540, label: 'simulate_in_twin',     sub: '디지털 트윈 ODE' },
    { x: 730, label: 'select_optimal',       sub: '최고 점수 선택' },
    { x: 920, label: 'END',                  kind: 'end' as const },
  ]
  const edges: [number, number][][] = [
    [[65,             yNode], [160 - HALF - 2, yNode]],
    [[160 + HALF,     yNode], [350 - HALF - 2, yNode]],
    [[350 + HALF,     yNode], [540 - HALF - 2, yNode]],
    [[540 + HALF,     yNode], [730 - HALF - 2, yNode]],
    [[730 + HALF,     yNode], [890,            yNode]],
  ]
  return (
    <svg viewBox="0 0 980 160" preserveAspectRatio="xMidYMid meet"
      className="w-full h-auto" style={{ minWidth: 820 }}
      role="img" aria-label="Optimization agent subgraph">
      <ArrowDefs />
      {edges.map((pts, i) => polylinePath(pts, { marker: visited ? 'active' : 'default' }, `opt-edge-${i}`))}
      {nodes.map((n, i) => (
        n.kind ? (
          <Terminal key={i} cx={n.x} cy={yNode} label={n.label} kind={n.kind} visited={visited} />
        ) : (
          <AgentNode key={i} cx={n.x} cy={yNode} label={n.label} sub={n.sub ?? ''} visited={visited} isLlm={n.isLlm} />
        )
      ))}
    </svg>
  )
}

// ── Action-to-actuator mapping ──────────────────────────────────────────────

type ActuatorId = 'feeder' | 'pump' | 'aeration' | 'exchange' | 'alert'

function actionToActuator(action: string): ActuatorId | null {
  switch (action) {
    case 'stop_feeding':
    case 'reduce_feeding': return 'feeder'
    case 'increase_aeration': return 'aeration'
    case 'water_exchange': return 'exchange'
    case 'create_alert': return 'alert'
    default: return null
  }
}

function actionLabel(action: string): string {
  return ({
    stop_feeding: '사료 중단',
    reduce_feeding: '사료 감량',
    increase_aeration: '산소 증가',
    water_exchange: '환수 실행',
    create_alert: '알림 생성',
    no_action: '조치 없음',
  } as Record<string, string>)[action] ?? action
}

// ── Main component ─────────────────────────────────────────────────────────

export default function AgentGraphVisualization() {
  const { data: cycleStatus } = useQuery<AgentCycleStatus>({
    queryKey: ['agent-cycle-status'],
    queryFn: getAgentCycleStatus,
    refetchInterval: 15_000,
    retry: false,
  })
  const { data: summary } = useQuery<DashboardSummary>({
    queryKey: ['dashboard-summary'],
    queryFn: getDashboardSummary,
    refetchInterval: 10_000,
  })
  const { data: feedingHistory } = useQuery<FeedingRecord[]>({
    queryKey: ['feeding-latest', 'graph'],
    queryFn: () => getFeedingHistory(undefined, 1),
    refetchInterval: 30_000,
  })

  // ── Derived state ─────────────────────────────────────────────────────────
  const ran = !!cycleStatus?.ran_at && cycleStatus.status !== 'no_cycle_run_yet'
  const errored = !!cycleStatus?.error
  const executedAny = (cycleStatus?.executed?.length ?? 0) > 0
  const nonTrivialDecisions = (cycleStatus?.decisions ?? []).filter((d) => d.action_type !== 'no_action')
  const branchTaken: 'execute' | 'report' =
    executedAny || nonTrivialDecisions.length > 0 ? 'execute' : 'report'

  const wq = summary?.water_quality
  const growth = summary?.fish_growth
  const feeding = feedingHistory?.[0]

  const wqLevels = {
    ammonia: levelForAmmonia(wq?.ammonia_ppm),
    nitrite: levelForNitrite(wq?.nitrite_ppm),
    do:      levelForDO(wq?.dissolved_oxygen_mgl),
    ph:      levelForPh(wq?.ph),
  }
  const worstWqLevel: MetricLevel =
    ([wqLevels.ammonia, wqLevels.nitrite, wqLevels.do, wqLevels.ph] as MetricLevel[])
      .reduce<MetricLevel>((acc, cur) => {
        const rank = { ok: 0, idle: 0, warn: 1, crit: 2 } as const
        return rank[cur] > rank[acc] ? cur : acc
      }, 'ok')

  // Map executed decisions to triggered actuators
  const triggeredActuators = new Set<ActuatorId>()
  const actuatorDetails: Record<ActuatorId, string> = {
    feeder: '', pump: '', aeration: '', exchange: '', alert: '',
  }
  for (const dec of cycleStatus?.decisions ?? []) {
    const act = actionToActuator(dec.action_type)
    if (act) {
      triggeredActuators.add(act)
      if (!actuatorDetails[act]) {
        actuatorDetails[act] = `${dec.tank_id}: ${actionLabel(dec.action_type)} (${(dec.confidence * 100).toFixed(0)}%)`
      }
    }
  }

  // ── Main SVG layout (3 lanes) ────────────────────────────────────────────
  // Lanes:
  //   sources: x 14..246 (centers ~130)
  //   agent:   x 322..724 (centers 523)
  //   actuator:x 800..996 (centers 898)

  const SOURCE_X = 14
  const AGENT_CX = 523
  const ACT_X = 800

  // Source card vertical positions
  const SRC_Y = { wq: 70, growth: 200, feeding: 330 } as const

  // Center agent nodes
  const AG_Y = {
    start: 30, collect: 90, analyse: 220,
    execute: 380, report: 500, end: 560,
  } as const

  // Actuator card vertical positions (5 cards)
  const ACT_Y = { feeder: 50, pump: 130, aeration: 210, exchange: 290, alert: 370 } as const

  // Build the agent edges
  const edgeCollectAnalyse: [number, number][] =
    [[AGENT_CX, AG_Y.collect + NODE_H / 2], [AGENT_CX, AG_Y.analyse - NODE_H / 2]]
  const edgeAnalyseExecute: [number, number][] =
    [[AGENT_CX, AG_Y.analyse + NODE_H / 2], [AGENT_CX, AG_Y.execute - NODE_H / 2]]
  const edgeAnalyseReportSkip: [number, number][] = [
    [AGENT_CX - NODE_W / 2, AG_Y.analyse],
    [AGENT_CX - NODE_W / 2 - 26, AG_Y.analyse],
    [AGENT_CX - NODE_W / 2 - 26, AG_Y.report],
    [AGENT_CX - NODE_W / 2, AG_Y.report],
  ]
  const edgeExecuteReport: [number, number][] =
    [[AGENT_CX, AG_Y.execute + NODE_H / 2], [AGENT_CX, AG_Y.report - NODE_H / 2]]
  const edgeStartCollect: [number, number][] =
    [[AGENT_CX, AG_Y.start + 15], [AGENT_CX, AG_Y.collect - NODE_H / 2]]
  const edgeReportEnd: [number, number][] =
    [[AGENT_CX, AG_Y.report + NODE_H / 2], [AGENT_CX, AG_Y.end - 15]]

  return (
    <div className="card space-y-6">
      <header className="flex items-start justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2">
          <Network size={15} style={{ color: COLORS.llmAccent }} />
          <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
            LangGraph 운영 파이프라인
          </h3>
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
            · 센서/카메라 → 의사결정 → 액추에이터까지 1회 사이클 전체 흐름
          </span>
        </div>
        <div className="flex items-center gap-3 text-[10px]" style={{ color: 'var(--text-muted)' }}>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: COLORS.streamWQ }} />
            수질
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: COLORS.streamGrowth }} />
            성장
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: COLORS.streamFeed }} />
            급이
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: COLORS.visitedBorder }} />
            실행 경로
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: COLORS.warn }} />
            액추에이터 활성
          </span>
        </div>
      </header>

      {/* ── Main 3-lane SCADA diagram ─────────────────────────────────── */}
      <div className="rounded-xl p-3 overflow-x-auto" style={{ backgroundColor: 'var(--bg-elevated)' }}>
        <svg
          viewBox="0 0 1010 640"
          preserveAspectRatio="xMidYMid meet"
          className="w-full h-auto"
          style={{ minWidth: 920 }}
          role="img"
          aria-label="LangGraph aquaculture pipeline"
        >
          <ArrowDefs />

          {/* Lane backgrounds */}
          <rect x={0}   y={0} width={260} height={640} fill="rgba(14,165,233,0.03)" />
          <rect x={300} y={0} width={460} height={640} fill="rgba(139,92,246,0.04)" />
          <rect x={780} y={0} width={230} height={640} fill="rgba(217,119,6,0.03)" />

          {/* Lane headers */}
          <text x={130} y={22} textAnchor="middle" fontSize={11} fontWeight={700}
            fill={COLORS.textMuted} letterSpacing={1.5}>
            데이터 소스
          </text>
          <text x={AGENT_CX} y={22} textAnchor="middle" fontSize={11} fontWeight={700}
            fill={COLORS.textMuted} letterSpacing={1.5}>
            LANGGRAPH 에이전트 (관리 그래프)
          </text>
          <text x={898} y={22} textAnchor="middle" fontSize={11} fontWeight={700}
            fill={COLORS.textMuted} letterSpacing={1.5}>
            물리 액추에이터 · 통보
          </text>

          {/* ── Source cards ── */}
          <SourceCard
            x={SOURCE_X} y={SRC_Y.wq} Icon={Droplet} accent={COLORS.streamWQ}
            title="수질 센서"
            subtitle={wq?.tank_id ?? '대기'}
            rows={[
              { label: 'NH₃ (ppm)', value: fmt(wq?.ammonia_ppm, 3),  level: wqLevels.ammonia },
              { label: 'NO₂ (ppm)', value: fmt(wq?.nitrite_ppm, 3),  level: wqLevels.nitrite },
              { label: 'DO (mg/L)', value: fmt(wq?.dissolved_oxygen_mgl, 2), level: wqLevels.do },
              { label: 'pH',        value: fmt(wq?.ph, 2),            level: wqLevels.ph },
            ]}
          />
          <SourceCard
            x={SOURCE_X} y={SRC_Y.growth} Icon={Fish} accent={COLORS.streamGrowth}
            title="성장 카메라"
            subtitle="YOLOv8"
            rows={[
              { label: '개체수',       value: growth?.fish_count != null ? `${growth.fish_count.toLocaleString()} 마리` : '—' },
              { label: '평균 길이',    value: fmt(growth?.avg_length_cm, 1, ' cm') },
              { label: '평균 체중',    value: fmt(growth?.avg_weight_g, 0, ' g') },
              { label: '바이오매스',   value: fmt(growth?.biomass_kg, 1, ' kg') },
            ]}
          />
          <SourceCard
            x={SOURCE_X} y={SRC_Y.feeding} Icon={Camera} accent={COLORS.streamFeed}
            title="급이 카메라"
            subtitle="ResNet18"
            rows={[
              { label: '활성도',      value: fmt(feeding?.activity_score, 2) },
              { label: '권장 급이량', value: fmt(feeding?.recommended_amount_kg, 2, ' kg') },
              { label: 'FCR',         value: '—' },
              { label: '잔여 사료',   value: fmt(feeding?.feed_waste_estimate_pct, 0, '%') },
            ]}
          />

          {/* ── Source → collect_data edges ── */}
          {polylinePath([
            [SOURCE_X + SRC_W, SRC_Y.wq + SRC_H / 2],
            [310, SRC_Y.wq + SRC_H / 2],
            [310, AG_Y.collect],
            [AGENT_CX - NODE_W / 2, AG_Y.collect],
          ], { marker: 'wq' })}
          {polylinePath([
            [SOURCE_X + SRC_W, SRC_Y.growth + SRC_H / 2],
            [310, SRC_Y.growth + SRC_H / 2],
            [310, AG_Y.collect],
            [AGENT_CX - NODE_W / 2, AG_Y.collect],
          ], { marker: 'growth' })}
          {polylinePath([
            [SOURCE_X + SRC_W, SRC_Y.feeding + SRC_H / 2],
            [310, SRC_Y.feeding + SRC_H / 2],
            [310, AG_Y.collect],
            [AGENT_CX - NODE_W / 2, AG_Y.collect],
          ], { marker: 'feed' })}

          {/* ── Agent nodes + internal edges ── */}
          {polylinePath(edgeStartCollect, { marker: ran ? 'active' : 'default' })}
          {polylinePath(edgeCollectAnalyse, { marker: ran ? 'active' : 'default' })}
          {polylinePath(edgeAnalyseExecute, {
            marker: branchTaken === 'execute' && ran ? 'active' : 'dim',
            dashed: branchTaken !== 'execute',
          })}
          {polylinePath(edgeAnalyseReportSkip, {
            marker: branchTaken === 'report' && ran ? 'active' : 'dim',
            dashed: branchTaken !== 'report',
          })}
          {polylinePath(edgeExecuteReport, { marker: ran && branchTaken === 'execute' ? 'active' : 'default' })}
          {polylinePath(edgeReportEnd, { marker: ran && cycleStatus?.final_report ? 'active' : 'default' })}

          <Terminal cx={AGENT_CX} cy={AG_Y.start} label="START" kind="start" visited={ran} />
          <AgentNode cx={AGENT_CX} cy={AG_Y.collect} label="collect_data"
            sub="GET /v1/dashboard/summary" visited={ran} />
          <AgentNode cx={AGENT_CX} cy={AG_Y.analyse} label="analyse_situation"
            sub="Claude 4.6 + opt-subgraph" visited={ran} isLlm
            errored={errored && !executedAny} />
          <AgentNode cx={AGENT_CX} cy={AG_Y.execute} label="execute_commands"
            sub={`POST /v1/control/*${executedAny ? ` (${cycleStatus?.executed.length})` : ''}`}
            visited={executedAny} errored={errored && executedAny} />
          <AgentNode cx={AGENT_CX} cy={AG_Y.report} label="generate_report"
            sub="보고서 → /status" visited={ran && !!cycleStatus?.final_report} />
          <Terminal cx={AGENT_CX} cy={AG_Y.end} label="END" kind="end"
            visited={ran && !!cycleStatus?.final_report} />

          {/* Branch labels */}
          <text x={AGENT_CX + 8} y={(AG_Y.analyse + AG_Y.execute) / 2}
            fontSize={9.5} fontWeight={700}
            fill={branchTaken === 'execute' ? COLORS.edgeActive : COLORS.textMuted}>
            needs_action
          </text>
          <text x={AGENT_CX - NODE_W / 2 - 22} y={(AG_Y.analyse + AG_Y.report) / 2}
            fontSize={9.5} fontWeight={700} textAnchor="end"
            fill={branchTaken === 'report' ? COLORS.edgeActive : COLORS.textMuted}>
            no_action
          </text>

          {/* ── Decision rules pinned beside analyse_situation ── */}
          <g>
            <rect
              x={AGENT_CX + NODE_W / 2 + 16}
              y={AG_Y.analyse - 64}
              width={134} height={130} rx={8}
              fill={COLORS.bgElev}
              stroke={LEVEL_COLOR[worstWqLevel]}
              strokeWidth={worstWqLevel === 'ok' ? 0.6 : 1.4}
              strokeDasharray={worstWqLevel === 'ok' ? '2 2' : undefined}
            />
            <text x={AGENT_CX + NODE_W / 2 + 24} y={AG_Y.analyse - 48}
              fontSize={9.5} fontWeight={700} fill={COLORS.textMuted}
              letterSpacing={0.6}>
              결정 규칙 (임계값)
            </text>
            <RulePill x={AGENT_CX + NODE_W / 2 + 24} y={AG_Y.analyse - 38} w={118}
              level={wqLevels.ammonia} label={`NH₃ ≥ 0.5 → 감량`} />
            <RulePill x={AGENT_CX + NODE_W / 2 + 24} y={AG_Y.analyse - 18} w={118}
              level={wqLevels.nitrite} label={`NO₂ ≥ 0.1 → 환수`} />
            <RulePill x={AGENT_CX + NODE_W / 2 + 24} y={AG_Y.analyse + 2} w={118}
              level={wqLevels.do} label={`DO ≤ 6.0 → 산소↑`} />
            <RulePill x={AGENT_CX + NODE_W / 2 + 24} y={AG_Y.analyse + 22} w={118}
              level={wqLevels.ph} label={`pH 6.5–8.5 유지`} />
            <RulePill x={AGENT_CX + NODE_W / 2 + 24} y={AG_Y.analyse + 42} w={118}
              level={wqLevels.ammonia === 'crit' ? 'crit' : 'ok'} label={`NH₃ ≥ 1.0 → 중단`} />
          </g>

          {/* ── execute_commands → actuator edges ── */}
          {(['feeder', 'pump', 'aeration', 'exchange', 'alert'] as ActuatorId[]).map((id) => {
            const targetY = ACT_Y[id]
            const triggered = triggeredActuators.has(id)
            return polylinePath([
              [AGENT_CX + NODE_W / 2, AG_Y.execute],
              [770, AG_Y.execute],
              [770, targetY + ACT_H / 2],
              [ACT_X, targetY + ACT_H / 2],
            ], {
              marker: triggered ? 'active' : 'dim',
              dashed: !triggered,
              opacity: triggered ? 1 : 0.4,
            }, `act-edge-${id}`)
          })}

          {/* ── Actuator cards ── */}
          <ActuatorCard x={ACT_X} y={ACT_Y.feeder}   Icon={UtensilsCrossed}
            title="사료 공급기" channel="cmd:{tank}:feeder"
            triggered={triggeredActuators.has('feeder')}   detail={actuatorDetails.feeder || undefined} />
          <ActuatorCard x={ACT_X} y={ACT_Y.pump}     Icon={Waves}
            title="순환 펌프"    channel="cmd:{tank}:pump"
            triggered={triggeredActuators.has('pump')}     detail={actuatorDetails.pump || undefined} />
          <ActuatorCard x={ACT_X} y={ACT_Y.aeration} Icon={Wind}
            title="산소 공급기"  channel="cmd:{tank}:aeration"
            triggered={triggeredActuators.has('aeration')} detail={actuatorDetails.aeration || undefined} />
          <ActuatorCard x={ACT_X} y={ACT_Y.exchange} Icon={Sliders}
            title="환수 밸브"    channel="cmd:{tank}:exchange"
            triggered={triggeredActuators.has('exchange')} detail={actuatorDetails.exchange || undefined} />
          <ActuatorCard x={ACT_X} y={ACT_Y.alert}    Icon={AlertTriangle}
            title="알림 시스템"  channel="events:alerts"
            triggered={triggeredActuators.has('alert') || (summary?.active_alert_count ?? 0) > 0}
            detail={
              actuatorDetails.alert ||
              ((summary?.active_alert_count ?? 0) > 0 ? `활성 알림 ${summary?.active_alert_count}건` : undefined)
            } />

          {/* report → external sinks */}
          {polylinePath([
            [AGENT_CX + NODE_W / 2, AG_Y.report],
            [870, AG_Y.report],
            [870, AG_Y.report + 50],
            [898, AG_Y.report + 50],
          ], { marker: 'default', opacity: 0.5, dashed: true })}
          <text x={870} y={AG_Y.report + 68} textAnchor="middle" fontSize={9.5}
            fill={COLORS.textMuted}>
            요약 → DB · Slack
          </text>
        </svg>
      </div>

      {/* ── Optimization subgraph callout ───────────────────────────── */}
      <div>
        <div className="flex items-center gap-1.5 mb-2">
          <GitBranch size={11} style={{ color: 'var(--text-muted)' }} />
          <p className="text-[11px] font-semibold uppercase tracking-wider"
            style={{ color: 'var(--text-muted)' }}>
            optimization_graph (서브그래프)
          </p>
          <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
            · analyse_situation 내부에서 호출 — 디지털 트윈으로 후보 액션을 검증
          </span>
        </div>
        <div className="rounded-xl p-2 overflow-x-auto" style={{ backgroundColor: 'var(--bg-elevated)' }}>
          <OptimizationSubgraph visited={ran} />
        </div>
      </div>

      {/* ── Last-cycle trace ───────────────────────────────────────── */}
      {ran && (
        <CycleTrace cycleStatus={cycleStatus!} />
      )}
    </div>
  )
}

// ── Cycle trace timeline ────────────────────────────────────────────────────

function CycleTrace({ cycleStatus }: { cycleStatus: AgentCycleStatus }) {
  const decisions = cycleStatus.decisions ?? []
  const executed = cycleStatus.executed ?? []
  const ranAt = new Date(cycleStatus.ran_at)

  // Backend does not yet report per-node timings; show step ordinals instead of
  // fabricated offsets. The first step carries the cycle's wall-clock timestamp.
  const steps: { step: string; label: string; detail: string; level: 'ok' | 'warn' | 'info' | 'danger' }[] = [
    {
      step: ranAt.toLocaleTimeString('ko-KR'),
      label: 'collect_data',
      detail: 'GET /v1/dashboard/summary',
      level: 'info',
    },
    {
      step: '단계 2',
      label: 'analyse_situation',
      detail: `Claude → ${decisions.length}개 결정${decisions.length > 0 ? ` (조치 ${decisions.filter(d => d.action_type !== 'no_action').length}건)` : ''}`,
      level: decisions.filter(d => d.action_type !== 'no_action').length > 0 ? 'warn' : 'ok',
    },
    ...(executed.length > 0
      ? [{
          step: '단계 3',
          label: 'execute_commands',
          detail: executed.map((e) => `${e.decision.tank_id}/${e.decision.action_type}: ${e.status}`).join(' · '),
          level: executed.every((e) => e.status === 'ok') ? 'ok' as const : 'danger' as const,
        }]
      : []),
    {
      step: executed.length > 0 ? '단계 4' : '단계 3',
      label: 'generate_report',
      detail: cycleStatus.final_report
        ? cycleStatus.final_report.slice(0, 80) + (cycleStatus.final_report.length > 80 ? '…' : '')
        : '—',
      level: 'info',
    },
  ]

  const levelColor: Record<typeof steps[number]['level'], string> = {
    ok: COLORS.ok, warn: COLORS.warn, info: COLORS.info, danger: COLORS.danger,
  }

  return (
    <div>
      <div className="flex items-center gap-1.5 mb-2">
        <Database size={11} style={{ color: 'var(--text-muted)' }} />
        <p className="text-[11px] font-semibold uppercase tracking-wider"
          style={{ color: 'var(--text-muted)' }}>
          최근 사이클 트레이스 · {ranAt.toLocaleString('ko-KR')}
        </p>
      </div>
      <div className="rounded-xl p-3 space-y-1.5" style={{ backgroundColor: 'var(--bg-elevated)' }}>
        {steps.map((s, i) => (
          <div key={`step-${i}`} className="flex items-start gap-3 text-[11px]">
            <span className="font-mono shrink-0 w-20"
              style={{ color: 'var(--text-muted)' }}>{s.step}</span>
            <span className="w-2 h-2 rounded-full mt-1.5 shrink-0"
              style={{ backgroundColor: levelColor[s.level] }} />
            <span className="font-mono font-semibold shrink-0 w-32"
              style={{ color: 'var(--text-secondary)' }}>{s.label}</span>
            <ChevronRight size={11} className="mt-0.5 shrink-0" style={{ color: 'var(--text-muted)' }} />
            <span className="flex-1" style={{ color: 'var(--text-primary)' }}>{s.detail}</span>
          </div>
        ))}
        {cycleStatus.error && (
          <div className="flex items-start gap-3 text-[11px] rounded-lg px-2 py-1.5 mt-1"
            style={{ backgroundColor: 'rgba(220,38,38,0.08)' }}>
            <AlertTriangle size={11} style={{ color: COLORS.danger }} className="mt-0.5 shrink-0" />
            <span style={{ color: COLORS.danger }}>오류: {cycleStatus.error}</span>
          </div>
        )}
      </div>
    </div>
  )
}
