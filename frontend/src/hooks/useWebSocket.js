import { useEffect, useRef, useState, useCallback } from 'react'

const WS_BASE_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws'

// Connection states
const CONNECTION_STATES = {
  CONNECTING: 'CONNECTING',
  OPEN: 'OPEN',
  CLOSED: 'CLOSED',
  ERROR: 'ERROR'
}

export const useWebSocket = (sessionId, onMessage, options = {}) => {
  const [connectionState, setConnectionState] = useState(CONNECTION_STATES.CLOSED)
  const [isConnected, setIsConnected] = useState(false)
  const [error, setError] = useState(null)
  const wsRef = useRef(null)
  const reconnectAttemptsRef = useRef(0)
  const reconnectTimeoutRef = useRef(null)
  const maxReconnectAttempts = options.maxReconnectAttempts || 10
  const baseReconnectDelay = options.baseReconnectDelay || 1000 // 1s start
  const maxDelay = options.maxDelay || 8000 // 8s max

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return
    }

    try {
      setConnectionState(CONNECTION_STATES.CONNECTING)
      const wsUrl = `${WS_BASE_URL}/${sessionId}`
      console.log('WebSocket connecting to:', wsUrl)
      const ws = new WebSocket(wsUrl)

      ws.onopen = () => {
        console.log('WebSocket connected')
        setConnectionState(CONNECTION_STATES.OPEN)
        setIsConnected(true)
        setError(null)
        reconnectAttemptsRef.current = 0
      }

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data)

          // Parse message by channel
          if (message.channel === 'detections') {
            if (onMessage) {
              onMessage({ type: 'detection', data: message.data })
            }
          } else if (message.channel === 'incidents') {
            if (onMessage) {
              onMessage({ type: 'incident', data: message.data })
            }
          } else if (message.channel === 'metrics') {
            if (onMessage) {
              onMessage({ type: 'metrics', data: message.data })
            }
          } else if (message.channel === 'heatmap') {
            if (onMessage) {
              onMessage({ type: 'heatmap', data: message.data })
            }
          } else {
            // Generic message handling for other channels
            if (onMessage) {
              onMessage(message)
            }
          }
        } catch (err) {
          console.error('Failed to parse WebSocket message:', err)
        }
      }

      ws.onerror = (event) => {
        console.error('WebSocket error:', event)
        setConnectionState(CONNECTION_STATES.ERROR)
        setError('WebSocket connection error')
      }

      ws.onclose = () => {
        console.log('WebSocket disconnected')
        setConnectionState(CONNECTION_STATES.CLOSED)
        setIsConnected(false)
        wsRef.current = null

        // Auto-reconnect with exponential backoff (1s, 2s, 4s, 8s max)
        if (reconnectAttemptsRef.current < maxReconnectAttempts) {
          const delay = Math.min(
            baseReconnectDelay * Math.pow(2, reconnectAttemptsRef.current),
            maxDelay
          )
          console.log(`Attempting reconnect in ${delay}ms (attempt ${reconnectAttemptsRef.current + 1}/${maxReconnectAttempts})`)
          reconnectTimeoutRef.current = setTimeout(() => {
            reconnectAttemptsRef.current += 1
            connect()
          }, delay)
        } else {
          setError('Failed to reconnect after maximum attempts')
        }
      }

      wsRef.current = ws
    } catch (err) {
      console.error('Failed to create WebSocket:', err)
      setConnectionState(CONNECTION_STATES.ERROR)
      setError(err.message)
    }
  }, [sessionId, onMessage, maxReconnectAttempts, baseReconnectDelay, maxDelay])

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
    }
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    setConnectionState(CONNECTION_STATES.CLOSED)
    setIsConnected(false)
  }, [])

  const send = useCallback((message) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message))
      return true
    } else {
      console.warn('WebSocket is not connected, cannot send message')
      return false
    }
  }, [])

  const sendMessage = useCallback((text) => {
    return send({
      type: 'chat',
      message: text
    })
  }, [send])

  const subscribe = useCallback((channel) => {
    send({
      type: 'subscribe',
      channel
    })
  }, [send])

  const unsubscribe = useCallback((channel) => {
    send({
      type: 'unsubscribe',
      channel
    })
  }, [send])

  useEffect(() => {
    if (sessionId) {
      connect()
    }

    return () => {
      disconnect()
    }
  }, [sessionId, connect, disconnect])

  return {
    isConnected,
    connectionState,
    error,
    send,
    sendMessage,
    subscribe,
    unsubscribe,
    disconnect,
    CONNECTION_STATES
  }
}
