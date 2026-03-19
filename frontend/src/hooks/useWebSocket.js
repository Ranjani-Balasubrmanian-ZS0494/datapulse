import { useEffect, useRef, useState, useCallback } from 'react'

const WS_BASE = (import.meta.env.VITE_WS_URL || 'ws://localhost:8000')

/**
 * useWebSocket(path)
 *
 * Connects to `WS_BASE + path`, returns { lastMessage, sendMessage }.
 * Auto-reconnects after 3 seconds on unexpected close.
 */
export default function useWebSocket(path) {
  const [lastMessage, setLastMessage] = useState(null)
  const ws = useRef(null)
  const reconnectTimer = useRef(null)

  const connect = useCallback(() => {
    if (!path) return
    const url = `${WS_BASE}${path}`
    ws.current = new WebSocket(url)

    ws.current.onmessage = (evt) => {
      try {
        setLastMessage(JSON.parse(evt.data))
      } catch (_) {
        setLastMessage(evt.data)
      }
    }

    ws.current.onclose = () => {
      reconnectTimer.current = setTimeout(connect, 3000)
    }

    ws.current.onerror = () => {
      ws.current?.close()
    }
  }, [path])

  useEffect(() => {
    connect()
    return () => {
      clearTimeout(reconnectTimer.current)
      ws.current?.close()
    }
  }, [connect])

  const sendMessage = useCallback((msg) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(typeof msg === 'string' ? msg : JSON.stringify(msg))
    }
  }, [])

  return { lastMessage, sendMessage }
}
