/**
 * Pure formatters / summarisers used by the MLOps + Agents UIs.
 *
 * Kept dependency-free (no React, no axios) so they're trivially unit-testable
 * and reusable across components.
 */
import type { AgentEvent, AuditEntry } from '@/types'

/**
 * Build a one-line Korean summary for a single MLOps audit-log entry.
 *
 * Defensive: any value type is accepted under ``event.data`` since the
 * audit log stores arbitrary JSON payloads. Missing fields render as ``—``.
 */
export function summariseAudit(event: AuditEntry): string {
  const d = (event.data || {}) as Record<string, unknown>
  switch (event.kind) {
    case 'automl': {
      const triggered = d.triggered ? '재훈련 트리거됨' : '재훈련 불필요'
      const samples =
        typeof d.new_samples === 'number' ? `샘플 ${d.new_samples}` : ''
      const promoted = d.promoted ? ' → Production 승격' : ''
      return [triggered, samples].filter(Boolean).join(', ') + promoted
    }
    case 'drift': {
      const psi =
        typeof d.max_psi === 'number' ? d.max_psi.toFixed(3) : '—'
      const flag = d.should_retrain ? ' (재훈련 권장)' : ''
      return `max PSI ${psi}${flag}`
    }
    case 'promotion':
      return `run_id ${String(d.run_id || '').slice(0, 8)} → Production`
    case 'deployment':
      return d.success
        ? '엣지 배포 성공'
        : `엣지 배포 실패: ${String(d.error || '')}`
    case 'error':
      return String(d.error || d.message || '오류')
    default:
      return ''
  }
}

/**
 * Build a one-line Korean summary for a live agent SSE event.
 *
 * Same defensive pattern as ``summariseAudit``.
 */
export function eventSummary(ev: AgentEvent): string {
  const d = (ev.data || {}) as Record<string, unknown>
  if (ev.kind === 'node_started' || ev.kind === 'node_completed') {
    const node = String(d.node || '')
    const dur = typeof d.duration_ms === 'number' ? ` (${d.duration_ms}ms)` : ''
    return `${node}${dur}`
  }
  if (ev.kind === 'cycle_completed') {
    return `결정 ${d.decisions ?? 0} · 실행 ${d.executed ?? 0}`
  }
  if (ev.kind === 'optimization_completed') {
    const action = d.selected_action ? String(d.selected_action) : ''
    const score =
      typeof d.score === 'number' ? (d.score as number).toFixed(2) : ''
    return action ? `${action}${score ? ` (점수 ${score})` : ''}` : ''
  }
  if (ev.kind === 'error') {
    return String(d.error || d.message || '오류')
  }
  return ''
}
