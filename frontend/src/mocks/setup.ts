// Mock adapter — intercepts API calls when VITE_USE_MOCK=true
// Uses axios custom adapters so no real network request is ever made.

import type { AxiosRequestConfig } from 'axios'
import { apiClient, agentClient } from '@/services/api'
import {
  MOCK_AGENT_HEALTH,
  MOCK_AGENT_STATUS,
  MOCK_ALERTS,
  MOCK_MODEL_STATUS,
  MOCK_OPT_STATUS,
  MOCK_SETTINGS,
  MOCK_TANKS,
  MOCK_USER,
  generateFeedingRecords,
  generateFishGrowth,
  generateWQHistory,
  getCurrentWQ,
  getDashboardSummary,
} from './data'

type MockResolver = (
  url: string,
  params: Record<string, unknown>,
  method: string,
  body: unknown,
) => unknown | null

// ── API mock router ───────────────────────────────────────────────────────────

const apiResolver: MockResolver = (url, params, method) => {
  const tankId = (params?.tank_id as string | undefined) ?? 'TANK-01'
  const limit   = Number(params?.limit ?? 10)
  const bucketMins = Number(params?.bucket_minutes ?? 60)

  // Auth
  if (url === '/v1/auth/me'      && method === 'get')  return MOCK_USER
  if (url === '/v1/auth/login'   && method === 'post') return { access_token: 'mock-access', refresh_token: 'mock-refresh', token_type: 'bearer' }
  if (url === '/v1/auth/refresh' && method === 'post') return { access_token: 'mock-access', refresh_token: 'mock-refresh', token_type: 'bearer' }
  if (url === '/v1/auth/logout'  && method === 'post') return {}
  if (url === '/v1/auth/register'&& method === 'post') return MOCK_USER

  // Dashboard
  if (url === '/v1/dashboard/summary') return getDashboardSummary()
  if (url === '/v1/dashboard/tanks')   return MOCK_TANKS

  // Monitoring
  if (url === '/v1/monitoring/water-quality/history')
    return generateWQHistory(tankId, limit > 0 ? limit : 24, bucketMins)
  if (url === '/v1/monitoring/water-quality/latest')
    return Array.from({ length: Math.min(limit, 20) }, (_, i) => ({
      ...(getCurrentWQ(tankId) as Record<string, unknown>),
      id: 1000 + i,
      measured_at: new Date(Date.now() - i * 5_000).toISOString(),
    }))
  if (url === '/v1/monitoring/fish-growth/latest')
    return generateFishGrowth(tankId, limit)
  if (url === '/v1/monitoring/feeding/latest')
    return generateFeedingRecords(tankId, limit)

  // Alerts
  if (url === '/v1/alerts/' || url === '/v1/alerts') {
    const activeOnly = params?.active_only === true || params?.active_only === 'true'
    return activeOnly ? MOCK_ALERTS.filter((a) => a.is_active) : MOCK_ALERTS
  }
  if (/\/v1\/alerts\/\d+\/resolve/.test(url) && method === 'patch') {
    return { ...MOCK_ALERTS[0], resolved_at: new Date().toISOString(), is_active: false }
  }

  // Control endpoints — return a stub job response
  if (url.startsWith('/v1/control'))
    return { job_id: `mock-job-${Date.now()}`, status: 'queued' }

  // Settings
  if (url === '/v1/settings' && method === 'get')   return MOCK_SETTINGS
  if (url === '/v1/settings' && method === 'patch')  return MOCK_SETTINGS

  // Model status
  if (url === '/v1/growth/status')        return MOCK_MODEL_STATUS.growth
  if (url === '/v1/feeding/status')       return MOCK_MODEL_STATUS.feeding
  if (url === '/v1/water-quality/status') return MOCK_MODEL_STATUS.waterQuality

  return null
}

// ── Agent mock router ─────────────────────────────────────────────────────────

const agentResolver: MockResolver = (url, _params, method) => {
  if (url === 'health'              && method === 'get')  return MOCK_AGENT_HEALTH
  if (url === 'status'              && method === 'get')  return MOCK_AGENT_STATUS
  if (url === 'run'                 && method === 'post') return {
    status: 'completed',
    final_report: MOCK_AGENT_STATUS.final_report,
    decisions: MOCK_AGENT_STATUS.decisions.length,
    executed: MOCK_AGENT_STATUS.executed.length,
  }
  if (url === 'optimization/status' && method === 'get')  return MOCK_OPT_STATUS
  if (url === 'optimize'            && method === 'post') return {
    status: 'completed',
    tank_id: 'TANK-01',
    selected_action: MOCK_OPT_STATUS.selected_action,
    simulation_result: MOCK_OPT_STATUS.simulation_result,
  }
  return null
}

// ── Axios adapter factory ─────────────────────────────────────────────────────

function makeMockAdapter(resolver: MockResolver) {
  return (config: AxiosRequestConfig) => {
    const url    = (config.url ?? '').replace(/^\/+/, '/')  // normalise leading slash
    const params = (config.params ?? {}) as Record<string, unknown>
    const method = (config.method ?? 'get').toLowerCase()
    let body: unknown
    try { body = config.data ? JSON.parse(config.data as string) : undefined } catch { body = config.data }

    const mockData = resolver(url, params, method, body)
    if (mockData === null) {
      // No mock for this URL — let the real request proceed
      return Promise.reject({ isMockPassthrough: true, config })
    }

    // Small simulated latency so the loading states render visibly
    return new Promise((resolve) =>
      setTimeout(() => {
        resolve({
          data: mockData,
          status: 200,
          statusText: 'OK (mock)',
          headers: { 'content-type': 'application/json' },
          config,
          request: {},
        })
      }, 80),
    )
  }
}

// ── Install ───────────────────────────────────────────────────────────────────

export function setupMocks() {
  const apiAdapter    = makeMockAdapter(apiResolver)
  const agentAdapter  = makeMockAdapter(agentResolver)

  apiClient.interceptors.request.use((config) => {
    config.adapter = apiAdapter as unknown as typeof config.adapter
    return config
  })

  agentClient.interceptors.request.use((config) => {
    config.adapter = agentAdapter as unknown as typeof config.adapter
    return config
  })

  console.info('[mock] Mock data active — all API calls are intercepted.')
}
