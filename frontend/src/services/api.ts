// API client — typed wrappers around backend REST endpoints
// TODO (Phase 2): Add request/response interceptors for auth token injection.
// TODO (Phase 3): Add React Query hooks for automatic caching and refetch.

import axios from 'axios'
import type {
  Alert,
  AlertCategory,
  AlertSeverity,
  DashboardSummary,
  FeedingRecord,
  FishGrowthRecord,
  Tank,
  WaterQualityReading,
} from '@/types'

const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

export const apiClient = axios.create({
  baseURL: `${BASE_URL}/api/v1`,
  headers: { 'Content-Type': 'application/json' },
  timeout: 10_000,
})

// ── Dashboard ──────────────────────────────────────────────────

export const getDashboardSummary = (): Promise<DashboardSummary> =>
  apiClient.get<DashboardSummary>('/dashboard/summary').then((r) => r.data)

export const listTanks = (): Promise<Tank[]> =>
  apiClient.get<Tank[]>('/dashboard/tanks').then((r) => r.data)

// ── Monitoring ─────────────────────────────────────────────────

export const getLatestWaterQuality = (
  tankId?: string,
  limit = 10
): Promise<WaterQualityReading[]> =>
  apiClient
    .get<WaterQualityReading[]>('/monitoring/water-quality/latest', {
      params: { tank_id: tankId, limit },
    })
    .then((r) => r.data)

export const getWaterQualityHistory = (
  tankId: string,
  params?: { start_time?: string; end_time?: string; limit?: number }
): Promise<WaterQualityReading[]> =>
  apiClient
    .get<WaterQualityReading[]>('/monitoring/water-quality/history', {
      params: { tank_id: tankId, ...params },
    })
    .then((r) => r.data)

export const getLatestFishGrowth = (
  tankId?: string,
  limit = 10
): Promise<FishGrowthRecord[]> =>
  apiClient
    .get<FishGrowthRecord[]>('/monitoring/fish-growth/latest', {
      params: { tank_id: tankId, limit },
    })
    .then((r) => r.data)

// ── Alerts ─────────────────────────────────────────────────────

export const listAlerts = (params?: {
  tank_id?: string
  active_only?: boolean
  limit?: number
}): Promise<Alert[]> =>
  apiClient.get<Alert[]>('/alerts/', { params }).then((r) => r.data)

export const resolveAlert = (
  alertId: number,
  notes?: string
): Promise<Alert> =>
  apiClient
    .patch<Alert>(`/alerts/${alertId}/resolve`, { resolution_notes: notes })
    .then((r) => r.data)

// ── Control ────────────────────────────────────────────────────

export const triggerFeeding = (
  tankId: string,
  amountKg: number,
  durationSeconds = 60
): Promise<{ job_id: string; status: string }> =>
  apiClient
    .post('/control/feeding/trigger', {
      tank_id: tankId,
      amount_kg: amountKg,
      duration_seconds: durationSeconds,
    })
    .then((r) => r.data)

export const stopFeeding = (tankId: string): Promise<{ job_id: string }> =>
  apiClient.post(`/control/feeding/stop/${tankId}`).then((r) => r.data)
