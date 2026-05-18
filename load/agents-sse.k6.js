// Agents SSE smoke — N VUs hold an EventSource against /agents/events/stream
// and observe how long the agents service can sustain concurrent subscribers
// (each one keeps a redis pubsub connection open).
//
// Note: k6 has no native EventSource client, but the protocol is line-oriented
// HTTP. We stream the response with http.get + responseCallback and count
// `data: ...` lines as events.
//
//   K6_VUS=20 K6_DURATION=60s k6 run load/agents-sse.k6.js
import http from 'k6/http'
import { check, sleep } from 'k6'
import { Counter } from 'k6/metrics'

import { login } from './lib/auth.js'

const AGENT_URL = __ENV.K6_AGENT_URL || 'http://localhost:8001'
const SESSION_SECONDS = Number(__ENV.SESSION_SECONDS || 15)

const sseEvents = new Counter('aquafarm_sse_events')

export const options = {
  vus: Number(__ENV.K6_VUS || 10),
  duration: __ENV.K6_DURATION || '60s',
  thresholds: {
    'http_req_failed': ['rate<0.01'],
    'checks':          ['rate>0.99'],
  },
}

export function setup() {
  return { cookie: login() }
}

export default function (data) {
  // The agents service is reachable directly on :8001 or via /agents/ on the
  // nginx gateway. Pick whichever K6_AGENT_URL points at.
  const res = http.get(`${AGENT_URL}/events/stream`, {
    headers: data.cookie ? { Cookie: `aq_access=${data.cookie}` } : {},
    timeout: `${SESSION_SECONDS + 5}s`,
    // k6 streams the body to memory; for long sessions, raise the iterations
    // duration instead of `timeout`. We hold for SESSION_SECONDS then close.
  })

  check(res, {
    'sse status 200': (r) => r.status === 200,
    'content-type is event-stream':
      (r) => (r.headers['Content-Type'] || '').includes('event-stream'),
  })

  // Each event arrives as `event: <name>\ndata: <json>\n\n`. Count the data
  // lines we received during the buffered read.
  if (res.body) {
    const count = String(res.body).split(/\n/).filter((l) => l.startsWith('data:')).length
    sseEvents.add(count)
  }
  sleep(1)
}
