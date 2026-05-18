/**
 * Pure-function tests for the audit + event summarisers.
 * No React, no DOM — runs in milliseconds.
 */
import { describe, expect, it } from 'vitest'

import { eventSummary, summariseAudit } from './format'
import type { AgentEvent, AuditEntry } from '@/types'

function audit(kind: string, data: Record<string, unknown> = {}): AuditEntry {
  return { ts: '2026-05-18T10:00:00Z', kind, model: 'M', data }
}
function agentEvt(
  kind: string,
  data: Record<string, unknown> = {},
): AgentEvent {
  return { ts: '2026-05-18T10:00:00Z', kind, tank_id: '', data }
}

describe('summariseAudit', () => {
  it('reports samples and trigger state for automl events', () => {
    expect(summariseAudit(audit('automl', { triggered: false, new_samples: 12 }))).toBe(
      '재훈련 불필요, 샘플 12',
    )
    expect(
      summariseAudit(audit('automl', { triggered: true, new_samples: 1024, promoted: true })),
    ).toBe('재훈련 트리거됨, 샘플 1024 → Production 승격')
  })

  it('formats drift PSI to 3 decimals and flags retraining', () => {
    expect(summariseAudit(audit('drift', { max_psi: 0.04567 }))).toBe('max PSI 0.046')
    expect(
      summariseAudit(audit('drift', { max_psi: 0.25, should_retrain: true })),
    ).toBe('max PSI 0.250 (재훈련 권장)')
  })

  it('falls back to em-dash when PSI is missing', () => {
    expect(summariseAudit(audit('drift', {}))).toBe('max PSI —')
  })

  it('truncates run_id for promotion events', () => {
    expect(
      summariseAudit(audit('promotion', { run_id: 'abcdef1234567890' })),
    ).toBe('run_id abcdef12 → Production')
  })

  it('formats deployment success and failure paths', () => {
    expect(summariseAudit(audit('deployment', { success: true }))).toBe('엣지 배포 성공')
    expect(
      summariseAudit(audit('deployment', { success: false, error: 'ssh refused' })),
    ).toBe('엣지 배포 실패: ssh refused')
  })

  it('surfaces error / message field for error events', () => {
    expect(summariseAudit(audit('error', { error: 'mlflow down' }))).toBe('mlflow down')
    expect(summariseAudit(audit('error', { message: 'fallback' }))).toBe('fallback')
  })

  it('returns empty string for unknown kinds', () => {
    expect(summariseAudit(audit('mystery'))).toBe('')
  })
})

describe('eventSummary', () => {
  it('shows node name and duration for node events', () => {
    expect(eventSummary(agentEvt('node_completed', { node: 'analyse', duration_ms: 250 }))).toBe(
      'analyse (250ms)',
    )
    expect(eventSummary(agentEvt('node_started', { node: 'collect' }))).toBe('collect')
  })

  it('aggregates counts for cycle_completed', () => {
    expect(eventSummary(agentEvt('cycle_completed', { decisions: 3, executed: 2 }))).toBe(
      '결정 3 · 실행 2',
    )
  })

  it('joins action + score for optimization_completed', () => {
    expect(
      eventSummary(agentEvt('optimization_completed', { selected_action: 'reduce_feeding', score: 0.876 })),
    ).toBe('reduce_feeding (점수 0.88)')
  })

  it('returns empty string when optimization has no selected action', () => {
    expect(eventSummary(agentEvt('optimization_completed', {}))).toBe('')
  })

  it('surfaces error for error events', () => {
    expect(eventSummary(agentEvt('error', { error: 'redis disconnected' }))).toBe(
      'redis disconnected',
    )
  })
})
