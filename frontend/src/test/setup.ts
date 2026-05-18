/**
 * Vitest setup — runs once before every test file.
 *
 * Responsibilities:
 *   1. Register @testing-library/jest-dom matchers (`toBeInTheDocument`, …).
 *   2. Auto-cleanup the React render tree after each test (avoid bleed).
 *   3. Polyfill `EventSource` since jsdom does not ship one — needed by
 *      the `useEventSource` hook.
 *   4. Polyfill `matchMedia` (Recharts / theme stores touch it).
 */
import '@testing-library/jest-dom/vitest'

import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

afterEach(() => {
  cleanup()
})

// ── matchMedia polyfill ──────────────────────────────────────────────────────
if (typeof window !== 'undefined' && !window.matchMedia) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  })
}

// ── EventSource polyfill ─────────────────────────────────────────────────────
// jsdom has no native EventSource. Tests that exercise useEventSource can grab
// the global stub via `MockEventSource.instances` and drive it imperatively.
//
//    const es = MockEventSource.last()
//    es.emit('agent', JSON.stringify({ ... }))
//    es.triggerError()
//    es.triggerOpen()
type Listener = (event: { data?: string }) => void

export class MockEventSource {
  static instances: MockEventSource[] = []
  static last(): MockEventSource {
    const arr = MockEventSource.instances
    if (arr.length === 0) {
      throw new Error('no MockEventSource yet — call useEventSource first')
    }
    return arr[arr.length - 1]
  }

  readonly url: string
  readonly withCredentials: boolean
  readyState: 0 | 1 | 2 = 0   // CONNECTING
  onopen: ((e: Event) => void) | null = null
  onerror: ((e: Event) => void) | null = null
  onmessage: ((e: { data: string }) => void) | null = null

  private listeners: Map<string, Set<Listener>> = new Map()

  constructor(url: string, init?: EventSourceInit) {
    this.url = url
    this.withCredentials = init?.withCredentials ?? false
    MockEventSource.instances.push(this)
  }

  addEventListener(type: string, listener: Listener): void {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set())
    this.listeners.get(type)!.add(listener)
  }

  removeEventListener(type: string, listener: Listener): void {
    this.listeners.get(type)?.delete(listener)
  }

  emit(type: string, data: string): void {
    const ls = this.listeners.get(type)
    ls?.forEach((l) => l({ data }))
  }

  triggerOpen(): void {
    this.readyState = 1
    this.onopen?.(new Event('open'))
  }

  triggerError(): void {
    this.readyState = 2
    this.onerror?.(new Event('error'))
  }

  close(): void {
    this.readyState = 2
  }
}

// Install on globalThis so production code's `new EventSource(url)` resolves
// to our stub at runtime.
;(globalThis as unknown as { EventSource: typeof MockEventSource }).EventSource =
  MockEventSource

// ── WebSocket polyfill ───────────────────────────────────────────────────────
// jsdom has no native WebSocket either. Same imperative shape as the SSE stub:
//
//    const ws = MockWebSocket.last()
//    ws.triggerOpen()
//    ws.triggerMessage('{"type":"wq"}')
//    ws.triggerClose(1006)            // abnormal closure → reconnect path
export class MockWebSocket {
  static instances: MockWebSocket[] = []
  static last(): MockWebSocket {
    const arr = MockWebSocket.instances
    if (arr.length === 0) throw new Error('no MockWebSocket yet')
    return arr[arr.length - 1]
  }

  static CONNECTING = 0
  static OPEN = 1
  static CLOSING = 2
  static CLOSED = 3

  readonly url: string
  readyState: 0 | 1 | 2 | 3 = 0
  onopen: ((e: Event) => void) | null = null
  onclose: ((e: { code: number; reason: string }) => void) | null = null
  onmessage: ((e: { data: string }) => void) | null = null
  onerror: ((e: Event) => void) | null = null

  sentMessages: string[] = []

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  send(data: string): void {
    this.sentMessages.push(data)
  }
  close(code = 1000, reason = ''): void {
    this.readyState = 3
    this.onclose?.({ code, reason })
  }
  triggerOpen(): void {
    this.readyState = 1
    this.onopen?.(new Event('open'))
  }
  triggerMessage(data: string): void {
    this.onmessage?.({ data })
  }
  triggerClose(code = 1006, reason = 'abnormal'): void {
    this.readyState = 3
    this.onclose?.({ code, reason })
  }
  triggerError(): void {
    this.onerror?.(new Event('error'))
  }
}

;(globalThis as unknown as { WebSocket: typeof MockWebSocket }).WebSocket =
  MockWebSocket as unknown as typeof WebSocket

// Reset between tests
afterEach(() => {
  MockEventSource.instances = []
  MockWebSocket.instances = []
})
