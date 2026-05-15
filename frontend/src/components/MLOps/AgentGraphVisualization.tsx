// LangGraph agent topology visualization.
//
// Renders the actual node/edge structure of the two compiled graphs that live
// in agents/management_agent/graph.py and agents/optimization_agent/graph.py,
// and highlights which nodes were touched by the most recent execution.

import { useQuery } from '@tanstack/react-query'
import { GitBranch, Network } from 'lucide-react'
import { getAgentCycleStatus } from '@/services/api'
import type { AgentCycleStatus } from '@/types'

// ── Geometry primitives ──────────────────────────────────────────────────────

type NodeKind = 'start' | 'end' | 'task' | 'llm' | 'subgraph'

interface GraphNode {
  id: string
  x: number
  y: number
  label: string
  sub?: string
  kind: NodeKind
}

interface GraphEdge {
  // Path is an explicit ordered list of (x, y) points; we draw a polyline + arrow.
  points: [number, number][]
  label?: string
  conditional?: boolean
  branchTaken?: boolean // when true and this edge is conditional, render as primary
}

interface NodeStatus {
  visited: boolean
  errored?: boolean
}

const NODE_W = 138
const NODE_H = 44
const SMALL_R = 18

// ── Visual constants ─────────────────────────────────────────────────────────

const COLORS = {
  edge:         'var(--bg-border)',
  edgeActive:   '#8B5CF6',
  edgeDimmed:   'var(--bg-border)',
  nodeFill:     'var(--bg-surface)',
  nodeBorder:   'var(--bg-border)',
  visitedFill:  'rgba(139, 92, 246, 0.10)',
  visitedBorder:'#8B5CF6',
  errorBorder:  'var(--danger)',
  startFill:    'rgba(5,150,105,0.12)',
  startBorder:  'var(--ok)',
  endFill:      'rgba(148, 163, 184, 0.12)',
  endBorder:    'var(--text-muted)',
  text:         'var(--text-primary)',
  textMuted:    'var(--text-muted)',
  llmAccent:    '#8B5CF6',
}

// ── Generic node + edge renderers ────────────────────────────────────────────

function renderNode(node: GraphNode, status: NodeStatus) {
  const isTerminal = node.kind === 'start' || node.kind === 'end'

  if (isTerminal) {
    const fill = node.kind === 'start' ? COLORS.startFill : COLORS.endFill
    const stroke = node.kind === 'start' ? COLORS.startBorder : COLORS.endBorder
    return (
      <g key={node.id}>
        <ellipse
          cx={node.x}
          cy={node.y}
          rx={SMALL_R + 6}
          ry={SMALL_R - 2}
          fill={fill}
          stroke={stroke}
          strokeWidth={1.5}
        />
        <text
          x={node.x}
          y={node.y + 1}
          textAnchor="middle"
          dominantBaseline="middle"
          fontSize={10}
          fontWeight={700}
          fill={stroke}
        >
          {node.label}
        </text>
      </g>
    )
  }

  const fill = status.visited ? COLORS.visitedFill : COLORS.nodeFill
  const border = status.errored
    ? COLORS.errorBorder
    : status.visited
    ? COLORS.visitedBorder
    : COLORS.nodeBorder

  return (
    <g key={node.id}>
      <rect
        x={node.x - NODE_W / 2}
        y={node.y - NODE_H / 2}
        width={NODE_W}
        height={NODE_H}
        rx={10}
        ry={10}
        fill={fill}
        stroke={border}
        strokeWidth={status.visited ? 1.5 : 1}
      />
      {node.kind === 'llm' && (
        // LLM badge in the top-right corner
        <circle cx={node.x + NODE_W / 2 - 8} cy={node.y - NODE_H / 2 + 8} r={3} fill={COLORS.llmAccent} />
      )}
      <text
        x={node.x}
        y={node.sub ? node.y - 5 : node.y + 1}
        textAnchor="middle"
        dominantBaseline="middle"
        fontSize={11}
        fontWeight={600}
        fontFamily="ui-monospace, SFMono-Regular, monospace"
        fill={COLORS.text}
      >
        {node.label}
      </text>
      {node.sub && (
        <text
          x={node.x}
          y={node.y + 9}
          textAnchor="middle"
          dominantBaseline="middle"
          fontSize={9.5}
          fill={COLORS.textMuted}
        >
          {node.sub}
        </text>
      )}
    </g>
  )
}

function renderEdge(edge: GraphEdge, idx: number) {
  // Color: active if conditional+branchTaken, dimmed if conditional+!branchTaken, default otherwise.
  let stroke = COLORS.edge
  let opacity = 1
  let dash: string | undefined
  if (edge.conditional) {
    if (edge.branchTaken) {
      stroke = COLORS.edgeActive
    } else {
      stroke = COLORS.edgeDimmed
      opacity = 0.5
      dash = '3 3'
    }
  }

  const pointsStr = edge.points.map(([x, y]) => `${x},${y}`).join(' ')

  // Place label near the midpoint of the first segment.
  let label: JSX.Element | null = null
  if (edge.label && edge.points.length >= 2) {
    const [p0, p1] = [edge.points[0], edge.points[1]]
    const mx = (p0[0] + p1[0]) / 2
    const my = (p0[1] + p1[1]) / 2
    label = (
      <text
        x={mx + 6}
        y={my}
        fontSize={9.5}
        fontWeight={600}
        fill={stroke}
        opacity={opacity}
        dominantBaseline="middle"
      >
        {edge.label}
      </text>
    )
  }

  return (
    <g key={`edge-${idx}`}>
      <polyline
        points={pointsStr}
        fill="none"
        stroke={stroke}
        strokeWidth={1.6}
        strokeDasharray={dash}
        opacity={opacity}
        markerEnd={
          edge.conditional && edge.branchTaken
            ? 'url(#arrow-active)'
            : edge.conditional
            ? 'url(#arrow-dim)'
            : 'url(#arrow)'
        }
      />
      {label}
    </g>
  )
}

// ── Management graph layout ──────────────────────────────────────────────────

const MGT_NODES: GraphNode[] = [
  { id: 'start',    x: 220, y: 28,  label: 'START',             kind: 'start' },
  { id: 'collect',  x: 220, y: 96,  label: 'collect_data',      sub: 'GET /dashboard/summary',     kind: 'task' },
  { id: 'analyse',  x: 220, y: 180, label: 'analyse_situation', sub: 'Claude 4.6 + 옵티마이저 서브그래프', kind: 'llm' },
  { id: 'execute',  x: 80,  y: 270, label: 'execute_commands',  sub: 'POST /control/*',            kind: 'task' },
  { id: 'report',   x: 220, y: 360, label: 'generate_report',   sub: '운영자용 요약 생성',          kind: 'task' },
  { id: 'end',      x: 220, y: 430, label: 'END',               kind: 'end' },
]

function buildManagementEdges(branchTaken: 'execute' | 'report'): GraphEdge[] {
  return [
    { points: [[220, 46], [220, 74]] },
    { points: [[220, 118], [220, 158]] },
    // conditional: analyse → execute (needs action)
    {
      points: [[220, 202], [220, 234], [80, 234], [80, 248]],
      label: 'needs_action',
      conditional: true,
      branchTaken: branchTaken === 'execute',
    },
    // conditional: analyse → report (no_action)
    {
      points: [[180, 196], [150, 196], [150, 338], [180, 338]],
      label: 'no_action',
      conditional: true,
      branchTaken: branchTaken === 'report',
    },
    // execute → report (merge)
    { points: [[80, 292], [80, 320], [220, 320], [220, 338]] },
    { points: [[220, 382], [220, 412]] },
  ]
}

// ── Optimization subgraph layout ─────────────────────────────────────────────

const OPT_NODES: GraphNode[] = [
  { id: 'start',  x: 30,  y: 80, label: 'START',                kind: 'start' },
  { id: 'gather', x: 145, y: 80, label: 'gather_outputs',       sub: 'AI 결과 수집',     kind: 'task' },
  { id: 'gen',    x: 305, y: 80, label: 'generate_candidates',  sub: 'Claude 후보 제안',  kind: 'llm' },
  { id: 'sim',    x: 465, y: 80, label: 'simulate_in_twin',     sub: '디지털 트윈 ODE',   kind: 'task' },
  { id: 'sel',    x: 625, y: 80, label: 'select_optimal',       sub: '최고 점수 선택',    kind: 'task' },
  { id: 'end',    x: 740, y: 80, label: 'END',                  kind: 'end' },
]

const OPT_EDGES: GraphEdge[] = [
  { points: [[54, 80], [76, 80]] },
  { points: [[214, 80], [236, 80]] },
  { points: [[374, 80], [396, 80]] },
  { points: [[534, 80], [556, 80]] },
  { points: [[694, 80], [716, 80]] },
]

// ── Arrow marker defs ────────────────────────────────────────────────────────

function ArrowDefs() {
  return (
    <defs>
      <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
        <path d="M0,0 L10,5 L0,10 z" fill={COLORS.edge} />
      </marker>
      <marker id="arrow-active" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
        <path d="M0,0 L10,5 L0,10 z" fill={COLORS.edgeActive} />
      </marker>
      <marker id="arrow-dim" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
        <path d="M0,0 L10,5 L0,10 z" fill={COLORS.edgeDimmed} opacity={0.5} />
      </marker>
    </defs>
  )
}

// ── Main component ───────────────────────────────────────────────────────────

export default function AgentGraphVisualization() {
  // Same queryKey as AgentPanel — React Query dedupes, no extra request.
  const { data: cycleStatus } = useQuery<AgentCycleStatus>({
    queryKey: ['agent-cycle-status'],
    queryFn: getAgentCycleStatus,
    refetchInterval: 15_000,
    retry: false,
  })
  // Determine which path the conditional took and which nodes were visited.
  const ran = !!cycleStatus?.ran_at && cycleStatus.status !== 'no_cycle_run_yet'
  const executedAny = (cycleStatus?.executed?.length ?? 0) > 0
  const nonTrivialDecisions = (cycleStatus?.decisions ?? []).filter(
    (d) => d.action_type !== 'no_action'
  ).length
  const branchTaken: 'execute' | 'report' =
    executedAny || nonTrivialDecisions > 0 ? 'execute' : 'report'

  const errored = !!cycleStatus?.error

  const mgtStatus: Record<string, NodeStatus> = {
    start:   { visited: ran },
    collect: { visited: ran },
    analyse: { visited: ran, errored: errored && !executedAny },
    execute: { visited: executedAny, errored: errored && executedAny },
    report:  { visited: ran && !!cycleStatus?.final_report },
    end:     { visited: ran && !!cycleStatus?.final_report },
  }

  // Optimization subgraph runs inside analyse_situation, so we mark it visited
  // whenever analyse was reached.
  const optVisited = ran
  const optStatus: Record<string, NodeStatus> = {
    start:  { visited: optVisited },
    gather: { visited: optVisited },
    gen:    { visited: optVisited },
    sim:    { visited: optVisited },
    sel:    { visited: optVisited },
    end:    { visited: optVisited },
  }

  const mgtEdges = buildManagementEdges(branchTaken)

  return (
    <div className="card space-y-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Network size={15} style={{ color: COLORS.llmAccent }} />
          <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
            LangGraph 워크플로우
          </h3>
        </div>
        <div className="flex items-center gap-3 text-[10px]" style={{ color: 'var(--text-muted)' }}>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: COLORS.visitedBorder }} />
            실행됨
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: COLORS.edge }} />
            대기
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: COLORS.errorBorder }} />
            실패
          </span>
          <span className="ml-1" style={{ color: COLORS.llmAccent }}>● LLM 노드</span>
        </div>
      </div>

      {/* Management graph */}
      <div>
        <div className="flex items-center gap-1.5 mb-2">
          <GitBranch size={11} style={{ color: 'var(--text-muted)' }} />
          <p className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
            management_graph
          </p>
          <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
            · 농장 1회 사이클 (15분 주기 또는 수동 실행)
          </span>
        </div>
        <div className="rounded-xl p-2" style={{ backgroundColor: 'var(--bg-elevated)' }}>
          <svg
            viewBox="0 0 440 460"
            preserveAspectRatio="xMidYMid meet"
            className="w-full h-auto max-h-[460px]"
            role="img"
            aria-label="Management agent graph"
          >
            <ArrowDefs />
            {mgtEdges.map(renderEdge)}
            {MGT_NODES.map((n) => renderNode(n, mgtStatus[n.id] ?? { visited: false }))}
          </svg>
        </div>
        <p className="text-[11px] mt-2" style={{ color: 'var(--text-muted)' }}>
          <span style={{ color: COLORS.edgeActive }}>실선·보라색</span>은 직전 사이클이
          실제로 통과한 분기입니다.{' '}
          {branchTaken === 'execute' ? (
            <>조치가 필요해 <code className="text-[10px]">execute_commands</code> 경로로 진행됐습니다.</>
          ) : (
            <>이상이 없어 바로 <code className="text-[10px]">generate_report</code>로 향했습니다.</>
          )}
        </p>
      </div>

      {/* Optimization subgraph */}
      <div>
        <div className="flex items-center gap-1.5 mb-2">
          <GitBranch size={11} style={{ color: 'var(--text-muted)' }} />
          <p className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
            optimization_graph (서브그래프)
          </p>
          <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
            · analyse_situation 내부에서 호출
          </span>
        </div>
        <div className="rounded-xl p-2 overflow-x-auto" style={{ backgroundColor: 'var(--bg-elevated)' }}>
          <svg
            viewBox="0 0 770 160"
            preserveAspectRatio="xMidYMid meet"
            className="w-full h-auto"
            style={{ minWidth: 600 }}
            role="img"
            aria-label="Optimization agent subgraph"
          >
            <ArrowDefs />
            {OPT_EDGES.map(renderEdge)}
            {OPT_NODES.map((n) => renderNode(n, optStatus[n.id] ?? { visited: false }))}
          </svg>
        </div>
        <p className="text-[11px] mt-2" style={{ color: 'var(--text-muted)' }}>
          AI 모듈 3종의 출력을 모은 뒤 Claude가 제어 후보를 생성하고, 디지털 트윈 ODE
          시뮬레이션으로 검증해 최고 점수 액션을 반환합니다.
        </p>
      </div>
    </div>
  )
}
