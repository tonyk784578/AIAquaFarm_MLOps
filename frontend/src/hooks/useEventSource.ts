// SSE hook for agent live events (`/agents/events/stream`).
// Connects to the EventSource endpoint, parses JSON payloads from the
// custom `agent` event, and exposes the most recent N events with status.
//
// Reconnect: native EventSource auto-reconnects on transient failures.
// We additionally track readyState transitions and back off on hard failures.

import { useCallback, useEffect, useRef, useState } from 'react'

import type { AgentEvent } from '@/types'

export type SSEStatus = 'connecting' | 'open' | 'closed' | 'error'

interface UseEventSourceOptions {
  enabled?: boolean
  /** Maximum events retained in the rolling buffer. */
  bufferSize?: number
  /** Optional callback for every event (useful for imperative side-effects). */
  onEvent?: (event: AgentEvent) => void
  /** Reconnect attempts before giving up (0 = unlimited). */
  maxReconnectAttempts?: number
  /** Base delay (ms) for exponential backoff between reconnects. */
  reconnectBaseDelay?: number
}

interface UseEventSourceReturn {
  status: SSEStatus
  events: AgentEvent[]
  lastEvent: AgentEvent | null
  reconnectAttempts: number
  close: () => void
}

function safeParse(raw: string): AgentEvent | null {
  try {
    const parsed = JSON.parse(raw)
    if (
      parsed &&
      typeof parsed === 'object' &&
      typeof parsed.kind === 'string' &&
      typeof parsed.ts === 'string'
    ) {
      return parsed as AgentEvent
    }
  } catch {
    /* swallow */
  }
  return null
}

export function useEventSource(
  url: string,
  options: UseEventSourceOptions = {}
): UseEventSourceReturn {
  const {
    enabled = true,
    bufferSize = 50,
    onEvent,
    maxReconnectAttempts = 0,
    reconnectBaseDelay = 1_000,
  } = options

  const [status, setStatus] = useState<SSEStatus>('connecting')
  const [events, setEvents] = useState<AgentEvent[]>([])
  const [reconnectAttempts, setReconnectAttempts] = useState(0)

  const sourceRef = useRef<EventSource | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const onEventRef = useRef(onEvent)
  onEventRef.current = onEvent

  const close = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
    if (sourceRef.current) {
      sourceRef.current.close()
      sourceRef.current = null
    }
    setStatus('closed')
  }, [])

  useEffect(() => {
    if (!enabled) {
      close()
      return
    }

    let cancelled = false
    let attempt = 0

    const connect = () => {
      if (cancelled) return
      setStatus('connecting')
      const es = new EventSource(url, { withCredentials: true })
      sourceRef.current = es

      es.onopen = () => {
        attempt = 0
        setReconnectAttempts(0)
        setStatus('open')
      }

      // The backend emits events under the `agent` event name; `ping` is a keep-alive.
      es.addEventListener('agent', (msg) => {
        const event = safeParse((msg as MessageEvent).data)
        if (!event) return
        setEvents((prev) => {
          const next = [...prev, event]
          return next.length > bufferSize ? next.slice(-bufferSize) : next
        })
        onEventRef.current?.(event)
      })

      es.addEventListener('ping', () => {
        // no-op — keep-alive
      })

      es.onerror = () => {
        es.close()
        if (cancelled) return
        if (maxReconnectAttempts > 0 && attempt >= maxReconnectAttempts) {
          setStatus('error')
          return
        }
        attempt += 1
        setReconnectAttempts(attempt)
        setStatus('error')
        const delay = Math.min(reconnectBaseDelay * 2 ** (attempt - 1), 30_000)
        timerRef.current = setTimeout(connect, delay)
      }
    }

    connect()

    return () => {
      cancelled = true
      close()
    }
  }, [url, enabled, bufferSize, maxReconnectAttempts, reconnectBaseDelay, close])

  return {
    status,
    events,
    lastEvent: events.length > 0 ? events[events.length - 1] : null,
    reconnectAttempts,
    close,
  }
}
