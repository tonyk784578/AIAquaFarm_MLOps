/**
 * Tests for the WebSocket monitoring hook.
 *
 * Uses the MockWebSocket installed by ``src/test/setup.ts`` — drives open /
 * message / close events imperatively to verify status transitions, message
 * parsing, ping filtering, and the reconnect / give-up policy.
 */
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useWebSocket } from './useWebSocket'
import { MockWebSocket } from '@/test/setup'

beforeEach(() => {
  vi.useFakeTimers()
})
afterEach(() => {
  vi.useRealTimers()
})

describe('useWebSocket', () => {
  it('opens a WebSocket and reports `connected` after onopen', () => {
    const { result } = renderHook(() => useWebSocket('TANK-01'))

    expect(MockWebSocket.instances).toHaveLength(1)
    expect(MockWebSocket.last().url).toContain('/api/v1/ws/monitoring/TANK-01')
    expect(result.current.status).toBe('connecting')

    act(() => MockWebSocket.last().triggerOpen())
    expect(result.current.status).toBe('connected')
  })

  it('parses JSON messages and exposes the latest one', () => {
    const onMessage = vi.fn()
    const { result } = renderHook(() => useWebSocket('TANK-01', { onMessage }))

    act(() => MockWebSocket.last().triggerOpen())
    act(() =>
      MockWebSocket.last().triggerMessage(
        JSON.stringify({ type: 'wq', tank_id: 'TANK-01', value: 7.2 }),
      ),
    )

    expect(result.current.lastMessage).toEqual({
      type: 'wq',
      tank_id: 'TANK-01',
      value: 7.2,
    })
    expect(onMessage).toHaveBeenCalledTimes(1)
  })

  it('drops ping keepalives without surfacing them', () => {
    const onMessage = vi.fn()
    const { result } = renderHook(() => useWebSocket('TANK-01', { onMessage }))
    act(() => MockWebSocket.last().triggerOpen())

    act(() =>
      MockWebSocket.last().triggerMessage(JSON.stringify({ type: 'ping' })),
    )
    expect(onMessage).not.toHaveBeenCalled()
    expect(result.current.lastMessage).toBeNull()
  })

  it('ignores malformed (non-JSON) frames', () => {
    const onMessage = vi.fn()
    renderHook(() => useWebSocket('TANK-01', { onMessage }))
    act(() => MockWebSocket.last().triggerOpen())

    act(() => MockWebSocket.last().triggerMessage('not json'))
    expect(onMessage).not.toHaveBeenCalled()
  })

  it('reconnects with linear backoff capped at 4×', () => {
    renderHook(() =>
      useWebSocket('TANK-01', {
        reconnectInterval: 100,
        maxReconnectAttempts: 5,
      }),
    )
    expect(MockWebSocket.instances).toHaveLength(1)

    // First abnormal close → reconnect after 100 ms (attempt 1 × 100)
    act(() => MockWebSocket.last().triggerClose(1006))
    act(() => vi.advanceTimersByTime(100))
    expect(MockWebSocket.instances).toHaveLength(2)

    // Second close → 200 ms backoff (attempt 2)
    act(() => MockWebSocket.last().triggerClose(1006))
    act(() => vi.advanceTimersByTime(199))
    expect(MockWebSocket.instances).toHaveLength(2)
    act(() => vi.advanceTimersByTime(1))
    expect(MockWebSocket.instances).toHaveLength(3)
  })

  it('gives up and reports `error` after max attempts', () => {
    const { result } = renderHook(() =>
      useWebSocket('TANK-01', {
        reconnectInterval: 50,
        maxReconnectAttempts: 2,
      }),
    )

    for (let i = 0; i < 3; i += 1) {
      act(() => MockWebSocket.last().triggerClose(1006))
      act(() => vi.advanceTimersByTime(500))
    }

    // 2 reconnect attempts max → instance count = original + 2
    expect(MockWebSocket.instances.length).toBe(3)
    expect(result.current.status).toBe('error')
  })

  it('does NOT reconnect when the component unmounts', () => {
    const { unmount } = renderHook(() =>
      useWebSocket('TANK-01', { reconnectInterval: 50 }),
    )
    unmount()
    act(() => vi.advanceTimersByTime(5_000))
    // The unmount cleanup closes the socket but should not spawn a new one.
    expect(MockWebSocket.instances).toHaveLength(1)
  })

  it('send() forwards JSON when the socket is open', () => {
    const { result } = renderHook(() => useWebSocket('TANK-01'))
    act(() => MockWebSocket.last().triggerOpen())

    act(() => result.current.send({ ping: 1 }))
    expect(MockWebSocket.last().sentMessages).toEqual(['{"ping":1}'])
  })

  it('send() is a no-op while the socket is still connecting', () => {
    const { result } = renderHook(() => useWebSocket('TANK-01'))
    // Don't trigger open — readyState stays at CONNECTING.
    act(() => result.current.send({ ping: 1 }))
    expect(MockWebSocket.last().sentMessages).toEqual([])
  })
})
