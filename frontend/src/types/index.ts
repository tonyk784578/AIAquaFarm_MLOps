// Core domain types matching backend Pydantic schemas

export interface WaterQualityReading {
  id: number
  tank_id: string
  measured_at: string
  temperature_c: number | null
  ph: number | null
  dissolved_oxygen_mgl: number | null
  turbidity_ntu: number | null
  ammonia_ppm: number | null
  nitrite_ppm: number | null
  ammonia_confidence: number | null
  nitrite_confidence: number | null
  source: 'sensor' | 'virtual_sensor' | 'manual'
}

export interface FishGrowthRecord {
  id: number
  tank_id: string
  measured_at: string
  avg_length_cm: number | null
  avg_weight_g: number | null
  fish_count: number | null
  biomass_kg: number | null
  daily_growth_rate_pct: number | null
  feed_conversion_ratio: number | null
  model_version: string | null
  inference_confidence: number | null
}

export interface FeedingRecord {
  id: number
  tank_id: string
  started_at: string
  ended_at: string | null
  commanded_amount_kg: number | null
  actual_amount_kg: number | null
  duration_seconds: number | null
  activity_score: number | null
  recommended_amount_kg: number | null
  feed_waste_estimate_pct: number | null
  trigger_source: 'ai' | 'manual' | 'schedule'
  is_completed: boolean
  is_emergency_stopped: boolean
}

export type AlertSeverity = 'critical' | 'warning' | 'info'
export type AlertCategory =
  | 'water_quality'
  | 'fish_growth'
  | 'feeding'
  | 'equipment'
  | 'system'

export interface Alert {
  id: number
  tank_id: string
  created_at: string
  resolved_at: string | null
  severity: AlertSeverity
  category: AlertCategory
  title: string
  message: string
  is_active: boolean
  metric_name: string | null
  metric_value: string | null
  threshold_value: string | null
  source: string
}

export interface DashboardSummary {
  water_quality: WaterQualityReading | null
  fish_growth: FishGrowthRecord | null
  active_alert_count: number
  recent_alerts: Alert[]
}

export interface Tank {
  tank_id: string
  name: string
  status: 'online' | 'offline' | 'warning'
}

export interface WSMessage<T = unknown> {
  type: 'water_quality' | 'fish_growth' | 'feeding' | 'alert' | 'control' | 'ping'
  tank_id: string
  timestamp: string
  data: T
}

// ── Auth ───────────────────────────────────────────────────────────────────────

export interface UserProfile {
  id: number
  username: string
  email: string
  full_name: string
  is_active: boolean
  is_superuser: boolean
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

// ── AI Model status ────────────────────────────────────────────────────────────

export interface ModelStatus {
  model_name: string
  is_loaded: boolean
  model_version: string
  device: string
}

export interface FarmSettings {
  ammonia_threshold_ppm: number
  nitrite_threshold_ppm: number
  dissolved_oxygen_min_mgl: number
  ph_min: number
  ph_max: number
  temperature_min_c: number
  temperature_max_c: number
  sensor_poll_interval: number
}

// ── Agent service types ────────────────────────────────────────────────────────

export interface ControlDecision {
  action_type: string
  tank_id: string
  parameters: Record<string, unknown>
  reasoning: string
  confidence: number
}

export interface ExecutedCommand {
  decision: ControlDecision
  status: 'ok' | 'error'
  error?: string
}

export interface AgentCycleStatus {
  status?: string
  ran_at: string
  final_report: string
  decisions: ControlDecision[]
  executed: ExecutedCommand[]
  error: string | null
}

export interface SimulationResult {
  status: string
  candidates_evaluated: number
  best_action: string
  best_score: number
}

export interface OptimizationStatus {
  status?: string
  ran_at: string
  tank_id: string
  selected_action: {
    action: string
    parameters: Record<string, unknown>
    reasoning: string
    score: number
  } | null
  simulation_result: SimulationResult | null
  candidates: number
}

export interface AgentHealth {
  status: string
  service: string
  management_graph: boolean
}
