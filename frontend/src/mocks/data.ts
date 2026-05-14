// Deterministic-ish helpers
const rng = (seed: number) => {
  const x = Math.sin(seed) * 10_000
  return x - Math.floor(x)
}
const jitter = (base: number, amp: number, seed: number) =>
  base + (rng(seed) - 0.5) * 2 * amp

// ── Static data ───────────────────────────────────────────────────────────────

export const MOCK_USER = {
  id: 1,
  username: 'demo',
  email: 'demo@aiaquafarm.io',
  full_name: '데모 관리자',
  is_active: true,
  is_superuser: true,
}

export const MOCK_TANKS = [
  { tank_id: 'TANK-01', name: '수조-01 (연어A)', status: 'online'  },
  { tank_id: 'TANK-02', name: '수조-02 (송어B)', status: 'warning' },
  { tank_id: 'TANK-03', name: '수조-03 (연어C)', status: 'offline' },
]

export const MOCK_SETTINGS = {
  ammonia_threshold_ppm:       0.8,
  nitrite_threshold_ppm:       0.15,
  dissolved_oxygen_min_mgl:    6.0,
  ph_min:                      6.8,
  ph_max:                      8.6,
  temperature_min_c:           18.0,
  temperature_max_c:           29.0,
  sensor_poll_interval:        5,
}

export const MOCK_MODEL_STATUS = {
  growth:      { model_name: 'FishDetection',             is_loaded: true,  model_version: 'v1.3.2', device: 'cpu' },
  feeding:     { model_name: 'FeedingActivityClassifier', is_loaded: true,  model_version: 'v2.1.0', device: 'cpu' },
  waterQuality:{ model_name: 'WaterQualityPredictor',     is_loaded: true,  model_version: 'v1.8.5', device: 'cpu' },
}

export const MOCK_AGENT_HEALTH = {
  status: 'ok',
  service: 'aquafarm-agents',
  management_graph: true,
}

// ── Current WQ per tank ───────────────────────────────────────────────────────

export function getCurrentWQ(tankId: string) {
  const base: Record<string, object> = {
    'TANK-01': {
      id: 1001, tank_id: 'TANK-01',
      measured_at: new Date().toISOString(),
      temperature_c:          25.3,
      ph:                      7.42,
      dissolved_oxygen_mgl:    8.14,
      ammonia_ppm:             0.82,   // warn
      nitrite_ppm:             0.13,   // warn
      turbidity_ntu:           7.2,
      ammonia_confidence: 0.94, nitrite_confidence: 0.91,
      source: 'virtual_sensor',
    },
    'TANK-02': {
      id: 1002, tank_id: 'TANK-02',
      measured_at: new Date().toISOString(),
      temperature_c:          23.8,
      ph:                      7.11,
      dissolved_oxygen_mgl:    5.1,    // danger < 6
      ammonia_ppm:             0.58,   // warn
      nitrite_ppm:             0.11,   // warn
      turbidity_ntu:           14.3,   // warn
      ammonia_confidence: 0.88, nitrite_confidence: 0.85,
      source: 'virtual_sensor',
    },
    'TANK-03': {
      id: 1003, tank_id: 'TANK-03',
      measured_at: new Date(Date.now() - 3 * 3600_000).toISOString(),
      temperature_c: 22.1, ph: 7.5,
      dissolved_oxygen_mgl: 7.8,
      ammonia_ppm: 0.12, nitrite_ppm: 0.04, turbidity_ntu: 4.1,
      ammonia_confidence: 0.92, nitrite_confidence: 0.89,
      source: 'sensor',
    },
  }
  return base[tankId] ?? base['TANK-01']
}

// ── WQ history: 24-hourly buckets with a story ────────────────────────────────
// TANK-01: ammonia spikes in the last ~6 hours (explains the alert)
// TANK-02: DO drops steadily across 24 h (explains the low-DO warning)

export function generateWQHistory(
  tankId: string,
  limit = 24,
  bucketMins = 60,
): Record<string, unknown>[] {
  const now = Date.now()
  return Array.from({ length: limit }, (_, i) => {
    const t = new Date(now - (limit - 1 - i) * bucketMins * 60_000)
    const hour = t.getHours()
    const s = i * 13 + (tankId === 'TANK-01' ? 7 : 31) // seed offset per tank

    const temp = 24 + 1.4 * Math.sin(((hour - 6) / 24) * Math.PI * 2) + jitter(0, 0.25, s)
    const ph   = 7.4 + 0.15 * Math.sin(i / 10) + jitter(0, 0.04, s + 1)
    const doBase = 8.6 - 0.9 * Math.sin(((hour - 6) / 24) * Math.PI * 2)

    // Ammonia story
    let ammonia: number
    if (tankId === 'TANK-01') {
      const progress = i / limit
      if (progress < 0.70) {
        ammonia = 0.18 + 0.06 * Math.sin(i * 0.5) + jitter(0, 0.04, s + 2)
      } else {
        const ramp = (progress - 0.70) / 0.30
        ammonia = 0.18 + ramp * 0.85 + jitter(0, 0.04, s + 2)
      }
    } else if (tankId === 'TANK-02') {
      ammonia = 0.52 + jitter(0, 0.06, s + 2)
    } else {
      ammonia = 0.10 + jitter(0, 0.03, s + 2)
    }

    // DO story
    let doVal: number
    if (tankId === 'TANK-02') {
      const drop = (i / limit) * 3.2
      doVal = Math.max(4.2, 8.1 - drop + jitter(0, 0.15, s + 3))
    } else {
      doVal = doBase + jitter(0, 0.18, s + 3)
    }

    const nitrite  = Math.max(0, 0.05 + (ammonia > 0.5 ? ammonia * 0.12 : 0) + jitter(0, 0.015, s + 4))
    const turbidity = 5.5 + jitter(0, 2.0, s + 5)

    return {
      bucket:                 t.toISOString(),
      temperature_c:          +temp.toFixed(2),
      ph:                     +ph.toFixed(2),
      dissolved_oxygen_mgl:   +doVal.toFixed(2),
      ammonia_ppm:            +Math.max(0, ammonia).toFixed(3),
      nitrite_ppm:            +Math.max(0, nitrite).toFixed(3),
      turbidity_ntu:          +Math.max(0, turbidity).toFixed(1),
    }
  })
}

// ── Fish growth: 30-day records showing consistent growth ─────────────────────

export function generateFishGrowth(tankId: string, limit = 30) {
  const now = Date.now()
  const baseWeight = tankId === 'TANK-02' ? 95 : 140
  const baseLength = tankId === 'TANK-02' ? 14 : 17.5
  const baseFishCount = tankId === 'TANK-02' ? 380 : 520

  return Array.from({ length: limit }, (_, i) => {
    const t = new Date(now - (limit - 1 - i) * 86_400_000)
    const dayGrowth = 1 + i * 0.013 + jitter(0, 0.003, i * 7 + 5)
    const weight    = baseWeight * dayGrowth
    const length    = baseLength * Math.pow(dayGrowth, 0.38)
    const fishCount = Math.max(baseFishCount - 10, baseFishCount - Math.floor(i * 0.3))
    const biomass   = (fishCount * weight) / 1000
    const fcr       = Math.max(1.0, 1.55 - i * 0.007 + jitter(0, 0.04, i * 3))
    const dailyRate = 1.3 + jitter(0, 0.25, i * 9)

    return {
      id:                   3000 + i,
      tank_id:              tankId,
      measured_at:          t.toISOString(),
      avg_weight_g:         +weight.toFixed(1),
      avg_length_cm:        +length.toFixed(2),
      fish_count:           fishCount,
      biomass_kg:           +biomass.toFixed(2),
      daily_growth_rate_pct:+dailyRate.toFixed(2),
      feed_conversion_ratio:+fcr.toFixed(3),
      model_version:        '1.3.2',
      inference_confidence: +(0.91 + jitter(0, 0.05, i * 11)).toFixed(3),
    }
  })
}

// ── Feeding records: 7 sessions with actual vs recommended variation ──────────

export function generateFeedingRecords(tankId: string, limit = 7) {
  const now = Date.now()

  // Craft a story: overfeeding → normal → underfeeding → AI correction
  const activityOverrides = [0.88, 0.82, 0.78, 0.52, 0.48, 0.71, 0.85]
  const sources: Array<'ai' | 'manual' | 'schedule'> = ['schedule', 'ai', 'ai', 'manual', 'ai', 'ai', 'ai']

  return Array.from({ length: limit }, (_, i) => {
    const start    = new Date(now - (limit - 1 - i) * 43_200_000) // every 12h
    const activity = activityOverrides[i] ?? (0.60 + jitter(0, 0.25, i * 17))
    const recommended = 2.8 + jitter(0, 0.35, i * 5)
    // Over/underfeed based on index
    const ratio = i < 2 ? 1.15 : i < 4 ? 0.95 : i < 6 ? 0.78 : 1.02
    const actual = recommended * ratio + jitter(0, 0.08, i * 3)
    const waste  = Math.max(0, (1 - activity) * 22 + jitter(0, 3, i * 7))

    return {
      id:                       5000 + i,
      tank_id:                  tankId,
      started_at:               start.toISOString(),
      ended_at:                 new Date(start.getTime() + 75_000).toISOString(),
      commanded_amount_kg:      +recommended.toFixed(2),
      actual_amount_kg:         +Math.max(0, actual).toFixed(2),
      duration_seconds:         75,
      activity_score:           +Math.min(1, Math.max(0, activity)).toFixed(3),
      recommended_amount_kg:    +recommended.toFixed(2),
      feed_waste_estimate_pct:  +waste.toFixed(1),
      trigger_source:           sources[i] ?? 'ai',
      is_completed:             true,
      is_emergency_stopped:     false,
    }
  })
}

// ── Alerts ────────────────────────────────────────────────────────────────────

export const MOCK_ALERTS = [
  {
    id: 101,
    tank_id: 'TANK-01',
    created_at: new Date(Date.now() - 22 * 60_000).toISOString(),
    resolved_at: null,
    severity: 'critical',
    category: 'water_quality',
    title: '암모니아 농도 위험 수준 초과',
    message: '암모니아 농도 0.82 ppm — 위험 임계값(0.8 ppm)을 초과했습니다. 즉각적인 수질 개선 조치가 필요합니다.',
    is_active: true,
    metric_name: 'ammonia_ppm',
    metric_value: '0.82',
    threshold_value: '0.80',
    source: 'virtual_sensor',
  },
  {
    id: 102,
    tank_id: 'TANK-02',
    created_at: new Date(Date.now() - 91 * 60_000).toISOString(),
    resolved_at: null,
    severity: 'critical',
    category: 'water_quality',
    title: '용존산소 위험 수준',
    message: '용존산소 5.1 mg/L — 위험 임계값(6.0 mg/L) 미만입니다. 산기장치를 확인하세요.',
    is_active: true,
    metric_name: 'dissolved_oxygen_mgl',
    metric_value: '5.1',
    threshold_value: '6.0',
    source: 'virtual_sensor',
  },
  {
    id: 103,
    tank_id: 'TANK-02',
    created_at: new Date(Date.now() - 3 * 3600_000).toISOString(),
    resolved_at: null,
    severity: 'warning',
    category: 'water_quality',
    title: '탁도 경고',
    message: '탁도 14.3 NTU — 권장 상한(10 NTU)을 초과했습니다. 여과 시스템을 점검하세요.',
    is_active: true,
    metric_name: 'turbidity_ntu',
    metric_value: '14.3',
    threshold_value: '10.0',
    source: 'sensor',
  },
  {
    id: 104,
    tank_id: 'TANK-01',
    created_at: new Date(Date.now() - 6 * 3600_000).toISOString(),
    resolved_at: new Date(Date.now() - 5 * 3600_000).toISOString(),
    severity: 'warning',
    category: 'feeding',
    title: '급이량 과다 감지',
    message: '실제 급이량(3.22 kg)이 권장량(2.80 kg) 대비 115% 수준입니다.',
    is_active: false,
    metric_name: 'actual_amount_kg',
    metric_value: '3.22',
    threshold_value: '2.80',
    source: 'ai',
  },
]

// ── Dashboard summary ─────────────────────────────────────────────────────────

export function getDashboardSummary() {
  const growthRows = generateFishGrowth('TANK-01', 1)
  const latestGrowth = growthRows[0]

  return {
    water_quality: getCurrentWQ('TANK-01'),
    fish_growth:   latestGrowth,
    active_alert_count: MOCK_ALERTS.filter((a) => a.is_active).length,
    recent_alerts: MOCK_ALERTS.filter((a) => a.is_active).slice(0, 5),
  }
}

// ── Agent cycle / optimization ────────────────────────────────────────────────

export const MOCK_AGENT_STATUS = {
  status: 'completed',
  ran_at: new Date(Date.now() - 8 * 60_000).toISOString(),
  final_report:
    'TANK-01 암모니아 수치 상승 감지. 환수 10% 실행 권고. TANK-02 산소 공급 증량 조치 완료. 전반적 급이 효율 개선 추세.',
  decisions: [
    {
      action_type: 'water_exchange',
      tank_id: 'TANK-01',
      parameters: { exchange_pct: 10 },
      reasoning: '암모니아 농도 0.82 ppm — 환수로 희석 필요',
      confidence: 0.91,
    },
    {
      action_type: 'aeration_increase',
      tank_id: 'TANK-02',
      parameters: { boost_pct: 35 },
      reasoning: '용존산소 5.1 mg/L — 산기 부스트로 DO 회복',
      confidence: 0.87,
    },
  ],
  executed: [
    { decision: { action_type: 'aeration_increase', tank_id: 'TANK-02', parameters: { boost_pct: 35 }, reasoning: '', confidence: 0.87 }, status: 'ok' },
  ],
  error: null,
}

export const MOCK_OPT_STATUS = {
  status: 'completed',
  ran_at: new Date(Date.now() - 8 * 60_000).toISOString(),
  tank_id: 'TANK-01',
  selected_action: {
    action: 'water_exchange',
    parameters: { exchange_pct: 10, duration_s: 300 },
    reasoning: '니트리피케이션 ODE 시뮬레이션 결과 10% 환수가 최적 점수(0.91)를 달성. 암모니아 0.82→0.52 ppm 예측.',
    score: 0.91,
  },
  simulation_result: {
    status: 'completed',
    candidates_evaluated: 5,
    best_action: 'water_exchange',
    best_score: 0.91,
  },
  candidates: 5,
}
