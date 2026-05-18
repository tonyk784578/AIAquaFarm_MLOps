// API client — typed wrappers around backend REST endpoints.
// Auth interceptors live in AuthContext (injected at runtime).

import axios from 'axios'
import type {
  AgentCycleStatus,
  AgentHealth,
  AgentHistoryResponse,
  Alert,
  AuditResponse,
  DashboardSummary,
  DriftResponse,
  FarmSettings,
  FeedingRecord,
  FishGrowthRecord,
  MLOpsActionResponse,
  ModelStatus,
  OptimizationHistoryResponse,
  OptimizationStatus,
  RegistryResponse,
  Tank,
  TokenResponse,
  UserProfile,
  WaterQualityReading,
} from '@/types'

// Empty string → relative URL → goes through Vite proxy in dev, Nginx proxy in prod.
// Set VITE_API_BASE_URL only when backend is on a different host entirely.
const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''
const AGENT_BASE_URL = import.meta.env.VITE_AGENT_BASE_URL ?? '/agents'

export const apiClient = axios.create({
  baseURL: `${BASE_URL}/api`,
  headers: { 'Content-Type': 'application/json' },
  timeout: 10_000,
  withCredentials: true, // send httpOnly auth cookies automatically
})

// Separate client for the agents service (port 8001 / /agents/ Nginx prefix)
export const agentClient = axios.create({
  baseURL: AGENT_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 90_000, // agent cycles can take up to ~60 s with LLM calls
})

// ── Auth ───────────────────────────────────────────────────────────────────────

export const loginUser = async (
  username: string,
  password: string
): Promise<TokenResponse> => {
  const form = new URLSearchParams({ username, password })
  const res = await apiClient.post<TokenResponse>('/v1/auth/login', form, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  })
  return res.data
}

// Cookie-based refresh — the httpOnly aq_refresh cookie is sent automatically.
// Passing an explicit token in the body is still supported for non-browser clients.
export const refreshSession = async (refreshToken?: string): Promise<TokenResponse> => {
  const res = await apiClient.post<TokenResponse>('/v1/auth/refresh', {
    refresh_token: refreshToken ?? null,
  })
  return res.data
}

export const getCurrentUser = (): Promise<UserProfile> =>
  apiClient.get<UserProfile>('/v1/auth/me').then((r) => r.data)

// ── Dashboard ──────────────────────────────────────────────────

export const getDashboardSummary = (): Promise<DashboardSummary> =>
  apiClient.get<DashboardSummary>('/v1/dashboard/summary').then((r) => r.data)

export const listTanks = (): Promise<Tank[]> =>
  apiClient.get<Tank[]>('/v1/dashboard/tanks').then((r) => r.data)

// ── Monitoring ─────────────────────────────────────────────────

export const getLatestWaterQuality = (
  tankId?: string,
  limit = 10
): Promise<WaterQualityReading[]> =>
  apiClient
    .get<WaterQualityReading[]>('/v1/monitoring/water-quality/latest', {
      params: { tank_id: tankId, limit },
    })
    .then((r) => r.data)

export const getWaterQualityHistory = (
  tankId: string,
  params?: { start_time?: string; end_time?: string; bucket_minutes?: number; limit?: number }
): Promise<Record<string, unknown>[]> =>
  apiClient
    .get<Record<string, unknown>[]>('/v1/monitoring/water-quality/history', {
      params: { tank_id: tankId, ...params },
    })
    .then((r) => r.data)

export const getLatestFishGrowth = (
  tankId?: string,
  limit = 10
): Promise<FishGrowthRecord[]> =>
  apiClient
    .get<FishGrowthRecord[]>('/v1/monitoring/fish-growth/latest', {
      params: { tank_id: tankId, limit },
    })
    .then((r) => r.data)

export const getFeedingHistory = (
  tankId?: string,
  limit = 20
): Promise<FeedingRecord[]> =>
  apiClient
    .get<FeedingRecord[]>('/v1/monitoring/feeding/latest', {
      params: { tank_id: tankId, limit },
    })
    .then((r) => r.data)

// ── Alerts ─────────────────────────────────────────────────────

export const listAlerts = (params?: {
  tank_id?: string
  active_only?: boolean
  limit?: number
}): Promise<Alert[]> =>
  apiClient.get<Alert[]>('/v1/alerts/', { params }).then((r) => r.data)

export const resolveAlert = (
  alertId: number,
  notes?: string
): Promise<Alert> =>
  apiClient
    .patch<Alert>(`/v1/alerts/${alertId}/resolve`, { resolution_notes: notes })
    .then((r) => r.data)

// ── AI Model status ────────────────────────────────────────────

export const getGrowthModelStatus = (): Promise<ModelStatus> =>
  apiClient.get<ModelStatus>('/v1/growth/status').then((r) => r.data)

export const getFeedingModelStatus = (): Promise<ModelStatus> =>
  apiClient.get<ModelStatus>('/v1/feeding/status').then((r) => r.data)

export const getWaterQualityModelStatus = (): Promise<ModelStatus> =>
  apiClient.get<ModelStatus>('/v1/water-quality/status').then((r) => r.data)

// ── Settings ───────────────────────────────────────────────────

export const getFarmSettings = (): Promise<FarmSettings> =>
  apiClient.get<FarmSettings>('/v1/settings').then((r) => r.data)

export const updateFarmSettings = (patch: Partial<FarmSettings>): Promise<FarmSettings> =>
  apiClient.patch<FarmSettings>('/v1/settings', patch).then((r) => r.data)

// ── Control ────────────────────────────────────────────────────

export const triggerFeeding = (
  tankId: string,
  amountKg: number,
  durationSeconds = 60
): Promise<{ job_id: string; status: string }> =>
  apiClient
    .post('/v1/control/feeding/trigger', {
      tank_id: tankId,
      amount_kg: amountKg,
      duration_seconds: durationSeconds,
    })
    .then((r) => r.data)

export const stopFeeding = (tankId: string): Promise<{ job_id: string }> =>
  apiClient.post(`/v1/control/feeding/stop/${tankId}`).then((r) => r.data)

export const controlPump = (
  tankId: string,
  action: 'start' | 'stop'
): Promise<{ job_id: string; status: string }> =>
  apiClient.post(`/v1/control/pump/${tankId}/${action}`).then((r) => r.data)

export const increaseAeration = (
  tankId: string,
  boostPct = 30
): Promise<{ job_id: string; status: string }> =>
  apiClient
    .post('/v1/control/aeration/increase', { tank_id: tankId, boost_pct: boostPct })
    .then((r) => r.data)

export const triggerWaterExchange = (
  tankId: string,
  exchangePct = 10
): Promise<{ job_id: string; status: string }> =>
  apiClient
    .post('/v1/control/water-exchange', { tank_id: tankId, exchange_pct: exchangePct })
    .then((r) => r.data)

// ── Agent service ───────────────────────────────────────────────

export const getAgentHealth = (): Promise<AgentHealth> =>
  agentClient.get<AgentHealth>('health').then((r) => r.data)

export const getAgentCycleStatus = (): Promise<AgentCycleStatus> =>
  agentClient.get<AgentCycleStatus>('status').then((r) => r.data)

export const triggerAgentCycle = (): Promise<{
  status: string
  final_report: string
  decisions: number
  executed: number
}> => agentClient.post('run').then((r) => r.data)

export const getOptimizationStatus = (): Promise<OptimizationStatus> =>
  agentClient.get<OptimizationStatus>('optimization/status').then((r) => r.data)

export const triggerOptimization = (params: {
  tank_id: string
  ammonia_ppm?: number
  nitrite_ppm?: number
  dissolved_oxygen_mgl?: number
  temperature_c?: number
  water_exchange_rate_pct?: number
}): Promise<{
  status: string
  tank_id: string
  selected_action: OptimizationStatus['selected_action']
  simulation_result: OptimizationStatus['simulation_result']
}> => agentClient.post('optimize', params).then((r) => r.data)

// ── Agent history ──────────────────────────────────────────────────────────────

export const getAgentHistory = (n = 20): Promise<AgentHistoryResponse> =>
  agentClient.get<AgentHistoryResponse>('history', { params: { n } }).then((r) => r.data)

export const getOptimizationHistory = (
  n = 20
): Promise<OptimizationHistoryResponse> =>
  agentClient
    .get<OptimizationHistoryResponse>('history/optimization', { params: { n } })
    .then((r) => r.data)

// SSE stream URL (consumed by useEventSource hook — EventSource doesn't accept
// custom headers, so this returns just the URL).
export const agentEventStreamUrl = (): string => `${AGENT_BASE_URL}/events/stream`

// ── MLOps (proxied via backend /api/v1/mlops/*) ───────────────────────────────

export const getMLOpsRegistry = (): Promise<RegistryResponse> =>
  apiClient.get<RegistryResponse>('/v1/mlops/registry').then((r) => r.data)

export const getMLOpsAudit = (params?: {
  n?: number
  kind?: string
  model?: string
}): Promise<AuditResponse> =>
  apiClient.get<AuditResponse>('/v1/mlops/audit', { params }).then((r) => r.data)

export const getMLOpsDrift = (): Promise<DriftResponse> =>
  apiClient.get<DriftResponse>('/v1/mlops/drift').then((r) => r.data)

export const triggerMLOpsRetrain = (
  model: string,
  dryRun = false
): Promise<MLOpsActionResponse> =>
  apiClient
    .post<MLOpsActionResponse>('/v1/mlops/retrain', { model, dry_run: dryRun })
    .then((r) => r.data)

export const triggerMLOpsPromote = (
  model: string,
  runId: string,
  force = false
): Promise<MLOpsActionResponse> =>
  apiClient
    .post<MLOpsActionResponse>('/v1/mlops/promote', { model, run_id: runId, force })
    .then((r) => r.data)

export const triggerMLOpsDeploy = (
  model?: string
): Promise<MLOpsActionResponse> =>
  apiClient
    .post<MLOpsActionResponse>('/v1/mlops/deploy', { model: model ?? null })
    .then((r) => r.data)
