// Shared login helper used by every k6 script.
//
// Logs in with admin credentials and returns the `aq_access` cookie value.
// k6 keeps cookies per-VU automatically via its CookieJar, so individual
// requests don't need to re-attach them — but having the raw value lets us
// pass it to WebSocket / SSE handshakes too.

import http from 'k6/http'
import { check } from 'k6'

const BASE_URL = __ENV.K6_BASE_URL || 'http://localhost:8000'
const ADMIN_USER = __ENV.ADMIN_USER || 'admin'
const ADMIN_PASS = __ENV.ADMIN_PASS || 'admin'

/**
 * Performs the OAuth2 password-grant login and returns the access cookie.
 *
 * The backend issues two httpOnly cookies; we only need `aq_access` for
 * Authorization on subsequent calls (the same cookie jar is reused).
 */
export function login(baseUrl) {
  const url = `${baseUrl || BASE_URL}/api/v1/auth/login`
  const payload = `username=${encodeURIComponent(ADMIN_USER)}&password=${encodeURIComponent(ADMIN_PASS)}`
  const res = http.post(url, payload, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  })
  check(res, {
    'login status is 200': (r) => r.status === 200,
  })
  // Cookie name pinned by backend/app/api/v1/auth.py.
  const cookies = res.cookies['aq_access']
  return cookies && cookies.length > 0 ? cookies[0].value : null
}

export { BASE_URL }
