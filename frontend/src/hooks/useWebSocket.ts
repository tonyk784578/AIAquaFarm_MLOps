// WebSocket hook for real-time data streaming from backend.
// Connects to WS /api/v1/ws/monitoring/{tankId} and receives
// WSMessage events pushed from the Redis pub/sub channel.

import { useCallback, useEffect, useRef, useState } from 'react'
import type { WSMessage } from '@/types'

type WSStatus = 'connecting' | 'connected' | 'disconnected' | 'error'

interface UseWebSocketOptions {
  onMessage?: (message: WSMessage) => void
  reconnectInterval?: number
  maxReconnectAttempts?: number
  enabled?: boolean
}

interface UseWebSocketReturn {
  status: WSStatus
  lastMessage: WSMessage | null
  send: (data: unknown) => void
  disconnect: () => void
}

const WS_BASE_URL =
  (import.meta.env.VITE_WS_BASE_URL as string | undefined) ||
  (typeof window !== 'undefined'
    ? `ws://${window.location.hostname}:8000`
    : 'ws://localhost:8000')

export function useWebSocket(
  tankId: string,
  options: UseWebSocketOptions = {}
): UseWebSocketReturn {
  const {
    onMessage,
    reconnectInterval = 3000,
    maxReconnectAttempts = 5,
    enabled = true,
  } = options

  const wsRef = useRef<WebSocket | null>(null)
  const reconnectAttemptsRef = useRef(0)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const mountedRef = useRef(true)

  const [status, setStatus] = useState<WSStatus>('disconnected')
  const [lastMessage, setLastMessage] = useState<WSMessage | null>(null)

  const disconnect = useCallback(() => {
    mountedRef.current = false
    if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current)
    wsRef.current?.close(1000, 'client disconnect')
    wsRef.current = null
  }, [])

  const connect = useCallback(() => {
    if (!enabled || !mountedRef.current) return

    const url = `${WS_BASE_URL}/api/v1/ws/monitoring/${tankId}`
    setStatus('connecting')

    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      if (!mountedRef.current) { ws.close(); return }
      reconnectAttemptsRef.current = 0
      setStatus('connected')
    }

    ws.onmessage = (event: MessageEvent) => {
      if (!mountedRef.current) return
      try {
        const msg = JSON.parse(event.data as string) as WSMessage
        if (msg.type === 'ping') return            // server keepalive
        setLastMessage(msg)
        onMessage?.(msg)
      } catch {
        // non-JSON frame — ignore
      }
    }

    ws.onclose = () => {
      if (!mountedRef.current) return
      setStatus('disconnected')
      if (reconnectAttemptsRef.current < maxReconnectAttempts) {
        reconnectAttemptsRef.current++
        const delay = reconnectInterval * Math.min(reconnectAttemptsRef.current, 4)
        reconnectTimerRef.current = setTimeout(connect, delay)
      } else {
        setStatus('error')
      }
    }

    ws.onerror = () => {
      setStatus('error')
    }
  }, [tankId, enabled, onMessage, reconnectInterval, maxReconnectAttempts])

  useEffect(() => {
    mountedRef.current = true
    connect()
    return () => {
      mountedRef.current = false
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current)
      wsRef.current?.close(1000, 'component unmount')
    }
  }, [connect])

  const send = useCallback((data: unknown) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data))
    }
  }, [])

  return { status, lastMessage, send, disconnect }
}
