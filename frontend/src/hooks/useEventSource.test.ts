/**
 * Tests for the SSE hook.
 *
 * Drives the MockEventSource installed by ``src/test/setup.ts``. The hook
 * itself never knows it's talking to a mock — it just calls
 * ``new EventSource(url)`` which jsdom resolves to the stub.
 */
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useEventSource } from './useEventSource'
import { MockEventSource } from '@/test/setup'

const URL = '/agents/events/stream'

beforeEach(() => {
  vi.useFakeTimers()
})
afterEach(() => {
  vi.useRealTimers()
})

describe('useEventSource', () => {
  it('opens an EventSource and reports `open` after onopen fires', () => {
    const { result } = renderHook(() => useEventSource(URL))

    expect(MockEventSource.instances).toHaveLength(1)
    expect(result.current.status).toBe('connecting')

    act(() => {
      MockEventSource.last().triggerOpen()
    })
    expect(result.current.status).toBe('open')
  })

  it('parses agent events and appends them to the buffer', () => {
    const { result } = renderHook(() => useEventSource(URL))
    const es = MockEventSource.last()

    act(() => es.triggerOpen())
    act(() => {
      es.emit(
        'agent',
        JSON.stringify({
          ts: '2026-05-18T10:00:00Z',
          kind: 'cycle_started',
          tank_id: 'TANK-01',
          data: {},
        }),
      )
    })

    expect(result.current.events).toHaveLength(1)
    expect(result.current.lastEvent?.kind).toBe('cycle_started')
    expect(result.current.lastEvent?.tank_id).toBe('TANK-01')
  })

  it('drops malformed payloads silently', () => {
    const { result } = renderHook(() => useEventSource(URL))
    const es = MockEventSource.last()

    act(() => {
      es.emit('agent', 'not json')
      es.emit('agent', JSON.stringify({ missing: 'fields' }))
    })

    expect(result.current.events).toHaveLength(0)
  })

  it('respects bufferSize by trimming oldest entries', () => {
    const { result } = renderHook(() =>
      useEventSource(URL, { bufferSize: 3 }),
    )
    const es = MockEventSource.last()

    act(() => {
      for (let i = 0; i < 5; i += 1) {
        es.emit(
          'agent',
          JSON.stringify({
            ts: `2026-05-18T10:00:0${i}Z`,
            kind: 'node_completed',
            tank_id: '',
            data: { node: `n${i}` },
          }),
        )
      }
    })

    expect(result.current.events).toHaveLength(3)
    // Oldest dropped — keep n2, n3, n4
    expect(result.current.events.map((e) => e.data.node)).toEqual(['n2', 'n3', 'n4'])
  })

  it('invokes onEvent callback for every parsed payload', () => {
    const onEvent = vi.fn()
    renderHook(() => useEventSource(URL, { onEvent }))
    const es = MockEventSource.last()

    act(() => {
      es.emit(
        'agent',
        JSON.stringify({
          ts: '2026-05-18T10:00:00Z',
          kind: 'decision_made',
          tank_id: '',
          data: {},
        }),
      )
    })

    expect(onEvent).toHaveBeenCalledTimes(1)
    expect(onEvent.mock.calls[0][0].kind).toBe('decision_made')
  })

  it('reconnects with exponential backoff on transient errors', () => {
    renderHook(() =>
      useEventSource(URL, { reconnectBaseDelay: 100, maxReconnectAttempts: 0 }),
    )
    expect(MockEventSource.instances).toHaveLength(1)

    // First error → schedule reconnect after baseDelay (100 ms)
    act(() => MockEventSource.last().triggerError())
    act(() => {
      vi.advanceTimersByTime(100)
    })
    expect(MockEventSource.instances).toHaveLength(2)

    // Second error → backoff doubles to 200 ms
    act(() => MockEventSource.last().triggerError())
    act(() => {
      vi.advanceTimersByTime(99)
    })
    expect(MockEventSource.instances).toHaveLength(2) // not yet
    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(MockEventSource.instances).toHaveLength(3)
  })

  it('stops reconnecting after maxReconnectAttempts', () => {
    const { result } = renderHook(() =>
      useEventSource(URL, { reconnectBaseDelay: 10, maxReconnectAttempts: 1 }),
    )

    act(() => MockEventSource.last().triggerError())
    act(() => vi.advanceTimersByTime(50))
    expect(MockEventSource.instances.length).toBe(2)

    act(() => MockEventSource.last().triggerError())
    act(() => vi.advanceTimersByTime(1000))
    // Reconnect attempts capped at 1
    expect(MockEventSource.instances.length).toBe(2)
    expect(result.current.status).toBe('error')
  })
})
