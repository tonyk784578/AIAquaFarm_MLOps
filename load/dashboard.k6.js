// Dashboard REST smoke — stresses the 5-second TTL cache + DB fall-through.
//
//   k6 run load/dashboard.k6.js                       # smoke (10 VUs × 30 s)
//   K6_VUS=50 K6_DURATION=5m k6 run load/dashboard.k6.js
//
// The dashboard summary is served from a Redis cache with a 5 s TTL; when the
// cache lapses, every concurrent VU lights up Postgres at once. The p(95) SLO
// is generous (500 ms) precisely to absorb that thundering herd, but anything
// above 1 s is a regression worth investigating.
import http from 'k6/http'
import { check, sleep } from 'k6'

import { BASE_URL, login } from './lib/auth.js'

export const options = {
  vus: Number(__ENV.K6_VUS || 10),
  duration: __ENV.K6_DURATION || '30s',
  thresholds: {
    'http_req_failed':           ['rate<0.01'],
    'http_req_duration{stage:summary}': ['p(95)<500'],
    'checks':                    ['rate>0.99'],
  },
}

export function setup() {
  // One login per test run (k6 setup runs once before the VUs spin up).
  // The token survives until logout / TTL expires.
  return { cookie: login() }
}

export default function (data) {
  // k6's CookieJar (per-VU) doesn't share with setup(), so explicit Cookie header.
  const headers = data.cookie
    ? { Cookie: `aq_access=${data.cookie}` }
    : {}

  const res = http.get(`${BASE_URL}/api/v1/dashboard/summary`, {
    headers,
    tags: { stage: 'summary' },
  })
  check(res, {
    '200 OK':                  (r) => r.status === 200,
    'has water_quality field': (r) => r.json('water_quality') !== undefined,
  })

  sleep(1)
}
