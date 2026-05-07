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

// TODO (Phase 2): Add WebSocket message types for real-time updates
export interface WSMessage<T = unknown> {
  type: 'water_quality' | 'fish_growth' | 'feeding' | 'alert' | 'control'
  tank_id: string
  timestamp: string
  data: T
}
