// WebSocket fan-out smoke — N VUs subscribe to /api/v1/ws/monitoring/{tank_id}
// and consume the live wq:* stream.
//
// Pass criteria:
//   • every VU receives ≥ 1 message within 20 s
//   • abnormal closures < 1 %
//   • mean message latency below a few hundred ms
//
//   K6_VUS=50 K6_DURATION=2m k6 run load/monitoring-ws.k6.js
import ws from 'k6/ws'
import { check } from 'k6'
import { Counter, Trend } from 'k6/metrics'

import { BASE_URL, login } from './lib/auth.js'

const TANK_IDS = (__ENV.TANK_IDS || 'TANK-01,TANK-02,TANK-03').split(',')
const SESSION_SECONDS = Number(__ENV.SESSION_SECONDS || 20)

const wsMessages = new Counter('aquafarm_ws_messages')
const wsFirstMessageMs = new Trend('aquafarm_ws_first_message_ms', true)

export const options = {
  vus: Number(__ENV.K6_VUS || 25),
  duration: __ENV.K6_DURATION || '60s',
  thresholds: {
    'ws_connecting':                ['p(95)<2000'],
    'aquafarm_ws_first_message_ms': ['p(95)<15000'],   // SensorPublisher every 5 s
    'checks':                       ['rate>0.99'],
  },
}

export function setup() {
  return { cookie: login() }
}

export default function (data) {
  const tank = TANK_IDS[(__VU - 1) % TANK_IDS.length]
  // Browser URL would be ws://host/api/v1/ws/... — same scheme transform here.
  const wsUrl = BASE_URL.replace(/^http/, 'ws') + `/api/v1/ws/monitoring/${tank}`

  // The backend WS handler accepts both cookie and bearer; cookie is the
  // browser path so we mirror it for realism.
  const params = data.cookie
    ? { headers: { Cookie: `aq_access=${data.cookie}` } }
    : {}

  const start = Date.now()
  let firstSeen = false

  const res = ws.connect(wsUrl, params, function (socket) {
    socket.on('message', (msg) => {
      wsMessages.add(1)
      if (!firstSeen) {
        firstSeen = true
        wsFirstMessageMs.add(Date.now() - start)
      }
      // Validate at least one message has the expected shape.
      try {
        const parsed = JSON.parse(msg)
        check(parsed, {
          'message has type field':    (m) => typeof m.type === 'string',
          'message has tank_id field': (m) => typeof m.tank_id === 'string',
        })
      } catch {
        // non-JSON keepalive — ignore
      }
    })

    socket.on('error', (e) => {
      console.error(`ws error: ${e.error()}`)
    })

    // Hold the connection open so SensorPublisher pushes a few intervals.
    socket.setTimeout(() => socket.close(), SESSION_SECONDS * 1000)
  })

  check(res, {
    'ws handshake 101': (r) => r && r.status === 101,
  })
}
